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
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from base import audited, deny

INTEGRATION = "calendar"
GCALENDAR_PY = Path.home() / "nexus" / "tools" / "gcalendar.py"

BLOCKED_OPS = {"create", "update", "delete"}


def _call_gcal(account: str, command: str, extra_args: list[str] = None) -> str:
    """Call gcalendar.py via subprocess and return stdout.

    CLI format: gcalendar.py <account> <command> [options]
    """
    cmd = ["python3", str(GCALENDAR_PY), account, command]
    if extra_args:
        cmd.extend(extra_args)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"gcalendar.py error: {result.stderr[:300]}")
    return result.stdout


@audited(INTEGRATION)
def list_events(days: int = 7, account: str = "ops") -> str:
    """List upcoming events. Maps days to gcalendar.py commands:
    days=1 -> today, days<=7 -> week, days>7 -> upcoming --limit 20.
    """
    if days <= 1:
        return _call_gcal(account, "today")
    elif days <= 7:
        return _call_gcal(account, "week")
    else:
        return _call_gcal(account, "upcoming", ["--limit", "20"])


@audited(INTEGRATION)
def get_event(event_id: str, account: str = "ops") -> str:
    """Get details of a specific event."""
    return _call_gcal(account, "get", ["--id", event_id])


@audited(INTEGRATION)
def search_events(query: str, account: str = "ops") -> str:
    """Search calendar events by keyword."""
    return _call_gcal(account, "search", ["-q", query])


def main():
    parser = argparse.ArgumentParser(description="pureMind Calendar integration (read-only)")
    parser.add_argument("command", choices=[
        "list_events", "get", "search",
        "create", "update", "delete",  # blocked
    ])
    parser.add_argument("query_or_id", nargs="?", default="")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--account", default="ops")

    args = parser.parse_args()

    if args.command in BLOCKED_OPS:
        deny(INTEGRATION, args.command, {"account": args.account})

    if args.command == "list_events":
        print(list_events(days=args.days, account=args.account))

    elif args.command == "get":
        if not args.query_or_id:
            print("ERROR: event_id required", file=sys.stderr); sys.exit(1)
        print(get_event(event_id=args.query_or_id, account=args.account))

    elif args.command == "search":
        if not args.query_or_id:
            print("ERROR: search query required", file=sys.stderr); sys.exit(1)
        print(search_events(query=args.query_or_id, account=args.account))


if __name__ == "__main__":
    main()
