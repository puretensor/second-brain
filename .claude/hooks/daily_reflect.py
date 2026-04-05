#!/usr/bin/env python3
"""pureMind daily reflection -- promote knowledge from daily logs to memory.

Nightly cron (23:00 UTC via systemd timer) reads today's daily log and
current memory.md, uses Claude CLI to extract high-signal items, and
promotes them to memory.md (RAM). This is the MemGPT-inspired disk-to-RAM
promotion mechanism.

Usage:
    python3 daily_reflect.py              # Normal run
    python3 daily_reflect.py --dry-run    # Show proposed changes, don't apply
    python3 daily_reflect.py --date 2026-04-04  # Reflect on a specific day
"""

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

PUREMIND_ROOT = Path.home() / "pureMind"
MEMORY_FILE = PUREMIND_ROOT / "memory" / "memory.md"
PENDING_FILE = PUREMIND_ROOT / "memory" / "pending.md"
DAILY_LOGS = PUREMIND_ROOT / "daily-logs"
ARCHIVE_DIR = PUREMIND_ROOT / "knowledge" / "archive"
REFLECT_LOG = DAILY_LOGS / "reflection-log.jsonl"

MEMORY_CAP_BYTES = 5120  # ~8K tokens
ARCHIVE_AFTER_DAYS = 30

REFLECTION_PROMPT = """\
You are the pureMind reflection engine for PureTensor's sovereign second brain.

## Your Task

Analyze today's daily log and the current state of memory.md and pending.md.
Output a JSON object with exactly these keys:

1. "add_to_memory": list of strings -- new bullet points to ADD to memory.md.
   Only promote items that are durable, high-signal knowledge:
   - Decisions with lasting impact and their rationale
   - Infrastructure changes (new services, config changes, capacity changes)
   - Lessons learned from incidents or debugging
   - New contacts, credentials references (pointers only, never actual secrets)
   - Project milestones or status changes
   DO NOT promote: one-off debug details, conversation-specific context,
   transient errors, items already in memory.md.

2. "remove_from_memory": list of strings -- exact lines to REMOVE from memory.md.
   Remove items that are stale, resolved, superseded, or no longer relevant.

3. "pending_updates": list of objects with keys "action" (add/resolve/update),
   "item" (the text), and "reason" (why).

4. "summary": one-sentence summary of what changed today.

## Scoring Guidelines
- Mentioned in 3+ sessions across days = strong promote signal
- Decisions with rationale = promote
- Infrastructure changes = promote
- Resolved pending items = mark done
- One-off debug details = skip
- Conversation-specific context = skip

Output ONLY valid JSON. No markdown fencing, no commentary.

## Current State

### memory.md (RAM)
{memory_content}

### pending.md
{pending_content}

### Today's Daily Log
{daily_log}
"""


def read_file_safe(path: Path) -> str:
    """Read a file safely, return empty string if missing or error."""
    if not path.exists():
        return "(empty)"
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return "(read error)"


def call_claude(prompt: str) -> dict | None:
    """Call Claude CLI in non-interactive mode and parse JSON response."""
    try:
        result = subprocess.run(
            ["claude", "-p", "--output-format", "json", "--max-turns", "1"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            print(f"Claude CLI error (rc={result.returncode}): {result.stderr[:200]}", file=sys.stderr)
            return None

        # Parse the outer JSON (Claude CLI wrapper)
        outer = json.loads(result.stdout)
        # Extract the text content from the response
        text = outer.get("result", "")
        if not text:
            print("Empty result from Claude CLI", file=sys.stderr)
            return None

        # Parse the inner JSON (our structured response)
        # Strip any markdown fencing if Claude adds it despite instructions
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        return json.loads(text)

    except subprocess.TimeoutExpired:
        print("Claude CLI timed out after 120s", file=sys.stderr)
        return None
    except json.JSONDecodeError as e:
        print(f"Failed to parse Claude response as JSON: {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Claude CLI call failed: {e}", file=sys.stderr)
        return None


def apply_memory_changes(changes: dict, dry_run: bool = False) -> dict:
    """Apply add/remove changes to memory.md. Returns stats."""
    stats = {"added": 0, "removed": 0, "pending_updated": 0}

    current = read_file_safe(MEMORY_FILE)
    if current == "(empty)" or current == "(read error)":
        current = ""

    lines = current.splitlines()

    # Remove lines
    removals = changes.get("remove_from_memory", [])
    if removals:
        new_lines = []
        for line in lines:
            stripped = line.strip()
            if any(stripped == r.strip() for r in removals):
                stats["removed"] += 1
                if dry_run:
                    print(f"  REMOVE: {stripped}")
            else:
                new_lines.append(line)
        lines = new_lines

    # Add lines (append before the last section or at end)
    additions = changes.get("add_to_memory", [])
    if additions:
        lines.append("")
        lines.append("## Recent Promotions")
        for item in additions:
            bullet = item if item.startswith("- ") else f"- {item}"
            lines.append(bullet)
            stats["added"] += 1
            if dry_run:
                print(f"  ADD: {bullet}")

    new_content = "\n".join(lines).strip() + "\n"

    # Enforce cap
    if len(new_content.encode("utf-8")) > MEMORY_CAP_BYTES:
        # Trim from "Recent Promotions" section first (oldest promotions)
        trimmed = enforce_cap(new_content)
        if dry_run:
            over = len(new_content.encode("utf-8")) - MEMORY_CAP_BYTES
            print(f"  CAP: Trimmed ~{over} bytes to stay under {MEMORY_CAP_BYTES}B")
        new_content = trimmed

    if not dry_run:
        MEMORY_FILE.write_text(new_content, encoding="utf-8")

    # Update pending.md
    pending_updates = changes.get("pending_updates", [])
    if pending_updates:
        apply_pending_changes(pending_updates, dry_run)
        stats["pending_updated"] = len(pending_updates)

    return stats


def enforce_cap(content: str) -> str:
    """Trim content to stay under MEMORY_CAP_BYTES."""
    encoded = content.encode("utf-8")
    if len(encoded) <= MEMORY_CAP_BYTES:
        return content

    lines = content.splitlines()
    # Remove lines from "Recent Promotions" section (bottom) first
    while len("\n".join(lines).encode("utf-8")) > MEMORY_CAP_BYTES and lines:
        # Find last "Recent Promotions" bullet and remove it
        for i in range(len(lines) - 1, -1, -1):
            if lines[i].strip().startswith("- ") and i > 0:
                # Check if we're in the Recent Promotions section
                for j in range(i, -1, -1):
                    if "Recent Promotions" in lines[j]:
                        lines.pop(i)
                        break
                else:
                    # Not in promotions, remove from very end
                    lines.pop()
                break
        else:
            lines.pop()

    return "\n".join(lines).strip() + "\n"


def apply_pending_changes(updates: list[dict], dry_run: bool = False):
    """Apply changes to pending.md."""
    current = read_file_safe(PENDING_FILE)
    if current in ("(empty)", "(read error)"):
        current = "# Pending Items\n\n## Active\n\n## Resolved\n"

    for update in updates:
        action = update.get("action", "")
        item = update.get("item", "")
        reason = update.get("reason", "")

        if dry_run:
            print(f"  PENDING {action.upper()}: {item} ({reason})")
            continue

        if action == "resolve":
            # Move from Active to Resolved
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            current = current.replace(
                f"- [ ] {item}",
                f"- [x] {item} (resolved {today}: {reason})",
            )
        elif action == "add":
            # Add to Active section
            active_marker = "## Active"
            if active_marker in current:
                current = current.replace(
                    active_marker,
                    f"{active_marker}\n- [ ] {item}",
                )

    if not dry_run:
        PENDING_FILE.write_text(current, encoding="utf-8")


def archive_old_logs():
    """Move daily logs older than ARCHIVE_AFTER_DAYS to knowledge/archive/."""
    if not DAILY_LOGS.is_dir():
        return 0

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    cutoff = datetime.now(timezone.utc) - timedelta(days=ARCHIVE_AFTER_DAYS)
    archived = 0

    for log_file in DAILY_LOGS.glob("????-??-??.md"):
        try:
            date_str = log_file.stem
            log_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            if log_date < cutoff:
                dest = ARCHIVE_DIR / log_file.name
                shutil.move(str(log_file), str(dest))
                archived += 1
        except (ValueError, OSError):
            continue

    return archived


def git_commit(message: str):
    """Stage and commit all pureMind changes."""
    try:
        subprocess.run(
            ["git", "-C", str(PUREMIND_ROOT), "add", "-A"],
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
        print(f"Git commit failed: {e}", file=sys.stderr)


def log_result(date_str: str, stats: dict, summary: str):
    """Append reflection result to JSONL log."""
    entry = {
        "date": date_str,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stats": stats,
        "summary": summary,
    }
    try:
        with open(REFLECT_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def main():
    dry_run = "--dry-run" in sys.argv
    date_override = None
    if "--date" in sys.argv:
        idx = sys.argv.index("--date")
        if idx + 1 < len(sys.argv):
            date_override = sys.argv[idx + 1]

    target_date = date_override or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log_path = DAILY_LOGS / f"{target_date}.md"

    if not log_path.exists():
        print(f"No daily log for {target_date}. Nothing to reflect on.")
        return

    daily_log = read_file_safe(log_path)
    memory_content = read_file_safe(MEMORY_FILE)
    pending_content = read_file_safe(PENDING_FILE)

    if dry_run:
        print(f"=== pureMind Reflection (DRY RUN) -- {target_date} ===\n")

    # Build prompt
    prompt = REFLECTION_PROMPT.format(
        memory_content=memory_content,
        pending_content=pending_content,
        daily_log=daily_log,
    )

    # Call Claude
    if dry_run:
        print("Calling Claude CLI for analysis...")
    changes = call_claude(prompt)

    if not changes:
        print("No changes extracted from Claude. Skipping.", file=sys.stderr)
        log_result(target_date, {"error": "no_response"}, "Claude returned no changes")
        return

    summary = changes.get("summary", "No summary provided")
    if dry_run:
        print(f"\nSummary: {summary}\n")
        print("Proposed changes:")

    # Apply changes
    stats = apply_memory_changes(changes, dry_run=dry_run)

    # Archive old logs (not in dry run)
    archived = 0
    if not dry_run:
        archived = archive_old_logs()
        stats["archived"] = archived

    if dry_run:
        print(f"\nStats: {json.dumps(stats, indent=2)}")
        print(f"Archived logs: {archived} (skipped in dry run)")
        print("\nNo changes applied (dry run).")
    else:
        # Commit all changes
        git_commit(f"reflect: {target_date} -- {summary[:60]}")
        log_result(target_date, stats, summary)
        print(f"Reflection complete for {target_date}: +{stats['added']} -{stats['removed']} pending:{stats['pending_updated']} archived:{archived}")


if __name__ == "__main__":
    main()
