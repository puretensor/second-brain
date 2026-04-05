You are reviewing Phase 6 (Heartbeat & Proactive Agent) of pureMind, a sovereign second brain system. This phase adds a proactive agent that runs on a 30-minute cron, gathers state from all integrations, reasons via Claude CLI (single-turn), executes bounded actions, and notifies the operator.

Score each area 1-10 and provide specific, actionable findings. For each finding, classify severity as Critical (C), Important (I), or Nice-to-have (N). Use IDs like A-01, B-02, etc.

## Evaluation Areas

A. Heartbeat Orchestration (heartbeat.py architecture, gather/reason/act/notify loop, error handling)
B. Security & Permission Enforcement (proactivity level filtering, action boundary compliance, no privilege escalation)
C. Claude CLI Integration (prompt engineering, JSON parsing robustness, timeout handling, fallback behavior)
D. JSON Output Parsers (gmail _parse_gmail_text, calendar _parse_calendar_text, telegram --json, github --json passthrough)
E. Configuration & Defaults (heartbeat_config.json schema, safe defaults, missing config handling)
F. Systemd Integration (timer/service correctness, waking hours enforcement, failure modes)
G. Logging & Observability (heartbeat-log.jsonl, daily log entries, audit trail completeness)
H. Action Execution (execute_actions dispatch, create_draft/comment_pr/create_issue/update_pending correctness)
I. Skill & Documentation Quality (heartbeat.md skill, CLAUDE.md Phase 6 section, README accuracy)
J. Edge Cases & Resilience (network failures, empty state, malformed Claude output, concurrent timer runs)

## Files Under Review

### tools/heartbeat.py (NEW -- ~600 lines, main Phase 6 deliverable)
```python
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
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PUREMIND_ROOT = Path.home() / "pureMind"
TOOLS_DIR = PUREMIND_ROOT / "tools"
INTEGRATIONS_DIR = PUREMIND_ROOT / ".claude" / "integrations"
CONFIG_FILE = INTEGRATIONS_DIR / "heartbeat_config.json"
HEARTBEAT_LOG = PUREMIND_ROOT / "daily-logs" / "heartbeat-log.jsonl"
DAILY_LOGS = PUREMIND_ROOT / "daily-logs"
MEMORY_DIR = PUREMIND_ROOT / "memory"

PROACTIVITY_LEVELS = ("observer", "adviser", "partner")

# Actions allowed at each proactivity level
LEVEL_ACTIONS = {
    "observer": {"log_only", "post_alert"},
    "adviser": {"log_only", "post_alert", "create_draft", "update_pending"},
    "partner": {"log_only", "post_alert", "create_draft", "update_pending",
                "comment_pr", "comment_issue", "create_issue"},
}

HEARTBEAT_PROMPT = """\
You are the pureMind heartbeat agent for PureTensor's sovereign second brain.

## Your Task

Analyze the gathered state from all integrations and produce a JSON response.
You are operating at proactivity level: **{level}**

{level_description}

Output a JSON object with exactly these keys:

1. "priority_items": list of objects, each with:
   - "source": one of "email", "github", "calendar", "pending", "vault"
   - "summary": one-line description of what needs attention
   - "urgency": one of "high", "medium", "low"

2. "proposed_actions": list of objects, each with:
   - "type": one of "log_only", "post_alert", "create_draft", "update_pending",
     "comment_pr", "comment_issue", "create_issue"
   - "params": dict with action-specific parameters
     - create_draft: {{"to": "...", "subject": "...", "body": "...", "account": "hal"}}
     - comment_pr: {{"repo": "...", "number": N, "body": "..."}}
     - comment_issue: {{"repo": "...", "number": N, "body": "..."}}
     - create_issue: {{"repo": "...", "title": "...", "body": "..."}}
     - update_pending: {{"action": "add|resolve", "item": "...", "reason": "..."}}
     - post_alert: {{"message": "..."}}
     - log_only: {{"note": "..."}}
   - "reason": brief explanation of why this action is proposed

3. "summary": 2-3 sentence briefing for the operator. Concise, numbers over narrative.

4. "attention_needed": list of strings -- items requiring the operator's direct decision.

IMPORTANT:
- Only propose actions allowed at your proactivity level.
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

### Current Date/Time
{current_time}
"""

LEVEL_DESCRIPTIONS = {
    "observer": "Observer mode: ONLY report and summarize. Do NOT propose any write actions (no drafts, no comments, no issues). Only log_only and post_alert are allowed.",
    "adviser": "Adviser mode: You may propose drafts and pending updates for operator review. Do NOT propose PR/issue comments or issue creation.",
    "partner": "Partner mode: You may propose drafts, pending updates, PR/issue comments, and issue creation for routine situations. Escalate novel or ambiguous situations to attention_needed.",
}


def load_config() -> dict:
    """Load heartbeat configuration."""
    if not CONFIG_FILE.exists():
        return {
            "proactivity_level": "observer",
            "watch": {"github_repos": [], "email_accounts": ["hal"], "calendar_accounts": ["ops"]},
            "thresholds": {"stale_pr_days": 3, "overdue_pending_days": 7, "unread_email_alert": 20},
            "schedule": {"waking_hours_utc": [7, 23]},
        }
    return json.loads(CONFIG_FILE.read_text())


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

    # Calendar
    cal_account = (watch.get("calendar_accounts") or ["ops"])[0]
    state["calendar"] = _run_integration([
        str(INTEGRATIONS_DIR / "calendar_integration.py"),
        "list_events", "--days", "2", "--account", cal_account, "--json",
    ])

    # Email (unread)
    for account in watch.get("email_accounts", ["hal"]):
        state[f"email_{account}"] = _run_integration([
            str(INTEGRATIONS_DIR / "gmail_integration.py"),
            "list_unread", "--account", account, "--json",
        ])

    # GitHub (open PRs across watched repos)
    gh_results = {}
    for repo in watch.get("github_repos", []):
        gh_results[repo] = _run_integration([
            str(INTEGRATIONS_DIR / "github_integration.py"),
            "list_prs", repo, "--state", "open",
        ])
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

    return state


def build_prompt(state: dict, level: str) -> str:
    """Build the Claude prompt with gathered state."""
    now = datetime.now(timezone.utc)

    # Format email state (may have multiple accounts)
    email_parts = []
    for key, val in state.items():
        if key.startswith("email_"):
            account = key.replace("email_", "")
            email_parts.append(f"Account: {account}\n{val}")
    email_state = "\n\n".join(email_parts) if email_parts else "(no email data)"

    return HEARTBEAT_PROMPT.format(
        level=level,
        level_description=LEVEL_DESCRIPTIONS.get(level, LEVEL_DESCRIPTIONS["observer"]),
        calendar_state=state.get("calendar", "(unavailable)"),
        email_state=email_state,
        github_state=state.get("github", "(unavailable)"),
        telegram_state=state.get("telegram", "(unavailable)"),
        pending_state=state.get("pending", "(no pending items)"),
        vault_state=state.get("vault", "(no vault context)"),
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


def filter_actions(proposed: list[dict], level: str) -> tuple[list[dict], list[dict]]:
    """Filter proposed actions by proactivity level.

    Returns (allowed, rejected) tuples.
    """
    allowed_types = LEVEL_ACTIONS.get(level, LEVEL_ACTIONS["observer"])
    allowed = []
    rejected = []
    for action in proposed:
        if action.get("type") in allowed_types:
            allowed.append(action)
        else:
            rejected.append(action)
    return allowed, rejected


def execute_actions(actions: list[dict]) -> list[dict]:
    """Execute allowed actions via integration CLIs. Returns results."""
    results = []
    for action in actions:
        action_type = action.get("type", "")
        params = action.get("params", {})
        result = {"type": action_type, "status": "skipped", "detail": ""}

        try:
            if action_type == "log_only":
                result["status"] = "ok"
                result["detail"] = params.get("note", "")

            elif action_type == "post_alert":
                msg = params.get("message", action.get("reason", "heartbeat alert"))
                output = _run_integration([
                    str(INTEGRATIONS_DIR / "telegram_integration.py"),
                    "post_alert", msg,
                ])
                result["status"] = "ok"
                result["detail"] = output

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
                result["status"] = "ok"
                result["detail"] = output

            elif action_type in ("comment_pr", "comment_issue"):
                cmd_name = action_type.replace("_", " ").replace("comment ", "comment_")
                output = _run_integration([
                    str(INTEGRATIONS_DIR / "github_integration.py"),
                    action_type,
                    params.get("repo", ""),
                    str(params.get("number", 0)),
                    "--body", params.get("body", ""),
                ])
                result["status"] = "ok"
                result["detail"] = output

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
                result["status"] = "ok"
                result["detail"] = output

            elif action_type == "update_pending":
                # Direct file modification follows daily_reflect.py pattern
                pending_file = MEMORY_DIR / "pending.md"
                if pending_file.exists():
                    content = pending_file.read_text(encoding="utf-8")
                    if params.get("action") == "add":
                        item = params.get("item", "")
                        bullet = item if item.startswith("- ") else f"- **{item}**"
                        # Insert after ## Active header
                        if "## Active" in content:
                            content = content.replace("## Active\n", f"## Active\n{bullet}\n", 1)
                        else:
                            content += f"\n## Active\n{bullet}\n"
                        pending_file.write_text(content, encoding="utf-8")
                        result["status"] = "ok"
                        result["detail"] = f"Added: {item}"
                    elif params.get("action") == "resolve":
                        # Mark item as resolved -- simplified, no move
                        item = params.get("item", "")
                        result["status"] = "ok"
                        result["detail"] = f"Resolve proposed: {item} (manual review needed)"

        except Exception as e:
            result["status"] = "error"
            result["detail"] = str(e)[:200]

        results.append(result)
    return results


def notify(summary: str, attention: list[str], action_results: list[dict],
           level: str, dry_run: bool = False) -> str:
    """Post structured summary to Telegram."""
    parts = [f"Heartbeat ({level}):", summary]

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
        return message

    try:
        _run_integration([
            str(INTEGRATIONS_DIR / "telegram_integration.py"),
            "post_alert", message[:4000],  # Telegram message limit
        ])
    except Exception as e:
        print(f"WARNING: Telegram notification failed: {e}", file=sys.stderr)

    return message


def log_results(state_summary: dict, response: dict, action_results: list[dict],
                level: str, dry_run: bool):
    """Write to heartbeat-log.jsonl and append to daily log."""
    now = datetime.now(timezone.utc)
    entry = {
        "timestamp": now.isoformat(),
        "level": level,
        "dry_run": dry_run,
        "priority_items": len(response.get("priority_items", [])),
        "actions_proposed": len(response.get("proposed_actions", [])),
        "actions_executed": len([r for r in action_results if r["status"] == "ok"]),
        "attention_needed": len(response.get("attention_needed", [])),
        "summary": response.get("summary", ""),
    }

    if not dry_run:
        # JSONL log
        try:
            with open(HEARTBEAT_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception:
            pass

        # Append to daily log
        today = now.strftime("%Y-%m-%d")
        log_path = DAILY_LOGS / f"{today}.md"
        hb_entry = (
            f"\n### Heartbeat [{now.strftime('%H:%M')}] ({level})\n"
            f"- {response.get('summary', 'No summary')}\n"
        )
        attention = response.get("attention_needed", [])
        if attention:
            hb_entry += f"- Attention needed: {', '.join(attention[:3])}\n"
        actions = [r for r in action_results if r["status"] == "ok" and r["type"] != "log_only"]
        if actions:
            hb_entry += f"- Actions: {', '.join(r['type'] for r in actions)}\n"

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

    config = load_config()
    level = args.level or config.get("proactivity_level", "observer")

    # Waking hours check
    if not args.force and not args.dry_run and not check_waking_hours(config):
        print("Outside waking hours. Use --force to override.")
        sys.exit(0)

    now = datetime.now(timezone.utc)
    print(f"=== pureMind Heartbeat {'(DRY RUN) ' if args.dry_run else ''}-- {now.strftime('%Y-%m-%d %H:%M UTC')} ===")
    print(f"Proactivity level: {level}\n")

    # 1. GATHER
    print("Gathering state...")
    state = gather_state(config)

    if args.dry_run:
        print("\n--- Gathered State ---")
        for key, val in state.items():
            print(f"\n[{key}]")
            # Pretty-print JSON, truncate long values
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

    # 3. ACT
    allowed, rejected = filter_actions(response.get("proposed_actions", []), level)
    if rejected:
        print(f"Filtered {len(rejected)} actions above {level} level")

    action_results = []
    if allowed:
        print(f"\nExecuting {len(allowed)} actions...")
        action_results = execute_actions(allowed)
        for r in action_results:
            status = "OK" if r["status"] == "ok" else "FAIL"
            print(f"  [{status}] {r['type']}: {r['detail'][:80]}")

    # 4. NOTIFY + LOG
    notification = notify(
        summary=response.get("summary", ""),
        attention=response.get("attention_needed", []),
        action_results=action_results,
        level=level,
    )
    print(f"\nNotification posted to Telegram")

    log_results(
        state_summary={"keys": list(state.keys())},
        response=response,
        action_results=action_results,
        level=level,
        dry_run=False,
    )

    git_commit(f"heartbeat: {now.strftime('%Y-%m-%d %H:%M')} ({level})")

    print(f"\nHeartbeat complete. {len(allowed)} actions executed, {len(response.get('attention_needed', []))} items need attention.")


if __name__ == "__main__":
    main()
```

### .claude/integrations/gmail_integration.py (MODIFIED -- added --json output parser)

Key changes:
- Added `_parse_gmail_text(text)` -- parses gmail.py fixed-width table (columns: ID 0-18, Date 19-37, From 38-68, Subject 69+) into `{"count": N, "messages": [{"id", "date", "from", "subject", "unread"}]}`
- Added `--json` CLI flag; list_unread/list_inbox/search output JSON when set
- A-01 fix (Phase 5): `create_draft()` enforces CC ops@puretensor.ai for hal account in code

```python
def _parse_gmail_text(text: str) -> dict:
    if "No messages found" in text or not text.strip():
        return {"count": 0, "messages": []}

    messages = []
    for line in text.strip().splitlines():
        if line.startswith("ID") or line.startswith("---") or not line.strip():
            continue
        if line.strip().startswith("(") or line.strip().startswith("Showing"):
            continue
        if len(line) >= 40:
            msg_id = line[0:18].strip()
            if not msg_id or not re.match(r'^[0-9a-f]+$', msg_id):
                continue
            msg = {
                "id": msg_id,
                "date": line[19:37].strip(),
                "from": line[38:68].strip(),
                "subject": line[69:].strip() if len(line) > 69 else "",
                "unread": line.rstrip().endswith("*"),
            }
            messages.append(msg)

    return {"count": len(messages), "messages": messages}
```

### .claude/integrations/calendar_integration.py (MODIFIED -- added --json output parser)

Key changes:
- Added `_parse_calendar_text(text)` -- parses gcalendar.py fixed-width table (columns: Time 0-45, Summary 46-94, ID 95+) into `{"events": [{"time", "summary", "id"}]}`
- Added `--json` CLI flag for list_events and search
- Skips token refresh output lines and section headers

```python
def _parse_calendar_text(text: str) -> dict:
    if not text.strip():
        return {"events": []}

    events = []
    in_table = False
    for line in text.strip().splitlines():
        if line.startswith("Refreshing") or line.startswith("Token saved"):
            continue
        if line.strip().startswith("Time") or line.startswith("---"):
            in_table = True
            continue
        if line.strip().startswith("Showing") or not line.strip():
            continue
        if line.strip().startswith("Today") or line.strip().startswith("Upcoming"):
            continue
        if not in_table:
            continue
        if len(line) >= 50:
            event = {
                "time": line[0:46].strip(),
                "summary": line[46:95].strip() if len(line) > 46 else "",
                "id": line[95:].strip() if len(line) > 95 else "",
            }
            if event["time"] or event["summary"]:
                events.append(event)

    return {"events": events}
```

### .claude/integrations/telegram_integration.py (MODIFIED -- added --json for read_channel)

Key change: `read_channel --json` returns raw Telegram Bot API updates filtered to ALERTS_CHAT_ID as `{"messages": [{"text", "date"}]}`. Bypasses the @audited text formatting.

```python
elif args.command == "read_channel":
    if args.json:
        result = _tg_api("getUpdates", {"limit": min(args.limit * 2, 50), "timeout": 1})
        updates = result.get("result", [])
        msgs = []
        for u in updates:
            msg = u.get("message") or u.get("channel_post", {})
            chat_id = str(msg.get("chat", {}).get("id", ""))
            if chat_id != str(ALERTS_CHAT_ID):
                continue
            msgs.append({"text": msg.get("text", ""), "date": msg.get("date", 0)})
        print(json.dumps({"messages": msgs[-args.limit:]}))
    else:
        print(read_channel(limit=args.limit))
```

### .claude/integrations/github_integration.py (MODIFIED -- added --json passthrough)

Minimal change: added `--json` CLI flag. GitHub output is already JSON from `gh --json`. The flag exists for CLI consistency but doesn't change behavior.

### .claude/integrations/heartbeat_config.json (NEW)

```json
{
  "proactivity_level": "observer",
  "schedule": {
    "interval_minutes": 30,
    "waking_hours_utc": [7, 23]
  },
  "watch": {
    "github_repos": ["PureClaw", "second-brain", "tensor-scripts", "macrophage"],
    "email_accounts": ["hal"],
    "calendar_accounts": ["ops"]
  },
  "thresholds": {
    "stale_pr_days": 3,
    "overdue_pending_days": 7,
    "unread_email_alert": 20
  }
}
```

### Systemd files (NEW)

puremind-heartbeat.service:
```ini
[Unit]
Description=pureMind heartbeat -- proactive agent gather/reason/act loop
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=puretensorai
Environment=HOME=/home/puretensorai
Environment=PATH=/home/puretensorai/.local/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=/usr/bin/python3 /home/puretensorai/pureMind/tools/heartbeat.py
TimeoutStartSec=120
```

puremind-heartbeat.timer:
```ini
[Unit]
Description=Run pureMind heartbeat every 30 minutes during waking hours

[Timer]
OnCalendar=*-*-* 07..22:00,30:00 UTC
Persistent=true
RandomizedDelaySec=60

[Install]
WantedBy=timers.target
```

### .claude/integrations/base.py (UNCHANGED -- context for review)

Provides @audited decorator (rate check + audit log + write-op fail-closed), deny() (raises PermissionError + audit log), sanitise_params (strips sensitive/content keys), file-based rate limiter. All Phase 6 actions go through this.

### .claude/skills/heartbeat.md (NEW)

Machine-readable frontmatter: inputs=[proactivity_level_override], outputs=[heartbeat_summary, actions_taken], writes_to=[daily-logs/, memory/pending.md], side_effects=[gmail_draft, pr_comment, telegram_alert, audit_log]. Documents all three proactivity levels, what gets gathered, cron schedule, constraints.

### Machine-readable skill contracts (MODIFIED -- 9 existing skills)

Added YAML frontmatter (inputs, outputs, writes_to, side_effects) to: briefing, puremind-search, gmail, github, calendar, alerts, diagram, write, project-status. All 15 skills now have complete machine-readable contracts.

## Prior Art

- `tools/heartbeat.py` follows the exact `daily_reflect.py` pattern for Claude CLI invocation: `claude -p --output-format json --max-turns 1`, subprocess, JSON parsing, git commit.
- `base.py` @audited decorator and deny() used identically to Phase 4 integrations.
- Proactivity level model is new to Phase 6.
- Text table parsers (_parse_gmail_text, _parse_calendar_text) are new -- they parse the underlying tools' fixed-width output without modifying those tools.

## Test Results

- `heartbeat.py --dry-run`: passes, shows gathered state from all integrations
- `heartbeat.py` (observer): passes, Telegram alert posted (msg 19668), heartbeat-log.jsonl entry, daily log entry appended
- `gmail_integration.py list_unread --account hal --json`: valid JSON with count + messages
- `calendar_integration.py list_events --days 1 --json`: valid JSON with events array
- `telegram_integration.py read_channel --json`: valid JSON with messages array
- `systemctl status puremind-heartbeat.timer`: active, next trigger confirmed

## What to Look For

1. Can Claude be tricked via crafted integration output (email subjects, PR titles) into proposing actions outside the proactivity level? The filter_actions() is post-hoc -- is the prompt boundary sufficient?
2. Are the text table parsers brittle? What happens if gmail.py or gcalendar.py change their output format?
3. Is the update_pending action (direct file write to pending.md) safe from race conditions with daily_reflect.py?
4. Does the git_commit() in heartbeat.py conflict with the auto-commit PostToolUse hook?
5. Does the systemd timer correctly skip hours outside 07:00-22:30, or can timer drift cause a run at 22:31?
6. Is the Telegram read_channel --json path properly audited? It bypasses the @audited read_channel() function.
7. The config thresholds (stale_pr_days, overdue_pending_days, unread_email_alert) are defined but not used anywhere in heartbeat.py -- they're passed to Claude in the prompt context but not enforced in code.

Provide your review as a structured scoring table (area, score, findings) with an overall score and prioritized fix list.
