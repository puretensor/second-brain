#!/usr/bin/env python3
"""pureMind daily reflection -- promote knowledge from daily logs to memory.

Nightly cron (23:00 UTC via systemd timer) reads today's daily log and
current memory.md, uses Claude CLI to extract high-signal items, and
promotes them to memory.md (RAM). This is the MemGPT-inspired disk-to-RAM
promotion mechanism.

Usage:
    python3 daily_reflect.py              # Normal run
    python3 daily_reflect.py --dry-run    # Show proposed changes, don't apply or call Claude
    python3 daily_reflect.py --date 2026-04-04  # Reflect on a specific day
"""

import json
import os
import re
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
   Match the EXACT text of the line including the leading "- ".

3. "pending_updates": list of objects, each with:
   - "action": one of "add", "resolve"
   - "item": for "add", the new item text; for "resolve", the EXACT text of
     the existing bullet (starting with "- **...") to match against
   - "reason": brief explanation

4. "summary": one-sentence summary of what changed today.

IMPORTANT: For "resolve" actions, the "item" must be an EXACT prefix match
of the line in pending.md (e.g., "- **Google Cloud Startups:**" to match
the full bullet). For "add" actions, use the format "- **Label:** description".

Output ONLY valid JSON. No markdown fencing, no commentary.

## Current State

### memory.md (RAM)
{memory_content}

### pending.md
{pending_content}

### Today's Daily Log
{daily_log}

### Historical Context (RAG)
{historical_context}
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
            print(f"ERROR: Claude CLI exited {result.returncode}: {result.stderr[:200]}", file=sys.stderr)
            return None

        # Parse the outer JSON (Claude CLI wrapper)
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

        # Validate expected schema
        if not isinstance(parsed, dict):
            print("ERROR: Claude returned non-dict JSON", file=sys.stderr)
            return None
        for key in ("add_to_memory", "remove_from_memory", "pending_updates", "summary"):
            if key not in parsed:
                print(f"WARNING: Missing key '{key}' in Claude response, defaulting", file=sys.stderr)
                if key == "summary":
                    parsed[key] = "No summary provided"
                else:
                    parsed[key] = []
        if not isinstance(parsed["add_to_memory"], list):
            parsed["add_to_memory"] = []
        if not isinstance(parsed["remove_from_memory"], list):
            parsed["remove_from_memory"] = []
        if not isinstance(parsed["pending_updates"], list):
            parsed["pending_updates"] = []

        return parsed

    except FileNotFoundError:
        print("ERROR: Claude CLI not found. Install with: npm install -g @anthropic-ai/claude-code", file=sys.stderr)
        return None
    except subprocess.TimeoutExpired:
        print("ERROR: Claude CLI timed out after 120s", file=sys.stderr)
        return None
    except json.JSONDecodeError as e:
        print(f"ERROR: Failed to parse Claude response as JSON: {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"ERROR: Claude CLI call failed: {e}", file=sys.stderr)
        return None


def apply_memory_changes(changes: dict, dry_run: bool = False) -> dict:
    """Apply add/remove changes to memory.md. Returns stats."""
    stats = {"added": 0, "removed": 0, "pending_updated": 0}

    current = read_file_safe(MEMORY_FILE)
    if current in ("(empty)", "(read error)"):
        current = ""

    lines = current.splitlines()

    # Remove lines (exact match)
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

    # Add lines -- append to existing "## Recent Promotions" or create it
    additions = changes.get("add_to_memory", [])
    if additions:
        # Find existing section to avoid duplicating header
        promo_idx = None
        for i, line in enumerate(lines):
            if line.strip() == "## Recent Promotions":
                promo_idx = i
                break

        if promo_idx is None:
            lines.append("")
            lines.append("## Recent Promotions")

        for item in additions:
            bullet = item if item.startswith("- ") else f"- {item}"
            lines.append(bullet)
            stats["added"] += 1
            if dry_run:
                print(f"  ADD: {bullet}")

    new_content = "\n".join(lines).strip() + "\n"

    # Enforce cap -- trim oldest promotions first
    new_content = enforce_cap(new_content, dry_run)

    if not dry_run:
        MEMORY_FILE.write_text(new_content, encoding="utf-8")

    # Update pending.md
    pending_updates = changes.get("pending_updates", [])
    if pending_updates:
        count = apply_pending_changes(pending_updates, dry_run)
        stats["pending_updated"] = count

    return stats


def enforce_cap(content: str, dry_run: bool = False) -> str:
    """Trim content to stay under MEMORY_CAP_BYTES. Removes oldest promotions first."""
    if len(content.encode("utf-8")) <= MEMORY_CAP_BYTES:
        return content

    lines = content.splitlines()

    # Find the "## Recent Promotions" section
    promo_start = None
    for i, line in enumerate(lines):
        if line.strip() == "## Recent Promotions":
            promo_start = i
            break

    if promo_start is None:
        # No promotions section -- truncate from end
        while len("\n".join(lines).encode("utf-8")) > MEMORY_CAP_BYTES and lines:
            removed = lines.pop()
            if dry_run:
                print(f"  CAP-TRIM: {removed.strip()}")
        return "\n".join(lines).strip() + "\n"

    # Collect promotion bullets (oldest first = right after the header)
    promo_bullets = []
    for i in range(promo_start + 1, len(lines)):
        if lines[i].strip().startswith("- "):
            promo_bullets.append(i)
        elif lines[i].strip().startswith("## "):
            break  # Hit next section

    # Remove oldest promotions (lowest index first) until under cap
    removed_indices = set()
    for idx in promo_bullets:
        if len("\n".join(l for i, l in enumerate(lines) if i not in removed_indices).encode("utf-8")) <= MEMORY_CAP_BYTES:
            break
        removed_indices.add(idx)
        if dry_run:
            print(f"  CAP-TRIM (oldest): {lines[idx].strip()}")

    result = [l for i, l in enumerate(lines) if i not in removed_indices]

    # If still over cap after removing all promotions, trim from end
    while len("\n".join(result).encode("utf-8")) > MEMORY_CAP_BYTES and result:
        removed = result.pop()
        if dry_run:
            print(f"  CAP-TRIM (tail): {removed.strip()}")

    return "\n".join(result).strip() + "\n"


def apply_pending_changes(updates: list[dict], dry_run: bool = False) -> int:
    """Apply changes to pending.md. Returns count of changes applied."""
    current = read_file_safe(PENDING_FILE)
    if current in ("(empty)", "(read error)"):
        current = "# Pending Items & Follow-Ups\n\nVolatile time-sensitive items. Review weekly, archive when resolved.\n\n## Active\n\n## Resolved\n"

    count = 0
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    for update in updates:
        action = update.get("action", "")
        item = update.get("item", "")
        reason = update.get("reason", "")

        if not item:
            continue

        if action == "resolve":
            # Find the line that starts with the item text (prefix match)
            lines = current.splitlines()
            resolved = False
            for i, line in enumerate(lines):
                if line.strip().startswith(item.strip()):
                    resolved_line = f"{line.strip()} *(resolved {today}: {reason})*"
                    # Move to Resolved section
                    lines.pop(i)
                    # Find ## Resolved and insert after it
                    for j, l in enumerate(lines):
                        if l.strip() == "## Resolved":
                            lines.insert(j + 1, resolved_line)
                            resolved = True
                            break
                    if not resolved:
                        # No Resolved section, append
                        lines.append("## Resolved")
                        lines.append(resolved_line)
                        resolved = True
                    break

            if resolved:
                current = "\n".join(lines)
                count += 1
                if dry_run:
                    print(f"  PENDING RESOLVE: {item} ({reason})")
            elif dry_run:
                print(f"  PENDING RESOLVE (no match): {item}")

        elif action == "add":
            # Add to Active section
            lines = current.splitlines()
            inserted = False
            for i, line in enumerate(lines):
                if line.strip() == "## Active":
                    # Insert after the ## Active line (and any blank line after it)
                    insert_at = i + 1
                    while insert_at < len(lines) and not lines[insert_at].strip():
                        insert_at += 1
                    bullet = item if item.startswith("- ") else f"- **{item}**"
                    lines.insert(insert_at, bullet)
                    inserted = True
                    break
            if inserted:
                current = "\n".join(lines)
                count += 1
                if dry_run:
                    print(f"  PENDING ADD: {item} ({reason})")

    if not dry_run and count > 0:
        PENDING_FILE.write_text(current.strip() + "\n", encoding="utf-8")

    return count


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
    """Stage owned files and commit."""
    try:
        # Scope to files this script owns -- not git add -A
        subprocess.run(
            ["git", "-C", str(PUREMIND_ROOT), "add",
             "memory/memory.md", "memory/pending.md",
             "daily-logs/reflection-log.jsonl", "knowledge/archive/"],
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
        print(f"ERROR: Git commit failed: {e}", file=sys.stderr)


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


def extract_topics(daily_log: str) -> list[str]:
    """Extract key topics from daily log for RAG queries.

    Filters out scaffolding headings (dates, generic section names) to
    produce more targeted RAG queries.
    """
    # Scaffolding terms to skip -- generic structure, not content
    SCAFFOLDING = {
        "work done", "decisions", "new facts", "pending", "context",
        "session", "compaction extract", "historical context",
        "overall assessment", "critical issues", "important improvements",
        "nice-to-haves", "structural observations", "missing from phase",
    }

    topics = []
    # Grab headings (skip generic ones)
    for match in re.finditer(r"^#{1,4}\s+(.+)$", daily_log, re.MULTILINE):
        heading = match.group(1).strip()
        # Skip date-like headings, session markers, scaffolding
        if re.match(r"^\d{4}-\d{2}-\d{2}", heading):
            continue
        if heading.lower().startswith("session:"):
            continue
        if any(heading.lower().startswith(s) for s in SCAFFOLDING):
            continue
        topics.append(heading)
    # Grab bold terms
    for match in re.finditer(r"\*\*([^*]+)\*\*", daily_log):
        term = match.group(1).strip().rstrip(":")
        if len(term) > 3 and len(term) < 80:
            # Skip generic labels
            if term.lower() not in SCAFFOLDING and not term.lower().startswith("context"):
                topics.append(term)
    # Deduplicate, limit
    seen = set()
    unique = []
    for t in topics:
        if t.lower() not in seen:
            seen.add(t.lower())
            unique.append(t)
    return unique[:10]


def get_rag_context(daily_log: str, target_date: str) -> str:
    """Search pureMind RAG for historical context related to today's topics.

    Excludes the current day's log from results to avoid circular context.
    """
    SEARCH_TOOL = PUREMIND_ROOT / "tools" / "search.py"
    if not SEARCH_TOOL.exists():
        return "(RAG not available -- search.py not found)"

    topics = extract_topics(daily_log)
    if not topics:
        return "(no topics extracted from daily log)"

    # Build a combined query from top topics
    query = " ".join(topics[:5])
    try:
        result = subprocess.run(
            [sys.executable, str(SEARCH_TOOL), query, "--limit", "8", "--json"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return f"(RAG search failed: {result.stderr[:100]})"

        results = json.loads(result.stdout)
        if not results:
            return "(no relevant historical context found)"

        # Filter out the current day's log to avoid circular context
        today_log_path = f"daily-logs/{target_date}.md"
        filtered = [r for r in results if r["file_path"] != today_log_path][:5]

        if not filtered:
            return "(no relevant historical context found outside today's log)"

        lines = []
        for r in filtered:
            lines.append(f"- [{r['file_path']}] {r['content'][:300]}")
        return "\n".join(lines)

    except Exception as e:
        return f"(RAG search error: {e})"


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
        sys.exit(0)

    daily_log = read_file_safe(log_path)
    memory_content = read_file_safe(MEMORY_FILE)
    pending_content = read_file_safe(PENDING_FILE)

    # Fetch RAG context (even in dry-run to show what would be included)
    historical_context = get_rag_context(daily_log, target_date)

    if dry_run:
        print(f"=== pureMind Reflection (DRY RUN) -- {target_date} ===\n")
        print("Showing what WOULD happen. No Claude call, no file writes.\n")
        print(f"Daily log: {len(daily_log)} chars")
        print(f"Memory: {len(memory_content)} chars ({len(memory_content.encode('utf-8'))} bytes / {MEMORY_CAP_BYTES} cap)")
        print(f"Pending: {len(pending_content)} chars")
        topics = extract_topics(daily_log)
        print(f"Topics extracted: {topics[:5]}")
        print(f"Historical context: {len(historical_context)} chars")
        print("\nTo run for real, omit --dry-run.")
        sys.exit(0)

    # Build prompt
    prompt = REFLECTION_PROMPT.format(
        memory_content=memory_content,
        pending_content=pending_content,
        daily_log=daily_log,
        historical_context=historical_context,
    )

    # Call Claude
    changes = call_claude(prompt)

    if not changes:
        print("ERROR: No changes extracted from Claude. Exiting with error.", file=sys.stderr)
        sys.exit(1)

    summary = changes.get("summary", "No summary provided")

    # Apply changes
    stats = apply_memory_changes(changes, dry_run=False)

    # Archive old logs
    archived = archive_old_logs()
    stats["archived"] = archived

    # Commit all changes (including reflection log)
    log_result(target_date, stats, summary)
    git_commit(f"reflect: {target_date} -- {summary[:60]}")

    # I-01: Re-index synchronously so chunk IDs are fresh before entity extraction
    index_script = PUREMIND_ROOT / "tools" / "index.py"
    if index_script.exists():
        try:
            subprocess.run(
                [sys.executable, str(index_script), "--quiet"],
                timeout=120,
            )
        except (subprocess.TimeoutExpired, Exception) as e:
            print(f"  Reindex failed: {e}", file=sys.stderr)

    # Extract entities from today's log for the knowledge graph (Phase 7)
    # I-01: runs after synchronous reindex so _find_chunk_ids() sees current data
    entity_count = 0
    try:
        sys.path.insert(0, str(PUREMIND_ROOT))
        from tools.extract import extract_from_file
        from tools.db import get_write_conn
        import hashlib

        conn = get_write_conn()
        if conn and log_path.exists():
            fhash = hashlib.sha256(log_path.read_bytes()).hexdigest()
            e, r = extract_from_file(conn, log_path, fhash, verbose=False)
            entity_count = e
            conn.close()
    except Exception as ex:
        print(f"  Entity extraction skipped: {ex}", file=sys.stderr)

    print(f"Reflection complete for {target_date}: +{stats['added']} -{stats['removed']} "
          f"pending:{stats['pending_updated']} archived:{archived} entities:{entity_count}")


if __name__ == "__main__":
    main()
