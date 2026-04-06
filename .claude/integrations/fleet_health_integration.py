#!/usr/bin/env python3
"""pureMind fleet health integration -- parallel node health checks via Tailscale SSH.

Read-only. Checks node reachability, disk usage, load average, and key services.
Two modes: quick_check (<30s, for heartbeat) and deep_check (2-3 min, for /health-sweep).

Usage:
    python3 fleet_health_integration.py quick_check --json
    python3 fleet_health_integration.py deep_check --json
    python3 fleet_health_integration.py quick_check --node tensor-core --json
"""

import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
_VAULT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _VAULT_ROOT not in sys.path:
    sys.path.insert(0, _VAULT_ROOT)

from base import audited

INTEGRATION = "cluster"

# Fleet node inventory -- Tailscale IPs (stable, always reachable when node is on)
FLEET_NODES = {
    "tensor-core": {"ip": "100.121.42.54", "tier": 0, "ssh_user": "puretensorai", "role": "gpu-bridge"},
    "fox-n0":      {"ip": "100.69.225.18",  "tier": 1, "ssh_user": "root", "role": "compute"},
    "fox-n1":      {"ip": "100.103.248.9",  "tier": 1, "ssh_user": "root", "role": "k3s-master"},
    "arx1":        {"ip": "100.118.169.103", "tier": 2, "ssh_user": "root", "role": "ceph-storage"},
    "arx2":        {"ip": "100.103.169.22",  "tier": 2, "ssh_user": "root", "role": "ceph-storage"},
    "arx3":        {"ip": "100.123.131.108", "tier": 2, "ssh_user": "root", "role": "ceph-storage"},
    "arx4":        {"ip": "100.109.8.110",   "tier": 2, "ssh_user": "root", "role": "ceph-storage"},
    "mon1":        {"ip": "100.92.245.5",    "tier": 3, "ssh_user": "root", "role": "monitoring"},
    "mon2":        {"ip": "100.80.213.1",    "tier": 3, "ssh_user": "root", "role": "monitoring"},
    "mon3":        {"ip": "100.124.96.120",  "tier": 3, "ssh_user": "root", "role": "monitoring-arm64"},
}

# SSH options matching ~/power/common.sh pattern
SSH_OPTS = [
    "-o", "BatchMode=yes",
    "-o", "ConnectTimeout=3",
    "-o", "StrictHostKeyChecking=no",
    "-o", "UserKnownHostsFile=/dev/null",
    "-o", "LogLevel=ERROR",
]

# Disk alert threshold (percentage)
DEFAULT_DISK_ALERT_PCT = 80
# Load alert threshold (1-min average)
DEFAULT_LOAD_ALERT = 10.0

# Quick check SSH command -- single command, minimal overhead
QUICK_CMD = (
    "echo '===DISK==='; df -h / /mnt/* 2>/dev/null | tail -n+2; "
    "echo '===LOAD==='; cat /proc/loadavg; "
    "echo '===UPTIME==='; uptime -s 2>/dev/null || uptime"
)

# Deep check adds service status, pods, ceph
DEEP_CMD_BASE = QUICK_CMD + (
    "; echo '===SERVICES==='; "
    "systemctl is-active kubelet k3s docker containerd 2>/dev/null; "
    "echo '===FAILED==='; systemctl --failed --no-legend --no-pager 2>/dev/null | head -5"
)

DEEP_CMD_K3S = DEEP_CMD_BASE + (
    "; echo '===PODS==='; "
    "kubectl get pods -A --field-selector=status.phase!=Running --no-headers 2>/dev/null | head -10"
)

DEEP_CMD_CEPH = DEEP_CMD_BASE + (
    "; echo '===CEPH==='; ceph health 2>/dev/null; "
    "echo '===OSD==='; ceph osd stat 2>/dev/null"
)

DEEP_CMD_DOCKER = DEEP_CMD_BASE + (
    "; echo '===DOCKER==='; "
    "docker ps --format '{{.Names}} {{.Status}}' 2>/dev/null | head -15"
)


def _ping(ip: str, timeout: int = 2) -> bool:
    """Quick ICMP ping to check reachability."""
    try:
        result = subprocess.run(
            ["ping", "-c", "1", "-W", str(timeout), ip],
            capture_output=True, timeout=timeout + 1,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def _ssh_cmd(user: str, ip: str, cmd: str, timeout: int = 10) -> tuple[int, str]:
    """Run SSH command with timeout. Returns (returncode, stdout)."""
    try:
        result = subprocess.run(
            ["ssh"] + SSH_OPTS + [f"{user}@{ip}", cmd],
            capture_output=True, text=True, timeout=timeout,
        )
        return result.returncode, result.stdout
    except subprocess.TimeoutExpired:
        return -1, "SSH_TIMEOUT"
    except OSError as e:
        return -2, str(e)[:200]


def _parse_disk(output: str, alert_pct: int = DEFAULT_DISK_ALERT_PCT) -> tuple[list, list]:
    """Parse df output into disk entries and alerts. Deduplicates by mount point."""
    seen = {}
    alerts = []
    for line in output.strip().splitlines():
        parts = line.split()
        if len(parts) >= 5:
            mount = parts[-1]
            if mount in seen:
                continue
            use_str = parts[-2].rstrip("%")
            try:
                use_pct = int(use_str)
                seen[mount] = {"mount": mount, "use_pct": use_pct, "size": parts[1], "avail": parts[3]}
                if use_pct >= alert_pct:
                    alerts.append(f"disk {mount} at {use_pct}%")
            except ValueError:
                continue
    return list(seen.values()), alerts


def _parse_load(output: str) -> float | None:
    """Parse /proc/loadavg for 1-min average."""
    parts = output.strip().split()
    if parts:
        try:
            return float(parts[0])
        except ValueError:
            return None
    return None


def _check_node_quick(name: str, info: dict, alert_pct: int) -> dict:
    """Quick health check for a single node (<5s)."""
    result = {
        "name": name,
        "tier": info["tier"],
        "role": info["role"],
        "reachable": False,
        "status": "unreachable",
        "disk": [],
        "load_1m": None,
        "alerts": [],
    }

    # Ping first (fast fail for unreachable nodes)
    if not _ping(info["ip"]):
        return result

    result["reachable"] = True

    # SSH quick command
    rc, stdout = _ssh_cmd(info["ssh_user"], info["ip"], QUICK_CMD)
    if rc != 0:
        result["status"] = "ssh_failed"
        result["alerts"].append(f"SSH failed (rc={rc})")
        return result

    # Parse sections
    sections = {}
    current = None
    for line in stdout.splitlines():
        if line.startswith("===") and line.endswith("==="):
            current = line.strip("=")
            sections[current] = []
        elif current is not None:
            sections[current].append(line)

    # Disk
    disk_text = "\n".join(sections.get("DISK", []))
    result["disk"], disk_alerts = _parse_disk(disk_text, alert_pct)
    result["alerts"].extend(disk_alerts)

    # Load
    load_text = "\n".join(sections.get("LOAD", []))
    result["load_1m"] = _parse_load(load_text)
    if result["load_1m"] is not None and result["load_1m"] > DEFAULT_LOAD_ALERT:
        result["alerts"].append(f"high load: {result['load_1m']:.1f}")

    # Status
    result["status"] = "degraded" if result["alerts"] else "healthy"
    return result


def _check_node_deep(name: str, info: dict, alert_pct: int) -> dict:
    """Deep health check for a single node (up to 15s)."""
    # Start with quick check data
    result = _check_node_quick(name, info, alert_pct)
    if not result["reachable"]:
        return result

    # Choose deep command based on role
    if info["role"] == "k3s-master":
        cmd = DEEP_CMD_K3S
    elif info["role"] == "ceph-storage":
        cmd = DEEP_CMD_CEPH
    elif info["role"] in ("monitoring",):
        cmd = DEEP_CMD_DOCKER
    else:
        cmd = DEEP_CMD_BASE

    rc, stdout = _ssh_cmd(info["ssh_user"], info["ip"], cmd, timeout=15)
    if rc != 0 and rc != -1:  # ignore if already got quick data
        pass

    # Parse additional sections
    sections = {}
    current = None
    for line in stdout.splitlines():
        if line.startswith("===") and line.endswith("==="):
            current = line.strip("=")
            sections[current] = []
        elif current is not None:
            sections[current].append(line)

    result["services"] = {}
    result["extra"] = {}

    # Service status
    for line in sections.get("SERVICES", []):
        line = line.strip()
        if line in ("active", "inactive", "failed", "not-found"):
            # Services are printed in order of the systemctl command
            pass  # Individual service status hard to map without names
        elif line:
            result["services"][line] = "checked"

    # Failed units
    failed = [l.strip() for l in sections.get("FAILED", []) if l.strip()]
    if failed:
        result["extra"]["failed_units"] = failed
        result["alerts"].append(f"{len(failed)} failed systemd unit(s)")

    # K3s pods not running
    bad_pods = [l.strip() for l in sections.get("PODS", []) if l.strip()]
    if bad_pods:
        result["extra"]["non_running_pods"] = bad_pods
        result["alerts"].append(f"{len(bad_pods)} pod(s) not Running")

    # Ceph health
    ceph_lines = sections.get("CEPH", [])
    if ceph_lines:
        ceph_status = " ".join(ceph_lines).strip()
        result["extra"]["ceph_health"] = ceph_status
        if "HEALTH_OK" not in ceph_status:
            result["alerts"].append(f"Ceph: {ceph_status[:80]}")

    # OSD stats
    osd_lines = sections.get("OSD", [])
    if osd_lines:
        result["extra"]["osd_stat"] = " ".join(osd_lines).strip()

    # Docker containers
    docker_lines = [l.strip() for l in sections.get("DOCKER", []) if l.strip()]
    if docker_lines:
        result["extra"]["docker_containers"] = docker_lines

    # Recalculate status
    result["status"] = "degraded" if result["alerts"] else "healthy"
    return result


def _run_parallel(check_fn, nodes: dict, alert_pct: int) -> dict:
    """Run check_fn across all nodes in parallel."""
    results = {}
    with ThreadPoolExecutor(max_workers=len(nodes)) as pool:
        futures = {
            pool.submit(check_fn, name, info, alert_pct): name
            for name, info in nodes.items()
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                results[name] = future.result()
            except Exception as e:
                results[name] = {
                    "name": name, "reachable": False, "status": "error",
                    "alerts": [str(e)[:200]], "disk": [], "load_1m": None,
                    "tier": nodes[name]["tier"], "role": nodes[name]["role"],
                }
    return results


@audited(INTEGRATION)
def quick_check(config: dict | None = None) -> str:
    """Quick fleet health check (<30s). For heartbeat gather phase."""
    config = config or {}
    alert_pct = config.get("alert_disk_pct", DEFAULT_DISK_ALERT_PCT)
    node_filter = config.get("_node_filter")
    nodes = {node_filter: FLEET_NODES[node_filter]} if node_filter else FLEET_NODES

    start = time.monotonic()
    node_results = _run_parallel(_check_node_quick, nodes, alert_pct)
    elapsed = time.monotonic() - start

    # Aggregate
    all_alerts = []
    summary = {"total": len(nodes), "reachable": 0, "unreachable": 0, "degraded": 0, "healthy": 0}

    for name, data in sorted(node_results.items(), key=lambda x: x[1].get("tier", 99)):
        if data["reachable"]:
            summary["reachable"] += 1
        else:
            summary["unreachable"] += 1
        if data["status"] == "healthy":
            summary["healthy"] += 1
        elif data["status"] == "degraded":
            summary["degraded"] += 1
        for alert in data.get("alerts", []):
            all_alerts.append(f"{name}: {alert}")

    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "elapsed_s": round(elapsed, 1),
        "summary": summary,
        "alerts": all_alerts,
        "nodes": node_results,
    }
    return json.dumps(output)


@audited(INTEGRATION)
def deep_check(config: dict | None = None) -> str:
    """Deep fleet health check (up to 2-3 min). For /health-sweep skill."""
    config = config or {}
    alert_pct = config.get("alert_disk_pct", DEFAULT_DISK_ALERT_PCT)
    node_filter = config.get("_node_filter")
    nodes = {node_filter: FLEET_NODES[node_filter]} if node_filter else FLEET_NODES

    start = time.monotonic()
    node_results = _run_parallel(_check_node_deep, nodes, alert_pct)
    elapsed = time.monotonic() - start

    all_alerts = []
    summary = {"total": len(nodes), "reachable": 0, "unreachable": 0, "degraded": 0, "healthy": 0}

    for name, data in sorted(node_results.items(), key=lambda x: x[1].get("tier", 99)):
        if data["reachable"]:
            summary["reachable"] += 1
        else:
            summary["unreachable"] += 1
        if data["status"] == "healthy":
            summary["healthy"] += 1
        elif data["status"] == "degraded":
            summary["degraded"] += 1
        for alert in data.get("alerts", []):
            all_alerts.append(f"{name}: {alert}")

    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "elapsed_s": round(elapsed, 1),
        "summary": summary,
        "alerts": all_alerts,
        "nodes": node_results,
    }
    return json.dumps(output)


def main():
    parser = argparse.ArgumentParser(description="pureMind fleet health integration")
    parser.add_argument("command", choices=["quick_check", "deep_check"])
    parser.add_argument("--json", action="store_true", help="JSON output (default)")
    parser.add_argument("--node", help="Check single node only")

    args = parser.parse_args()

    # Load heartbeat config for thresholds
    config_file = Path(__file__).parent / "heartbeat_config.json"
    config = {}
    if config_file.exists():
        try:
            full_config = json.loads(config_file.read_text())
            config = full_config.get("fleet_health", {})
        except (json.JSONDecodeError, KeyError):
            pass

    # Filter to single node if requested
    if args.node:
        if args.node not in FLEET_NODES:
            print(json.dumps({"error": f"Unknown node: {args.node}"}))
            sys.exit(1)
        config["_node_filter"] = args.node

    try:
        if args.command == "quick_check":
            result = quick_check(config=config)
        else:
            result = deep_check(config=config)
        print(result)
    except Exception as e:
        print(json.dumps({"error": str(e)[:500]}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
