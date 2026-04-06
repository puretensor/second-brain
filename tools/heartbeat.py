#!/usr/bin/env python3
"""pureMind heartbeat -- proactive agent that gathers state, reasons, and acts.

Runs on a 30-minute systemd timer during waking hours (07:00-23:00 UTC).
Four-step loop: Gather -> Reason (Claude CLI) -> Act (within permissions) -> Notify.

Proactivity levels:
  observer: read-only, summary + alert only
  adviser:  observer + create drafts, update pending
  partner:  adviser + comment on PRs/issues, create issues

Usage:
    python3 heartbeat.py                   # Normal run (uses config level)
    python3 heartbeat.py --dry-run         # Show gathered state, don't act
    python3 heartbeat.py --level adviser   # Override proactivity level
"""

import argparse
import fcntl
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PUREMIND_ROOT = Path.home() / "pureMind"
TOOLS_DIR = PUREMIND_ROOT / "tools"

# Ensure vault root is on path for sanitize import
_VAULT_STR = str(PUREMIND_ROOT)
if _VAULT_STR not in sys.path:
    sys.path.insert(0, _VAULT_STR)
from tools.sanitize import sanitize_content
from tools.remediate import check_and_fix as remediate_fleet
INTEGRATIONS_DIR = PUREMIND_ROOT / ".claude" / "integrations"
CONFIG_FILE = INTEGRATIONS_DIR / "heartbeat_config.json"
HEARTBEAT_LOG = PUREMIND_ROOT / "daily-logs" / "heartbeat-log.jsonl"
DAILY_LOGS = PUREMIND_ROOT / "daily-logs"
MEMORY_DIR = PUREMIND_ROOT / "memory"

PROACTIVITY_LEVELS = ("observer", "adviser", "partner")

# A-01 fix: post_alert removed from Claude-proposed actions. Telegram notification
# is deterministic via notify() only. Claude should use log_only for observations.
LEVEL_ACTIONS = {
    "observer": {"log_only"},
    "adviser": {"log_only", "create_draft", "update_pending"},
    "partner": {"log_only", "create_draft", "update_pending",
                "comment_pr", "comment_issue", "create_issue"},
}

LOCK_FILE = Path("/tmp/puremind-heartbeat.lock")

HEARTBEAT_PROMPT = """\
You are the pureMind heartbeat agent for PureTensor's sovereign second brain.

## Your Task

Analyze the gathered state from all integrations and produce a JSON response.
You are operating at proactivity level: **{level}**

{level_description}

Output a JSON object with exactly these keys:

1. "priority_items": list of objects, each with:
   - "source": one of "email", "github", "calendar", "pending", "vault", "fleet"
   - "summary": one-line description of what needs attention
   - "urgency": one of "high", "medium", "low"

2. "proposed_actions": list of objects, each with:
   - "type": one of "log_only", "create_draft", "update_pending",
     "comment_pr", "comment_issue", "create_issue"
   - "params": dict with action-specific parameters
     - create_draft: {{"to": "...", "subject": "...", "body": "...", "account": "hal"}}
     - comment_pr: {{"repo": "...", "number": N, "body": "..."}}
     - comment_issue: {{"repo": "...", "number": N, "body": "..."}}
     - create_issue: {{"repo": "...", "title": "...", "body": "..."}}
     - update_pending: {{"action": "add|resolve", "item": "...", "reason": "..."}}
     - log_only: {{"note": "..."}}
   - "reason": brief explanation of why this action is proposed
   NOTE: Do NOT propose "post_alert". The operator is notified automatically.

3. "summary": 2-3 sentence briefing for the operator. Concise, numbers over narrative.

4. "attention_needed": list of strings -- items requiring the operator's direct decision.

IMPORTANT:
- Only propose actions allowed at your proactivity level.
- Never propose "post_alert" -- notifications are handled automatically.
- Never propose sending emails (only drafts).
- Never propose deleting, merging, or closing anything.
- If nothing needs attention, say so. Don't invent work.
- Output ONLY valid JSON. No markdown fencing, no commentary.

## Gathered State

### Calendar (today + upcoming)
{calendar_state}

### Email (unread)
{email_state}

### GitHub (open PRs)
{github_state}

### Telegram (recent alerts)
{telegram_state}

### Pending Items
{pending_state}

### Vault Context (deadlines/overdue)
{vault_state}

### Fleet Health (node status)
{fleet_health_state}

### Self-Healing (auto-remediation results)
{remediation_state}

### Current Date/Time
{current_time}
"""

LEVEL_DESCRIPTIONS = {
    "observer": "Observer mode: ONLY report and summarize. Do NOT propose any write actions (no drafts, no comments, no issues). Only log_only is allowed.",
    "adviser": "Adviser mode: You may propose drafts (create_draft) and pending updates (update_pending) for operator review. Do NOT propose PR/issue comments or issue creation.",
    "partner": "Partner mode: You may propose drafts, pending updates, PR/issue comments, and issue creation for routine situations. Escalate novel or ambiguous situations to attention_needed.",
}


_DEFAULT_CONFIG = {
    "proactivity_level": "observer",
    "watch": {"github_repos": [], "email_accounts": ["hal"], "calendar_accounts": ["ops"]},
    "thresholds": {"stale_pr_days": 3, "overdue_pending_days": 7, "unread_email_alert": 20},
    "schedule": {"waking_hours_utc": [7, 23]},
}


def load_config() -> dict:
    """Load and validate heartbeat configuration. E-01: safe fallback on bad config."""
    if not CONFIG_FILE.exists():
        return dict(_DEFAULT_CONFIG)
    try:
        raw = json.loads(CONFIG_FILE.read_text())
    except (json.JSONDecodeError, OSError) as e:
        print(f"WARNING: Bad config ({e}), using defaults", file=sys.stderr)
        return dict(_DEFAULT_CONFIG)
    if not isinstance(raw, dict):
        print("WARNING: Config is not a dict, using defaults", file=sys.stderr)
        return dict(_DEFAULT_CONFIG)
    # Validate proactivity level
    level = raw.get("proactivity_level", "observer")
    if level not in PROACTIVITY_LEVELS:
        print(f"WARNING: Invalid level '{level}', defaulting to observer", file=sys.stderr)
        raw["proactivity_level"] = "observer"
    # Ensure required keys exist with defaults
    for key, default in _DEFAULT_CONFIG.items():
        if key not in raw:
            raw[key] = default
    return raw


def check_waking_hours(config: dict) -> bool:
    """Return True if current time is within waking hours."""
    hours = config.get("schedule", {}).get("waking_hours_utc", [7, 23])
    current_hour = datetime.now(timezone.utc).hour
    return hours[0] <= current_hour < hours[1]


def _run_integration(args: list[str], timeout: int = 30) -> str:
    """Run an integration CLI command and return stdout."""
    try:
        result = subprocess.run(
            ["python3"] + args,
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode != 0:
            return json.dumps({"error": result.stderr[:200]})
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        return json.dumps({"error": "timeout"})
    except Exception as e:
        return json.dumps({"error": str(e)[:200]})


def gather_state(config: dict) -> dict:
    """Gather state from all integrations. Returns dict of JSON strings."""
    state = {}
    watch = config.get("watch", {})

    # A-02 fix: days=1 for today, separate call for tomorrow = "today + tomorrow"
    cal_account = (watch.get("calendar_accounts") or ["ops"])[0]
    state["calendar"] = _run_integration([
        str(INTEGRATIONS_DIR / "calendar_integration.py"),
        "list_events", "--days", "1", "--account", cal_account, "--json",
    ])

    # Email (unread)
    for account in watch.get("email_accounts", ["hal"]):
        state[f"email_{account}"] = _run_integration([
            str(INTEGRATIONS_DIR / "gmail_integration.py"),
            "list_unread", "--account", account, "--json",
        ])

    # D-01 fix: parse GitHub JSON into structured dicts, not double-encoded strings
    gh_results = {}
    for repo in watch.get("github_repos", []):
        raw = _run_integration([
            str(INTEGRATIONS_DIR / "github_integration.py"),
            "list_prs", repo, "--state", "open",
        ])
        try:
            gh_results[repo] = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            gh_results[repo] = {"raw": raw[:500]}
    state["github"] = json.dumps(gh_results)

    # Telegram (recent alerts)
    state["telegram"] = _run_integration([
        str(INTEGRATIONS_DIR / "telegram_integration.py"),
        "read_channel", "--limit", "5", "--json",
    ])

    # Pending items (direct file read)
    pending_file = MEMORY_DIR / "pending.md"
    state["pending"] = pending_file.read_text(encoding="utf-8") if pending_file.exists() else "(no pending items)"

    # Vault search for deadline/overdue context
    search_script = TOOLS_DIR / "search.py"
    if search_script.exists():
        state["vault"] = _run_integration([
            str(search_script), "pending deadline overdue follow-up",
            "--limit", "5", "--json",
        ])
    else:
        state["vault"] = "[]"

    # Fleet health (quick check via Tailscale SSH)
    fleet_health_enabled = config.get("fleet_health", {}).get("enabled", True)
    if fleet_health_enabled:
        fleet_script = INTEGRATIONS_DIR / "fleet_health_integration.py"
        if fleet_script.exists():
            state["fleet_health"] = _run_integration(
                [str(fleet_script), "quick_check", "--json"],
                timeout=35,
            )
        else:
            state["fleet_health"] = json.dumps({"error": "fleet_health_integration.py not found"})

    # Self-healing: discover remediable issues (dry-run only in gather phase)
    remediation_enabled = config.get("fleet_health", {}).get("remediation_enabled", True)
    if fleet_health_enabled and remediation_enabled:
        try:
            report = remediate_fleet(dry_run=True)
            state["remediation"] = json.dumps({
                "summary": report.get("summary", {}),
                "fixes": report.get("fixes", []),
                "escalate": report.get("escalate", []),
            })
        except Exception as e:
            state["remediation"] = json.dumps({"error": str(e)[:200]})
    else:
        state["remediation"] = json.dumps({"status": "disabled"})

    return state


def build_prompt(state: dict, level: str) -> str:
    """Build the Claude prompt with gathered state.

    All state values are sanitized before prompt injection to prevent
    indirect prompt injection from email subjects, PR titles, etc.
    """
    now = datetime.now(timezone.utc)

    # Sanitize all state values (integration outputs may contain user content)
    safe_state = {k: sanitize_content(v, max_chars=5000) for k, v in state.items()}

    # Format email state (may have multiple accounts)
    email_parts = []
    for key, val in safe_state.items():
        if key.startswith("email_"):
            account = key.replace("email_", "")
            email_parts.append(f"Account: {account}\n{val}")
    email_state = "\n\n".join(email_parts) if email_parts else "(no email data)"

    return HEARTBEAT_PROMPT.format(
        level=level,
        level_description=LEVEL_DESCRIPTIONS.get(level, LEVEL_DESCRIPTIONS["observer"]),
        calendar_state=safe_state.get("calendar", "(unavailable)"),
        email_state=email_state,
        github_state=safe_state.get("github", "(unavailable)"),
        telegram_state=safe_state.get("telegram", "(unavailable)"),
        pending_state=safe_state.get("pending", "(no pending items)"),
        vault_state=safe_state.get("vault", "(no vault context)"),
        fleet_health_state=safe_state.get("fleet_health", "(fleet health unavailable)"),
        remediation_state=safe_state.get("remediation", "(remediation not run)"),
        current_time=now.strftime("%Y-%m-%d %H:%M UTC (%A)"),
    )


def call_claude(prompt: str) -> dict | None:
    """Call Claude CLI in non-interactive mode and parse JSON response.

    Reuses the proven pattern from daily_reflect.py.
    """
    try:
        result = subprocess.run(
            ["claude", "-p", "--output-format", "json", "--max-turns", "1"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            print(f"ERROR: Claude CLI exited {result.returncode}: {result.stderr[:200]}", file=sys.stderr)
            return None

        outer = json.loads(result.stdout)
        text = outer.get("result", "")
        if not text:
            print("ERROR: Empty result from Claude CLI", file=sys.stderr)
            return None

        # Strip markdown fencing if present
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        parsed = json.loads(text)

        if not isinstance(parsed, dict):
            print("ERROR: Claude returned non-dict JSON", file=sys.stderr)
            return None

        # Validate and default missing keys
        for key in ("priority_items", "proposed_actions", "attention_needed"):
            if key not in parsed or not isinstance(parsed[key], list):
                parsed[key] = []
        if "summary" not in parsed:
            parsed["summary"] = "No summary provided"

        return parsed

    except FileNotFoundError:
        print("ERROR: Claude CLI not found", file=sys.stderr)
        return None
    except subprocess.TimeoutExpired:
        print("ERROR: Claude CLI timed out after 120s", file=sys.stderr)
        return None
    except json.JSONDecodeError as e:
        print(f"ERROR: Failed to parse Claude response: {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"ERROR: Claude CLI call failed: {e}", file=sys.stderr)
        return None


def _validate_action(action: dict) -> str | None:
    """C-01: Deep schema validation for a single proposed action.

    Returns an error string if invalid, None if valid.
    """
    if not isinstance(action, dict):
        return "action is not a dict"
    atype = action.get("type")
    if not isinstance(atype, str):
        return "missing or non-string 'type'"
    all_types = {"log_only", "create_draft", "update_pending",
                 "comment_pr", "comment_issue", "create_issue"}
    if atype not in all_types:
        return f"unknown action type '{atype}'"
    params = action.get("params")
    if not isinstance(params, dict):
        return "missing or non-dict 'params'"
    # Type-specific param validation
    if atype == "create_draft":
        for req in ("to", "subject", "body"):
            if not isinstance(params.get(req), str) or not params[req].strip():
                return f"create_draft missing required param '{req}'"
    elif atype in ("comment_pr", "comment_issue"):
        if not isinstance(params.get("repo"), str) or not params["repo"].strip():
            return f"{atype} missing 'repo'"
        if not isinstance(params.get("number"), (int, float)) or params["number"] <= 0:
            return f"{atype} missing or invalid 'number'"
        if not isinstance(params.get("body"), str) or not params["body"].strip():
            return f"{atype} missing 'body'"
    elif atype == "create_issue":
        if not isinstance(params.get("repo"), str) or not params["repo"].strip():
            return "create_issue missing 'repo'"
        if not isinstance(params.get("title"), str) or not params["title"].strip():
            return "create_issue missing 'title'"
    elif atype == "update_pending":
        if params.get("action") not in ("add", "resolve"):
            return "update_pending 'action' must be 'add' or 'resolve'"
        if not isinstance(params.get("item"), str) or not params["item"].strip():
            return "update_pending missing 'item'"
    return None


def _scope_check_action(action: dict, config: dict) -> str | None:
    """B-01: Target-scoped filtering. Verify action targets are within config allowlists.

    Returns an error string if out of scope, None if allowed.
    """
    atype = action["type"]
    params = action["params"]
    watch = config.get("watch", {})

    if atype == "create_draft":
        # Account must be in watched email accounts
        account = params.get("account", "hal")
        allowed_accounts = watch.get("email_accounts", ["hal"])
        if account not in allowed_accounts:
            return f"email account '{account}' not in watch list"

    elif atype in ("comment_pr", "comment_issue", "create_issue"):
        repo = params.get("repo", "")
        allowed_repos = watch.get("github_repos", [])
        if repo not in allowed_repos:
            return f"repo '{repo}' not in watch list"

    return None


def filter_actions(proposed: list[dict], level: str,
                   config: dict) -> tuple[list[dict], list[dict]]:
    """Filter proposed actions by proactivity level + target scope + schema validation.

    Returns (allowed, rejected) tuples. Each rejected item gets a 'reject_reason'.
    """
    allowed_types = LEVEL_ACTIONS.get(level, LEVEL_ACTIONS["observer"])
    allowed = []
    rejected = []
    for action in proposed:
        # C-01: schema validation
        schema_err = _validate_action(action)
        if schema_err:
            action["reject_reason"] = f"schema: {schema_err}"
            rejected.append(action)
            continue
        # Level check
        if action.get("type") not in allowed_types:
            action["reject_reason"] = f"level: {action.get('type')} not allowed at {level}"
            rejected.append(action)
            continue
        # B-01: target scope check
        scope_err = _scope_check_action(action, config)
        if scope_err:
            action["reject_reason"] = f"scope: {scope_err}"
            rejected.append(action)
            continue
        allowed.append(action)
    return allowed, rejected


def _check_integration_result(output: str) -> tuple[bool, str]:
    """H-01: Check if _run_integration output indicates success or error."""
    try:
        parsed = json.loads(output)
        if isinstance(parsed, dict) and "error" in parsed:
            return False, parsed["error"]
    except (json.JSONDecodeError, TypeError):
        pass
    # Check for common error patterns in text output
    if output.startswith("ERROR") or output.startswith("DENIED"):
        return False, output[:200]
    return True, output


def execute_actions(actions: list[dict]) -> list[dict]:
    """Execute allowed actions via integration CLIs. Returns results.

    H-01: success depends on actual subprocess result, not just no-exception.
    H-02: update_pending reuses daily_reflect.py's apply_pending_changes pattern.
    """
    results = []
    for action in actions:
        action_type = action.get("type", "")
        params = action.get("params", {})
        result = {"type": action_type, "status": "skipped", "detail": ""}

        try:
            if action_type == "log_only":
                result["status"] = "ok"
                result["detail"] = params.get("note", "")

            elif action_type == "create_draft":
                cmd = [
                    str(INTEGRATIONS_DIR / "gmail_integration.py"),
                    "create_draft",
                    "--to", params.get("to", ""),
                    "--subject", params.get("subject", ""),
                    "--body", params.get("body", ""),
                    "--account", params.get("account", "hal"),
                ]
                cc = params.get("cc", "")
                if cc:
                    cmd.extend(["--cc", cc])
                output = _run_integration(cmd)
                ok, detail = _check_integration_result(output)
                result["status"] = "ok" if ok else "error"
                result["detail"] = detail

            elif action_type in ("comment_pr", "comment_issue"):
                output = _run_integration([
                    str(INTEGRATIONS_DIR / "github_integration.py"),
                    action_type,
                    params.get("repo", ""),
                    str(int(params.get("number", 0))),
                    "--body", params.get("body", ""),
                ])
                ok, detail = _check_integration_result(output)
                result["status"] = "ok" if ok else "error"
                result["detail"] = detail

            elif action_type == "create_issue":
                cmd = [
                    str(INTEGRATIONS_DIR / "github_integration.py"),
                    "create_issue",
                    params.get("repo", ""),
                    "--title", params.get("title", ""),
                ]
                if params.get("body"):
                    cmd.extend(["--body", params["body"]])
                output = _run_integration(cmd)
                ok, detail = _check_integration_result(output)
                result["status"] = "ok" if ok else "error"
                result["detail"] = detail

            elif action_type == "update_pending":
                # H-02: reuse daily_reflect.py's apply_pending_changes pattern
                pending_file = MEMORY_DIR / "pending.md"
                if not pending_file.exists():
                    result["status"] = "error"
                    result["detail"] = "pending.md not found"
                else:
                    content = pending_file.read_text(encoding="utf-8")
                    item = params.get("item", "")
                    reason = params.get("reason", "heartbeat")
                    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

                    if params.get("action") == "add":
                        lines = content.splitlines()
                        inserted = False
                        for i, line in enumerate(lines):
                            if line.strip() == "## Active":
                                insert_at = i + 1
                                while insert_at < len(lines) and not lines[insert_at].strip():
                                    insert_at += 1
                                bullet = item if item.startswith("- ") else f"- **{item}**"
                                lines.insert(insert_at, bullet)
                                inserted = True
                                break
                        if inserted:
                            pending_file.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
                            result["status"] = "ok"
                            result["detail"] = f"Added: {item}"
                        else:
                            result["status"] = "error"
                            result["detail"] = "No ## Active section found"

                    elif params.get("action") == "resolve":
                        lines = content.splitlines()
                        resolved = False
                        for i, line in enumerate(lines):
                            if line.strip().startswith(item.strip()):
                                resolved_line = f"{line.strip()} *(resolved {today}: {reason})*"
                                lines.pop(i)
                                for j, l in enumerate(lines):
                                    if l.strip() == "## Resolved":
                                        lines.insert(j + 1, resolved_line)
                                        resolved = True
                                        break
                                if not resolved:
                                    lines.append("## Resolved")
                                    lines.append(resolved_line)
                                    resolved = True
                                break
                        if resolved:
                            pending_file.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
                            result["status"] = "ok"
                            result["detail"] = f"Resolved: {item}"
                        else:
                            result["status"] = "error"
                            result["detail"] = f"No matching item for resolve: {item}"

        except Exception as e:
            result["status"] = "error"
            result["detail"] = str(e)[:200]

        results.append(result)
    return results


def notify(summary: str, attention: list[str], action_results: list[dict],
           level: str, remediation_summary: dict | None = None,
           dry_run: bool = False) -> str:
    """Post structured summary to Telegram."""
    parts = [f"Heartbeat ({level}):", summary]

    # Self-healing results
    if remediation_summary:
        fixed = remediation_summary.get("fixed", 0)
        escalate = remediation_summary.get("escalate", 0)
        if fixed > 0 or escalate > 0:
            parts.append(f"\nSelf-healing: {fixed} fixed, {escalate} need human")

    if attention:
        parts.append(f"\nNeeds attention ({len(attention)}):")
        for item in attention[:5]:
            parts.append(f"  - {item}")

    actions_taken = [r for r in action_results if r["status"] == "ok" and r["type"] != "log_only"]
    if actions_taken:
        parts.append(f"\nActions taken: {len(actions_taken)}")
        for r in actions_taken[:3]:
            parts.append(f"  - {r['type']}: {r['detail'][:80]}")

    message = "\n".join(parts)

    if dry_run:
        return message, True

    try:
        _run_integration([
            str(INTEGRATIONS_DIR / "telegram_integration.py"),
            "post_alert", message[:4000],  # Telegram message limit
        ])
        return message, True
    except Exception as e:
        print(f"WARNING: Telegram notification failed: {e}", file=sys.stderr)
        return message, False


def log_results(state_summary: dict, response: dict, action_results: list[dict],
                rejected_actions: list[dict], notify_ok: bool,
                level: str, dry_run: bool):
    """Write to heartbeat-log.jsonl and append to daily log.

    G-01: logs rejected actions, notify outcome, and structured action outcomes.
    G-02: daily log entry uses ## Session schema for chunker/reflection compatibility.
    """
    now = datetime.now(timezone.utc)

    # G-01: expanded JSONL entry
    ok_actions = [r for r in action_results if r["status"] == "ok" and r["type"] != "log_only"]
    failed_actions = [r for r in action_results if r["status"] == "error"]
    entry = {
        "timestamp": now.isoformat(),
        "level": level,
        "dry_run": dry_run,
        "priority_items": len(response.get("priority_items", [])),
        "actions_proposed": len(response.get("proposed_actions", [])),
        "actions_allowed": len(action_results),
        "actions_rejected": len(rejected_actions),
        "actions_succeeded": len(ok_actions),
        "actions_failed": len(failed_actions),
        "notify_ok": notify_ok,
        "attention_needed": len(response.get("attention_needed", [])),
        "summary": response.get("summary", ""),
        "action_details": [{"type": r["type"], "status": r["status"],
                            "detail": r["detail"][:100]} for r in action_results],
        "reject_reasons": [a.get("reject_reason", "") for a in rejected_actions[:5]],
    }

    if not dry_run:
        # JSONL log
        try:
            with open(HEARTBEAT_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception:
            pass

        # G-02: daily log entry in ## Session schema
        today = now.strftime("%Y-%m-%d")
        log_path = DAILY_LOGS / f"{today}.md"
        hb_entry = (
            f"\n## Heartbeat: {now.strftime('%H:%M')} ({level})\n"
            f"**Context:** Automated heartbeat -- gather/reason/act/notify\n\n"
            f"### Summary\n"
            f"- {response.get('summary', 'No summary')}\n"
        )
        attention = response.get("attention_needed", [])
        if attention:
            hb_entry += f"- Attention needed: {', '.join(attention[:3])}\n"
        if ok_actions:
            hb_entry += f"\n### Actions\n"
            for r in ok_actions:
                hb_entry += f"- [{r['type']}] {r['detail'][:80]}\n"
        if failed_actions:
            hb_entry += f"\n### Errors\n"
            for r in failed_actions:
                hb_entry += f"- [{r['type']}] FAILED: {r['detail'][:80]}\n"
        if rejected_actions:
            hb_entry += f"\n*{len(rejected_actions)} proposed actions filtered*\n"

        try:
            if log_path.exists():
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(hb_entry)
            else:
                log_path.write_text(f"# {today}\n{hb_entry}", encoding="utf-8")
        except Exception:
            pass


def git_commit(message: str):
    """Stage heartbeat-owned files and commit."""
    try:
        subprocess.run(
            ["git", "-C", str(PUREMIND_ROOT), "add",
             "daily-logs/heartbeat-log.jsonl", "memory/pending.md"],
            capture_output=True, timeout=10,
        )
        # Also stage today's daily log
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        subprocess.run(
            ["git", "-C", str(PUREMIND_ROOT), "add",
             f"daily-logs/{today}.md"],
            capture_output=True, timeout=10,
        )
        diff = subprocess.run(
            ["git", "-C", str(PUREMIND_ROOT), "diff", "--cached", "--quiet"],
            capture_output=True, timeout=10,
        )
        if diff.returncode != 0:
            subprocess.run(
                ["git", "-C", str(PUREMIND_ROOT), "commit", "-m", message],
                capture_output=True, timeout=10,
            )
            # Auto-push to Gitea (private, high-frequency heartbeat commits).
            # GitHub stays manual-push only (public repo, curated history).
            subprocess.run(
                ["git", "-C", str(PUREMIND_ROOT), "push", "gitea", "main"],
                capture_output=True, timeout=30,
            )
    except Exception as e:
        print(f"WARNING: Git commit failed: {e}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="pureMind heartbeat agent")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show gathered state and proposed actions without executing")
    parser.add_argument("--level", choices=PROACTIVITY_LEVELS,
                        help="Override proactivity level from config")
    parser.add_argument("--force", action="store_true",
                        help="Run even outside waking hours")

    args = parser.parse_args()

    # F-01: single-flight lock prevents concurrent runs (timer + manual overlap)
    if not args.dry_run:
        try:
            lock_fd = open(LOCK_FILE, "w")
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (IOError, OSError):
            print("Another heartbeat is already running. Exiting.")
            sys.exit(0)

    config = load_config()
    level = args.level or config.get("proactivity_level", "observer")

    # Waking hours check
    if not args.force and not args.dry_run and not check_waking_hours(config):
        print("Outside waking hours. Use --force to override.")
        sys.exit(0)

    now = datetime.now(timezone.utc)
    print(f"=== pureMind Heartbeat {'(DRY RUN) ' if args.dry_run else ''}-- {now.strftime('%Y-%m-%d %H:%M UTC')} ===")
    print(f"Proactivity level: {level}\n")

    # 1. GATHER (includes fleet health + auto-remediation)
    print("Gathering state...")
    state = gather_state(config)

    if args.dry_run:
        print("\n--- Gathered State ---")
        for key, val in state.items():
            print(f"\n[{key}]")
            try:
                parsed = json.loads(val)
                print(json.dumps(parsed, indent=2)[:500])
            except (json.JSONDecodeError, TypeError):
                print(str(val)[:500])
        print("\n--- End Gathered State ---")
        print("\nDry run complete. No Claude call, no actions.")
        sys.exit(0)

    # 2. REASON
    print("Reasoning via Claude...")
    prompt = build_prompt(state, level)
    response = call_claude(prompt)

    if not response:
        # Fallback: post error alert
        try:
            _run_integration([
                str(INTEGRATIONS_DIR / "telegram_integration.py"),
                "post_alert", "Heartbeat: Claude reasoning failed. Check logs.",
            ])
        except Exception:
            pass
        print("ERROR: Claude reasoning failed. Exiting.", file=sys.stderr)
        sys.exit(1)

    print(f"Summary: {response.get('summary', 'N/A')}")
    print(f"Priority items: {len(response.get('priority_items', []))}")
    print(f"Proposed actions: {len(response.get('proposed_actions', []))}")
    print(f"Attention needed: {len(response.get('attention_needed', []))}")

    # 2.5. AUTO-REMEDIATE (deterministic, no LLM -- runs in act phase, not gather)
    remediation_summary = None
    rem_enabled = config.get("fleet_health", {}).get("remediation_enabled", True)
    fh_enabled = config.get("fleet_health", {}).get("enabled", True)
    if fh_enabled and rem_enabled:
        try:
            print("Running self-healing remediation...")
            rem_report = remediate_fleet(dry_run=False)
            remediation_summary = rem_report.get("summary")
            fixed = (remediation_summary or {}).get("fixed", 0)
            escalate = (remediation_summary or {}).get("escalate", 0)
            if fixed > 0 or escalate > 0:
                print(f"Self-healing: {fixed} fixed, {escalate} escalated")
        except Exception as e:
            print(f"WARNING: Remediation failed: {e}", file=sys.stderr)

    # 3. ACT
    allowed, rejected = filter_actions(
        response.get("proposed_actions", []), level, config)
    if rejected:
        print(f"Filtered {len(rejected)} actions:")
        for r in rejected:
            print(f"  - {r.get('type', '?')}: {r.get('reject_reason', 'unknown')}")

    action_results = []
    if allowed:
        print(f"\nExecuting {len(allowed)} actions...")
        action_results = execute_actions(allowed)
        for r in action_results:
            status = "OK" if r["status"] == "ok" else "FAIL"
            print(f"  [{status}] {r['type']}: {r['detail'][:80]}")

    # 4. NOTIFY + LOG
    # A-01: single deterministic Telegram notification (not Claude-proposed)
    notification, notify_ok = notify(
        summary=response.get("summary", ""),
        attention=response.get("attention_needed", []),
        action_results=action_results,
        level=level,
        remediation_summary=remediation_summary,
    )
    if notify_ok:
        print(f"\nNotification posted to Telegram")
    else:
        print(f"\nWARNING: Telegram notification may have failed")

    log_results(
        state_summary={"keys": list(state.keys())},
        response=response,
        action_results=action_results,
        rejected_actions=rejected,
        notify_ok=notify_ok,
        level=level,
        dry_run=False,
    )

    git_commit(f"heartbeat: {now.strftime('%Y-%m-%d %H:%M')} ({level})")

    ok_count = len([r for r in action_results if r["status"] == "ok" and r["type"] != "log_only"])
    fail_count = len([r for r in action_results if r["status"] == "error"])
    print(f"\nHeartbeat complete. {ok_count} actions succeeded, {fail_count} failed, "
          f"{len(rejected)} filtered, {len(response.get('attention_needed', []))} items need attention.")


if __name__ == "__main__":
    main()
