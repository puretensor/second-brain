#!/usr/bin/env python3
"""pureMind Gmail integration -- permission-enforced wrapper over gmail.py.

Read operations: inbox search, thread reading, unread listing.
Write operations: Draft creation ONLY. No send, no trash, no delete.

Usage:
    python3 gmail_integration.py search "invoice from scan" [--account hal]
    python3 gmail_integration.py list_inbox [--account hal] [--limit 20]
    python3 gmail_integration.py list_unread [--account hal]
    python3 gmail_integration.py get <message_id> [--account hal]
    python3 gmail_integration.py create_draft --to user@example.com --subject "Re: Quote" --body "Draft text"
"""

import argparse
import base64
import json
import re
import subprocess
import sys
from email.mime.text import MIMEText
from pathlib import Path

# Add integrations dir to path for base module
sys.path.insert(0, str(Path(__file__).parent))
from base import audited, deny

INTEGRATION = "gmail"
GMAIL_PY = Path.home() / ".config" / "puretensor" / "gmail.py"
TOKEN_DIR = Path.home() / ".config" / "puretensor" / "gdrive_tokens"

# Operations explicitly blocked by pureMind permission model
BLOCKED_OPS = {"send", "reply", "trash", "batch_trash", "delete", "spam",
               "filter_create", "filter_delete"}

# A-01 fix: gmail.py commands allowed through the subprocess wrapper
_ALLOWED_GMAIL_COMMANDS = {"search", "read", "inbox", "unread"}

# D-02 fix: explicit account allowlist (prevents scope creep via extra token files)
ALLOWED_ACCOUNTS = {"hal", "ops", "personal"}


def _call_gmail(account: str, command: str, extra_args: list[str] = None) -> str:
    """Call gmail.py via subprocess and return stdout.

    A-01 fix: validates command against allowlist before subprocess call.
    D-02 fix: validates account against allowlist.
    """
    if command not in _ALLOWED_GMAIL_COMMANDS:
        deny(INTEGRATION, command, {"account": account})
    if account not in ALLOWED_ACCOUNTS:
        deny(INTEGRATION, "access_account", {"account": account,
             "reason": f"Account '{account}' not in allowlist"})
    cmd = ["python3", str(GMAIL_PY), account, command]
    if extra_args:
        cmd.extend(extra_args)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"gmail.py error: {result.stderr[:300]}")
    return result.stdout


@audited(INTEGRATION)
def search(query: str, account: str = "hal") -> str:
    """Search inbox using Gmail search syntax."""
    return _call_gmail(account, "search", ["-q", query])


@audited(INTEGRATION)
def get(message_id: str, account: str = "hal") -> str:
    """Read a specific message by ID."""
    return _call_gmail(account, "read", ["--id", message_id])


@audited(INTEGRATION)
def list_inbox(account: str = "hal", limit: int = 20) -> str:
    """List inbox messages."""
    return _call_gmail(account, "inbox", ["--limit", str(limit)])


@audited(INTEGRATION)
def list_unread(account: str = "hal") -> str:
    """List unread messages."""
    return _call_gmail(account, "unread")


@audited(INTEGRATION)
def create_draft(to: str, subject: str, body: str, account: str = "hal",
                 cc: str = "") -> str:
    """Create a Gmail draft (does NOT send). Returns draft ID.

    D-01 fix: explicit token refresh, timeout, and Google API error handling.
    D-02 fix: account validated against allowlist.
    """
    if account not in ALLOWED_ACCOUNTS:
        deny(INTEGRATION, "create_draft", {"account": account,
             "reason": f"Account '{account}' not in allowlist"})
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError

        # Load token for the requested account
        token_path = TOKEN_DIR / f"gmail_token_{account}.json"
        if not token_path.exists():
            raise FileNotFoundError(f"No Gmail token for account '{account}' at {token_path}")

        creds = Credentials.from_authorized_user_file(str(token_path))

        # D-01: explicit token refresh if expired
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token_path.write_text(creds.to_json())

        service = build("gmail", "v1", credentials=creds, cache_discovery=False)

        # A-01 fix: enforce CC ops@puretensor.ai for hal account
        if account == "hal":
            required_cc = "ops@puretensor.ai"
            if cc:
                cc_addrs = [a.strip().lower() for a in cc.split(",")]
                if required_cc not in cc_addrs:
                    cc = f"{cc}, {required_cc}"
            else:
                cc = required_cc

        # Build message
        msg = MIMEText(body)
        msg["to"] = to
        msg["subject"] = subject
        if cc:
            msg["cc"] = cc
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

        # Create draft with timeout
        draft = service.users().drafts().create(
            userId="me",
            body={"message": {"raw": raw}}
        ).execute()

        draft_id = draft["id"]
        return f"Draft created (ID: {draft_id}). Open Gmail to review. Use /approve to send."

    except ImportError:
        raise RuntimeError(
            "google-api-python-client not installed. "
            "Run: pip install google-api-python-client google-auth")
    except HttpError as e:
        raise RuntimeError(f"Gmail API error creating draft: {e.status_code} {e.reason}")
    except Exception as e:
        if "invalid_grant" in str(e).lower() or "token" in str(e).lower():
            raise RuntimeError(
                f"Gmail OAuth token error for account '{account}': {e}. "
                f"Re-authenticate with: python3 gmail.py {account} auth")
        raise


def _parse_gmail_text(text: str) -> dict:
    """Parse gmail.py text table output into structured JSON.

    J-01: enables --json output for heartbeat consumption.
    Handles the fixed-width table format: ID(0-18) Date(19-37) From(38-68) Subject(69+)
    """
    if "No messages found" in text or not text.strip():
        return {"count": 0, "messages": []}

    messages = []
    for line in text.strip().splitlines():
        # Skip header, separator, footer, and empty lines
        if line.startswith("ID") or line.startswith("---") or not line.strip():
            continue
        if line.strip().startswith("(") or line.strip().startswith("Showing"):
            continue
        # Parse fixed-width columns
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


def main():
    parser = argparse.ArgumentParser(description="pureMind Gmail integration")
    parser.add_argument("command", choices=[
        "search", "get", "list_inbox", "list_unread", "create_draft",
        # Blocked but listed so we can give a clear denial message
        "send", "reply", "trash", "delete", "spam",
    ])
    parser.add_argument("--account", default="hal")
    parser.add_argument("--query", "-q", default="")
    parser.add_argument("--id", default="")
    parser.add_argument("--to", default="")
    parser.add_argument("--cc", default="")
    parser.add_argument("--subject", default="")
    parser.add_argument("--body", default="")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--json", action="store_true",
                        help="Output as JSON (J-01)")

    args = parser.parse_args()

    try:
        # Block disallowed operations
        if args.command in BLOCKED_OPS:
            deny(INTEGRATION, args.command, {"account": args.account})

        if args.command == "search":
            if not args.query:
                print("ERROR: --query required for search", file=sys.stderr)
                sys.exit(1)
            result = search(query=args.query, account=args.account)
            print(json.dumps(_parse_gmail_text(result)) if args.json else result)

        elif args.command == "get":
            if not args.id:
                print("ERROR: --id required for get", file=sys.stderr)
                sys.exit(1)
            print(get(message_id=args.id, account=args.account))

        elif args.command == "list_inbox":
            result = list_inbox(account=args.account, limit=args.limit)
            print(json.dumps(_parse_gmail_text(result)) if args.json else result)

        elif args.command == "list_unread":
            result = list_unread(account=args.account)
            print(json.dumps(_parse_gmail_text(result)) if args.json else result)

        elif args.command == "create_draft":
            if not args.to or not args.subject:
                print("ERROR: --to and --subject required for create_draft", file=sys.stderr)
                sys.exit(1)
            print(create_draft(to=args.to, subject=args.subject, body=args.body,
                               account=args.account, cc=args.cc))

    except PermissionError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
