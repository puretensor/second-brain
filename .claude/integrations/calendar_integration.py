#!/usr/bin/env python3
"""pureMind Google Calendar integration -- read-only wrapper over gcalendar.py.

Read: event listing, event details, search. Write: NONE (Phase 4 = read-only).

gcalendar.py CLI: gcalendar.py {personal,ops,all} {today,week,upcoming,search,get,...}

Usage:
    python3 calendar_integration.py list_events [--days 2] [--account ops]
    python3 calendar_integration.py get <event_id> [--account ops]
    python3 calendar_integration.py search "standup" [--account ops]
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from base import audited, deny

INTEGRATION = "calendar"
GCALENDAR_PY = Path.home() / "nexus" / "tools" / "gcalendar.py"

BLOCKED_OPS = {"create", "update", "delete"}

# A-01 fix: gcalendar.py commands allowed through the subprocess wrapper
_ALLOWED_GCAL_COMMANDS = {"today", "week", "upcoming", "search", "get", "calendars"}


def _call_gcal(account: str, command: str, extra_args: list[str] = None) -> str:
    """Call gcalendar.py via subprocess and return stdout.

    A-01 fix: validates command against allowlist before subprocess call.
    """
    if command not in _ALLOWED_GCAL_COMMANDS:
        deny(INTEGRATION, command, {"account": account})
    cmd = ["python3", str(GCALENDAR_PY), account, command]
    if extra_args:
        cmd.extend(extra_args)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"gcalendar.py error: {result.stderr[:300]}")
    return result.stdout


@audited(INTEGRATION)
def list_events(days: int = 7, account: str = "ops") -> str:
    """List upcoming events.

    F-01 fix: days=1 -> today, days>1 -> upcoming with scaled limit.
    No longer maps days=2-7 to "week" (which over-returns).
    """
    if days <= 1:
        return _call_gcal(account, "today")
    else:
        # upcoming returns next N events chronologically; scale with requested days
        limit = min(days * 3, 30)
        return _call_gcal(account, "upcoming", ["--limit", str(limit)])


@audited(INTEGRATION)
def get_event(event_id: str, account: str = "ops") -> str:
    """Get details of a specific event."""
    return _call_gcal(account, "get", ["--id", event_id])


@audited(INTEGRATION)
def search_events(query: str, account: str = "ops") -> str:
    """Search calendar events by keyword."""
    return _call_gcal(account, "search", ["-q", query])


def _parse_calendar_text(text: str) -> dict:
    """Parse gcalendar.py text table output into structured JSON.

    J-01: enables --json output for heartbeat consumption.
    Handles the fixed-width table: Time(0-45) Summary(46-94) ID(95+)
    """
    if not text.strip():
        return {"events": []}

    events = []
    in_table = False
    for line in text.strip().splitlines():
        # Skip token refresh, headers, footers
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
        # Parse fixed-width columns
        if len(line) >= 50:
            event = {
                "time": line[0:46].strip(),
                "summary": line[46:95].strip() if len(line) > 46 else "",
                "id": line[95:].strip() if len(line) > 95 else "",
            }
            if event["time"] or event["summary"]:
                events.append(event)

    return {"events": events}


def main():
    parser = argparse.ArgumentParser(description="pureMind Calendar integration (read-only)")
    parser.add_argument("command", choices=[
        "list_events", "get", "search",
        "create", "update", "delete",  # blocked
    ])
    parser.add_argument("query_or_id", nargs="?", default="")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--account", default="ops")
    parser.add_argument("--json", action="store_true",
                        help="Output as JSON (J-01)")

    args = parser.parse_args()

    try:
        if args.command in BLOCKED_OPS:
            deny(INTEGRATION, args.command, {"account": args.account})

        if args.command == "list_events":
            result = list_events(days=args.days, account=args.account)
            print(json.dumps(_parse_calendar_text(result)) if args.json else result)

        elif args.command == "get":
            if not args.query_or_id:
                print("ERROR: event_id required", file=sys.stderr); sys.exit(1)
            print(get_event(event_id=args.query_or_id, account=args.account))

        elif args.command == "search":
            if not args.query_or_id:
                print("ERROR: search query required", file=sys.stderr); sys.exit(1)
            result = search_events(query=args.query_or_id, account=args.account)
            print(json.dumps(_parse_calendar_text(result)) if args.json else result)

    except PermissionError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
