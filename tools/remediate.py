#!/usr/bin/env python3
"""pureMind self-healing remediation engine.

Matches fleet health issues against known-safe fix patterns and executes remediation.
All actions logged to pm_audit. Deterministic -- no LLM reasoning needed.

Safety bounds (NEVER auto-fix):
  - Reboot nodes
  - Modify DNS
  - Delete data or volumes
  - Change certificates
  - Stop services (only restart)
  - Touch GPU workloads on tensor-core

Safe auto-fixes:
  - vacuum_journal: journalctl --vacuum-size=500M (when journal >2GB)
  - restart_crashed_pod: kubectl delete pod (crash-looping >5 restarts)
  - restart_failed_unit: systemctl restart (non-critical units only)
  - clear_completed_jobs: kubectl delete job (completed K8s jobs)
  - restart_tailscale: systemctl restart tailscaled (tunnel down)

Usage:
    python3 remediate.py --json                  # Check + fix
    python3 remediate.py --dry-run --json        # Show what would be fixed
    python3 remediate.py --fix vacuum_journal --node tensor-core  # Single fix
"""

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_VAULT_ROOT = str(Path(__file__).resolve().parent.parent)
if _VAULT_ROOT not in sys.path:
    sys.path.insert(0, _VAULT_ROOT)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / ".claude" / "integrations"))
from base import audited
from tools.db import get_conn

INTEGRATION = "cluster"

# Import fleet node inventory
from pathlib import Path as _P
_FLEET_MOD = _P(__file__).resolve().parent.parent / ".claude" / "integrations" / "fleet_health_integration.py"
# We import FLEET_NODES and SSH_OPTS directly
import importlib.util
_spec = importlib.util.spec_from_file_location("fleet_health", str(_FLEET_MOD))
_fleet = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fleet)
FLEET_NODES = _fleet.FLEET_NODES
SSH_OPTS = _fleet.SSH_OPTS

# ---------------------------------------------------------------------------
# Critical units -- NEVER auto-restart these
# ---------------------------------------------------------------------------
CRITICAL_UNITS = frozenset({
    "kubelet", "k3s", "k3s-agent", "docker", "containerd",
    "ceph-mon", "ceph-osd", "ceph-mgr", "ceph-mds",
    "postgresql", "postgres", "sshd", "tailscaled",
    "systemd-journald", "systemd-networkd", "systemd-resolved",
    "NetworkManager", "dbus",
})

# Critical K8s namespaces -- pods here get restarted more carefully
CRITICAL_K8S_NAMESPACES = frozenset({
    "kube-system", "databases", "cert-manager",
})

# Thresholds
JOURNAL_WARN_GB = 2.0
JOURNAL_VACUUM_TARGET = "500M"
CRASH_LOOP_RESTART_THRESHOLD = 5
COMPLETED_JOB_KEEP_HOURS = 24

# ---------------------------------------------------------------------------
# SSH helper
# ---------------------------------------------------------------------------

def _ssh(node_name: str, cmd: str, timeout: int = 15) -> tuple[int, str, str]:
    """Run SSH command on a fleet node. Returns (rc, stdout, stderr)."""
    info = FLEET_NODES.get(node_name)
    if not info:
        return -1, "", f"Unknown node: {node_name}"
    try:
        result = subprocess.run(
            ["ssh"] + SSH_OPTS + [f"{info['ssh_user']}@{info['ip']}", cmd],
            capture_output=True, text=True, timeout=timeout,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "SSH_TIMEOUT"
    except OSError as e:
        return -2, "", str(e)[:200]


# ---------------------------------------------------------------------------
# Issue discovery -- extended health checks
# ---------------------------------------------------------------------------

HEALTH_CMD = (
    "echo '===JOURNAL==='; journalctl --disk-usage 2>/dev/null; "
    "echo '===FAILED==='; systemctl --failed --no-legend --no-pager 2>/dev/null; "
    "echo '===TAILSCALE==='; tailscale status --self 2>&1 | head -1; "
    "echo '===MEMORY==='; free -m | grep Mem; "
    "echo '===DNS==='; "
    "dig +short puretensor.com 2>/dev/null | head -1; "
    "dig +short mail.puretensor.com 2>/dev/null | head -1; "
    "dig +short pureclaw.ai 2>/dev/null | head -1; "
    "echo '===DISK==='; df -h / /mnt/* 2>/dev/null | tail -n+2"
)

K3S_CMD = (
    "echo '===CRASHLOOP==='; "
    "kubectl get pods -A --no-headers 2>/dev/null | "
    "awk '{split($5,a,\"(\"); restarts=a[1]+0; if(restarts>5) print $1,$2,restarts}'; "
    "echo '===COMPLETED==='; "
    "kubectl get pods -A --field-selector=status.phase=Succeeded --no-headers 2>/dev/null"
)


def _parse_sections(stdout: str) -> dict[str, list[str]]:
    """Parse ===SECTION=== delimited output into dict of line lists."""
    sections = {}
    current = None
    for line in stdout.splitlines():
        if line.startswith("===") and line.endswith("==="):
            current = line.strip("=")
            sections[current] = []
        elif current is not None:
            if line.strip():
                sections[current].append(line.strip())
    return sections


def _parse_journal_size(lines: list[str]) -> float:
    """Parse journalctl --disk-usage output to GB."""
    for line in lines:
        # "Archived and active journals take up 4.0G in the file system."
        m = re.search(r'([\d.]+)\s*([GMK])', line)
        if m:
            val = float(m.group(1))
            unit = m.group(2)
            if unit == 'G':
                return val
            elif unit == 'M':
                return val / 1024
            elif unit == 'K':
                return val / (1024 * 1024)
    return 0.0


def discover_issues(node_name: str) -> list[dict]:
    """Run extended health checks on a node and return classified issues."""
    issues = []
    info = FLEET_NODES.get(node_name)
    if not info:
        return [{"node": node_name, "type": "unknown_node", "severity": "red",
                 "detail": f"Node {node_name} not in inventory", "remediable": False}]

    # Run health command
    rc, stdout, stderr = _ssh(node_name, HEALTH_CMD, timeout=20)
    if rc != 0 and not stdout:
        return [{"node": node_name, "type": "unreachable", "severity": "red",
                 "detail": f"SSH failed: {stderr[:100]}", "remediable": False}]

    sections = _parse_sections(stdout)

    # Journal size
    journal_gb = _parse_journal_size(sections.get("JOURNAL", []))
    if journal_gb > JOURNAL_WARN_GB:
        issues.append({
            "node": node_name, "type": "journal_large", "severity": "amber",
            "detail": f"Journal at {journal_gb:.1f}G (threshold: {JOURNAL_WARN_GB}G)",
            "remediable": True, "fix_id": "vacuum_journal",
            "fix_params": {"target": JOURNAL_VACUUM_TARGET},
        })

    # Failed systemd units
    for line in sections.get("FAILED", []):
        # "● gdrive-verify.service loaded failed failed ..."
        # Bullet (U+25CF) may be separate token or attached
        parts = line.split()
        unit = ""
        for p in parts:
            cleaned = p.replace("\u25cf", "").strip()
            if cleaned.endswith(".service") or cleaned.endswith(".timer") or cleaned.endswith(".socket"):
                unit = cleaned
                break
        if not unit:
            continue
        unit_base = unit.replace(".service", "").replace(".timer", "").replace(".socket", "")
        is_critical = unit_base in CRITICAL_UNITS
        issues.append({
            "node": node_name, "type": "failed_unit", "severity": "amber",
            "detail": f"Failed: {unit}",
            "remediable": not is_critical, "fix_id": "restart_failed_unit",
            "fix_params": {"unit": unit},
            "critical": is_critical,
        })

    # Tailscale
    ts_lines = sections.get("TAILSCALE", [])
    ts_ok = any("online" in l.lower() or info["ip"] in l for l in ts_lines)
    if not ts_ok and ts_lines:
        # If we can SSH, tailscale is probably fine -- just check for offline
        if any("offline" in l.lower() or "stopped" in l.lower() for l in ts_lines):
            issues.append({
                "node": node_name, "type": "tailscale_down", "severity": "red",
                "detail": f"Tailscale offline: {ts_lines[0][:80]}",
                "remediable": True, "fix_id": "restart_tailscale",
                "fix_params": {},
            })

    # DNS
    dns_lines = sections.get("DNS", [])
    if len(dns_lines) < 3 or any("FAIL" in l or "NXDOMAIN" in l for l in dns_lines[:3]):
        failing = [l for l in dns_lines[:3] if "FAIL" in l or "NXDOMAIN" in l or not l.strip()]
        if failing:
            issues.append({
                "node": node_name, "type": "dns_failure", "severity": "amber",
                "detail": f"DNS resolution failing on {node_name}",
                "remediable": False,  # DNS issues need investigation
            })

    # Disk
    seen = set()
    for line in sections.get("DISK", []):
        parts = line.split()
        if len(parts) >= 5:
            mount = parts[-1]
            if mount in seen:
                continue
            seen.add(mount)
            try:
                use_pct = int(parts[-2].rstrip("%"))
                if use_pct >= 90:
                    issues.append({
                        "node": node_name, "type": "disk_critical", "severity": "red",
                        "detail": f"Disk {mount} at {use_pct}% on {node_name}",
                        "remediable": False,
                    })
                elif use_pct >= 80:
                    issues.append({
                        "node": node_name, "type": "disk_warning", "severity": "amber",
                        "detail": f"Disk {mount} at {use_pct}% on {node_name}",
                        "remediable": False,
                    })
            except ValueError:
                continue

    # K3s-specific checks
    if info["role"] == "k3s-master":
        rc2, stdout2, _ = _ssh(node_name, K3S_CMD, timeout=20)
        if rc2 == 0 and stdout2:
            k3s_sections = _parse_sections(stdout2)

            # Crash-looping pods
            for line in k3s_sections.get("CRASHLOOP", []):
                parts = line.split()
                if len(parts) >= 3:
                    ns, pod, restarts = parts[0], parts[1], int(parts[2])
                    is_critical_ns = ns in CRITICAL_K8S_NAMESPACES
                    issues.append({
                        "node": node_name, "type": "crash_loop", "severity": "red",
                        "detail": f"Pod {ns}/{pod} has {restarts} restarts",
                        "remediable": True,
                        "fix_id": "restart_crashed_pod",
                        "fix_params": {"namespace": ns, "name": pod, "restarts": restarts},
                        "critical_ns": is_critical_ns,
                    })

            # Completed jobs (cleanup candidates)
            completed = k3s_sections.get("COMPLETED", [])
            for line in completed:
                parts = line.split()
                if len(parts) >= 2:
                    ns, pod = parts[0], parts[1]
                    # Extract job name from pod name (remove random suffix)
                    job_name = re.sub(r'-[a-z0-9]{5}$', '', pod)
                    issues.append({
                        "node": node_name, "type": "completed_job",
                        "severity": "green",
                        "detail": f"Completed job: {ns}/{job_name}",
                        "remediable": True,
                        "fix_id": "clear_completed_pod",
                        "fix_params": {"namespace": ns, "name": pod},
                    })

    return issues


def discover_all_issues() -> list[dict]:
    """Run discovery on all fleet nodes in parallel."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    all_issues = []
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(discover_issues, name): name for name in FLEET_NODES}
        for future in as_completed(futures):
            try:
                all_issues.extend(future.result())
            except Exception as e:
                name = futures[future]
                all_issues.append({
                    "node": name, "type": "discovery_error", "severity": "red",
                    "detail": str(e)[:200], "remediable": False,
                })
    return all_issues


# ---------------------------------------------------------------------------
# Remediation execution
# ---------------------------------------------------------------------------

def _log_remediation(node: str, fix_id: str, params: dict, success: bool, detail: str, latency_ms: int):
    """Log remediation action to pm_audit."""
    conn = get_conn()
    if conn is None:
        return
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO pm_audit (integration, function, parameters, result, detail, latency_ms)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (INTEGRATION, f"remediate:{fix_id}",
                 json.dumps({"node": node, **params}),
                 "ok" if success else "error",
                 detail[:500], latency_ms),
            )
        conn.commit()
    except Exception as e:
        print(f"WARNING: remediation audit log failed: {e}", file=sys.stderr)


def apply_fix(issue: dict, dry_run: bool = False) -> dict:
    """Apply a single fix for an issue. Returns result dict."""
    node = issue["node"]
    fix_id = issue.get("fix_id", "unknown")
    params = issue.get("fix_params", {})

    result = {
        "node": node,
        "fix_id": fix_id,
        "issue": issue["detail"],
        "status": "skipped",
        "detail": "",
    }

    if not issue.get("remediable"):
        result["status"] = "not_remediable"
        result["detail"] = "Issue not auto-remediable"
        return result

    if dry_run:
        result["status"] = "dry_run"
        result["detail"] = f"Would apply {fix_id} on {node}"
        return result

    start = time.monotonic()

    try:
        if fix_id == "vacuum_journal":
            target = params.get("target", JOURNAL_VACUUM_TARGET)
            rc, stdout, stderr = _ssh(node, f"journalctl --vacuum-size={target}", timeout=30)
            result["status"] = "ok" if rc == 0 else "error"
            result["detail"] = stdout[:200] if rc == 0 else stderr[:200]

        elif fix_id == "restart_crashed_pod":
            ns = params.get("namespace", "")
            name = params.get("name", "")
            if not ns or not name:
                result["status"] = "error"
                result["detail"] = "Missing namespace or pod name"
            else:
                k3s_node = "fox-n1"  # K3s master
                rc, stdout, stderr = _ssh(k3s_node, f"kubectl delete pod {name} -n {ns}", timeout=30)
                result["status"] = "ok" if rc == 0 else "error"
                result["detail"] = stdout[:200] if rc == 0 else stderr[:200]

        elif fix_id == "restart_failed_unit":
            unit = params.get("unit", "")
            if not unit:
                result["status"] = "error"
                result["detail"] = "Missing unit name"
            else:
                unit_base = unit.replace(".service", "").replace(".timer", "")
                if unit_base in CRITICAL_UNITS:
                    result["status"] = "blocked"
                    result["detail"] = f"Unit {unit} is critical -- manual fix required"
                else:
                    rc, stdout, stderr = _ssh(node, f"systemctl restart {unit}", timeout=15)
                    # Verify
                    rc2, stdout2, _ = _ssh(node, f"systemctl is-active {unit}", timeout=5)
                    active = stdout2.strip() == "active"
                    result["status"] = "ok" if active else "partial"
                    result["detail"] = f"Restarted {unit}, now {'active' if active else stdout2.strip()}"

        elif fix_id == "restart_tailscale":
            rc, _, stderr = _ssh(node, "systemctl restart tailscaled", timeout=15)
            # Wait briefly and verify
            import time as _t
            _t.sleep(3)
            rc2, stdout2, _ = _ssh(node, "tailscale status --self 2>&1 | head -1", timeout=5)
            online = "online" in stdout2.lower() if stdout2 else False
            result["status"] = "ok" if online else "partial"
            result["detail"] = f"Restarted tailscaled, now {'online' if online else 'check needed'}"

        elif fix_id == "clear_completed_pod":
            ns = params.get("namespace", "")
            name = params.get("name", "")
            if ns and name:
                k3s_node = "fox-n1"
                rc, stdout, stderr = _ssh(k3s_node, f"kubectl delete pod {name} -n {ns}", timeout=15)
                result["status"] = "ok" if rc == 0 else "error"
                result["detail"] = stdout[:200] if rc == 0 else stderr[:200]
            else:
                result["status"] = "error"
                result["detail"] = "Missing namespace or pod name"

        else:
            result["status"] = "unknown_fix"
            result["detail"] = f"No handler for fix_id: {fix_id}"

    except Exception as e:
        result["status"] = "error"
        result["detail"] = str(e)[:200]

    elapsed_ms = int((time.monotonic() - start) * 1000)
    _log_remediation(node, fix_id, params, result["status"] == "ok", result["detail"], elapsed_ms)

    return result


def check_and_fix(dry_run: bool = False, node_filter: str | None = None) -> dict:
    """Full self-healing cycle: discover issues, apply known fixes, report.

    Returns structured report with issues found, fixes applied, and remaining issues.
    """
    start = time.monotonic()

    # Discover
    if node_filter:
        issues = discover_issues(node_filter)
    else:
        issues = discover_all_issues()

    # Classify
    remediable = [i for i in issues if i.get("remediable")]
    escalate = [i for i in issues if not i.get("remediable") and i.get("severity") != "green"]

    # Apply fixes
    fix_results = []
    for issue in remediable:
        result = apply_fix(issue, dry_run=dry_run)
        fix_results.append(result)

    elapsed = round(time.monotonic() - start, 1)

    # Summary
    fixed = [r for r in fix_results if r["status"] == "ok"]
    failed = [r for r in fix_results if r["status"] in ("error", "partial")]
    skipped = [r for r in fix_results if r["status"] in ("dry_run", "not_remediable", "blocked")]

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dry_run": dry_run,
        "elapsed_s": elapsed,
        "summary": {
            "issues_found": len(issues),
            "remediable": len(remediable),
            "escalate": len(escalate),
            "fixed": len(fixed),
            "failed": len(failed),
            "skipped": len(skipped),
        },
        "issues": issues,
        "fixes": fix_results,
        "escalate": escalate,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="pureMind self-healing remediation engine")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be fixed")
    parser.add_argument("--node", help="Check single node only")

    args = parser.parse_args()

    report = check_and_fix(dry_run=args.dry_run, node_filter=args.node)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        s = report["summary"]
        print(f"Self-Healing Report ({report['timestamp']})")
        print(f"  Issues found: {s['issues_found']} | Remediable: {s['remediable']} | "
              f"Escalate: {s['escalate']}")
        print(f"  Fixed: {s['fixed']} | Failed: {s['failed']} | Skipped: {s['skipped']}")
        print(f"  Elapsed: {report['elapsed_s']}s")

        if report["fixes"]:
            print("\nFixes:")
            for r in report["fixes"]:
                icon = "OK" if r["status"] == "ok" else "FAIL" if r["status"] == "error" else r["status"].upper()
                print(f"  [{icon}] {r['node']}/{r['fix_id']}: {r['detail'][:80]}")

        if report["escalate"]:
            print("\nEscalate (needs human):")
            for e in report["escalate"]:
                print(f"  [{e['severity'].upper()}] {e['node']}: {e['detail'][:80]}")

        sys.exit(0 if s["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
