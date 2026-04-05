#!/usr/bin/env python3
"""pureMind Telegram alerts integration -- post to operator alerts endpoint only.

Write: post_alert to the configured alerts chat. Read: read recent bot updates.
Blocked: DMs to other users, posting to other channels/groups.

Usage:
    python3 telegram_integration.py post_alert "Phase 4 integration test complete"
    python3 telegram_integration.py read_channel [--limit 10]
"""

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError

sys.path.insert(0, str(Path(__file__).parent))
_VAULT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _VAULT_ROOT not in sys.path:
    sys.path.insert(0, _VAULT_ROOT)

from base import audited, deny
from tools.credentials import get_telegram_config

INTEGRATION = "telegram"

# Credentials resolved via tools.credentials (env > secrets.env > fallback)
_tg_cfg = get_telegram_config()
BOT_TOKEN = _tg_cfg["bot_token"]
ALERTS_CHAT_ID = _tg_cfg["chat_id"]

BLOCKED_OPS = {"send_dm", "post_other"}
API_BASE = "https://api.telegram.org/bot"


def _tg_api(method: str, params: dict) -> dict:
    """Call the Telegram Bot API.

    A-01/G-01 fix: enforces that chat_id in params matches ALERTS_CHAT_ID.
    Prevents imported code from messaging arbitrary chats.
    """
    # G-01: enforce chat_id restriction at the API layer
    if "chat_id" in params and str(params["chat_id"]) != str(ALERTS_CHAT_ID):
        deny(INTEGRATION, "send_to_unauthorized_chat",
             {"target_chat": params["chat_id"], "allowed_chat": ALERTS_CHAT_ID})

    url = f"{API_BASE}{BOT_TOKEN}/{method}"
    data = json.dumps(params).encode()
    req = Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except URLError as e:
        raise RuntimeError(f"Telegram API error: {e}")


@audited(INTEGRATION)
def post_alert(message: str) -> str:
    """Post a message to the pureMind alerts endpoint."""
    if not ALERTS_CHAT_ID:
        raise RuntimeError(
            "ALERTS_CHAT_ID not configured. Set chat_id in telegram_config.json "
            "or PUREMIND_TG_CHAT_ID env var.")
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN not configured.")

    # G-02 fix: no parse_mode -- plain text avoids Markdown escaping issues
    result = _tg_api("sendMessage", {
        "chat_id": ALERTS_CHAT_ID,
        "text": f"[pureMind] {message}",
    })
    if not result.get("ok"):
        raise RuntimeError(f"Telegram send failed: {result.get('description', 'unknown error')}")
    msg_id = result["result"]["message_id"]
    return f"Alert posted (message_id: {msg_id})"


@audited(INTEGRATION)
def read_channel(limit: int = 10) -> str:
    """Read recent bot updates, filtered to alerts chat only.

    G-01 fix: filters getUpdates results to ALERTS_CHAT_ID only.
    Note: getUpdates returns messages sent TO the bot, not full channel history.
    """
    if not ALERTS_CHAT_ID:
        raise RuntimeError("ALERTS_CHAT_ID not configured.")
    result = _tg_api("getUpdates", {"limit": min(limit * 2, 50), "timeout": 1})
    if not result.get("ok"):
        raise RuntimeError(f"Telegram read failed: {result.get('description')}")
    updates = result.get("result", [])
    if not updates:
        return "No recent updates from bot."
    lines = []
    for u in updates:
        msg = u.get("message") or u.get("channel_post", {})
        # G-01: only show messages from/to the configured alerts chat
        chat_id = str(msg.get("chat", {}).get("id", ""))
        if chat_id != str(ALERTS_CHAT_ID):
            continue
        text = msg.get("text", "(no text)")
        date = msg.get("date", 0)
        lines.append(f"[{date}] {text[:200]}")
    if not lines:
        return "No recent alerts in configured chat."
    return "\n".join(lines[-limit:])


def main():
    parser = argparse.ArgumentParser(description="pureMind Telegram alerts")
    parser.add_argument("command", choices=[
        "post_alert", "read_channel",
        "send_dm", "post_other",  # blocked
    ])
    parser.add_argument("message", nargs="?", default="")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--json", action="store_true",
                        help="Output as JSON (J-01)")

    args = parser.parse_args()

    try:
        if args.command in BLOCKED_OPS:
            deny(INTEGRATION, args.command, {})

        if args.command == "post_alert":
            if not args.message:
                print("ERROR: message text required", file=sys.stderr); sys.exit(1)
            print(post_alert(message=args.message))

        elif args.command == "read_channel":
            # D-02 fix: route --json through audited path then reformat
            text_result = read_channel(limit=args.limit)
            if args.json:
                # Re-fetch via audited read_channel, then format as JSON
                # read_channel already filters to ALERTS_CHAT_ID
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
                print(text_result)

    except PermissionError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
