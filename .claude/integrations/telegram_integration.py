#!/usr/bin/env python3
"""pureMind Telegram alerts integration -- post to pureMind alerts channel only.

Write: post_alert to the dedicated alerts channel. Read: read recent alerts.
Blocked: DMs, posting to other channels/groups.

Usage:
    python3 telegram_integration.py post_alert "Phase 4 integration test complete"
    python3 telegram_integration.py read_channel [--limit 10]
"""

import argparse
import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError

sys.path.insert(0, str(Path(__file__).parent))
from base import audited, deny

INTEGRATION = "telegram"

# PureTensor alert bot -- already deployed on mon2
BOT_TOKEN = "REDACTED_TELEGRAM_TOKEN"  # Will be set from env or config
ALERTS_CHAT_ID = ""  # Set after creating the pureMind alerts channel

# Try to load from environment or config
import os
BOT_TOKEN = os.environ.get("PUREMIND_TG_BOT_TOKEN", BOT_TOKEN)
ALERTS_CHAT_ID = os.environ.get("PUREMIND_TG_CHAT_ID", ALERTS_CHAT_ID)

# Config file fallback
_CONFIG_FILE = Path.home() / "pureMind" / ".claude" / "integrations" / "telegram_config.json"
if _CONFIG_FILE.exists():
    try:
        _cfg = json.loads(_CONFIG_FILE.read_text())
        BOT_TOKEN = _cfg.get("bot_token", BOT_TOKEN)
        ALERTS_CHAT_ID = _cfg.get("chat_id", ALERTS_CHAT_ID)
    except Exception:
        pass

BLOCKED_OPS = {"send_dm", "post_other"}
API_BASE = "https://api.telegram.org/bot"


def _tg_api(method: str, params: dict) -> dict:
    """Call the Telegram Bot API."""
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
    """Post a message to the pureMind alerts channel."""
    if not ALERTS_CHAT_ID:
        raise RuntimeError(
            "ALERTS_CHAT_ID not configured. Create the pureMind alerts channel, "
            "add the bot, then set chat_id in telegram_config.json or PUREMIND_TG_CHAT_ID env var."
        )
    result = _tg_api("sendMessage", {
        "chat_id": ALERTS_CHAT_ID,
        "text": f"[pureMind] {message}",
        "parse_mode": "Markdown",
    })
    if not result.get("ok"):
        raise RuntimeError(f"Telegram send failed: {result.get('description', 'unknown error')}")
    msg_id = result["result"]["message_id"]
    return f"Alert posted (message_id: {msg_id})"


@audited(INTEGRATION)
def read_channel(limit: int = 10) -> str:
    """Read recent messages from the alerts channel."""
    if not ALERTS_CHAT_ID:
        raise RuntimeError("ALERTS_CHAT_ID not configured.")
    # Note: getUpdates only works for bot messages, not channel history.
    # For channel history, we'd need a userbot or the channel must be a supergroup.
    # For now, return a note about this limitation.
    result = _tg_api("getUpdates", {"limit": limit, "timeout": 1})
    if not result.get("ok"):
        raise RuntimeError(f"Telegram read failed: {result.get('description')}")
    updates = result.get("result", [])
    if not updates:
        return "No recent updates from bot."
    lines = []
    for u in updates[-limit:]:
        msg = u.get("message") or u.get("channel_post", {})
        text = msg.get("text", "(no text)")
        date = msg.get("date", 0)
        lines.append(f"[{date}] {text[:200]}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="pureMind Telegram alerts")
    parser.add_argument("command", choices=[
        "post_alert", "read_channel",
        "send_dm", "post_other",  # blocked
    ])
    parser.add_argument("message", nargs="?", default="")
    parser.add_argument("--limit", type=int, default=10)

    args = parser.parse_args()

    if args.command in BLOCKED_OPS:
        deny(INTEGRATION, args.command, {})

    if args.command == "post_alert":
        if not args.message:
            print("ERROR: message text required", file=sys.stderr); sys.exit(1)
        print(post_alert(message=args.message))

    elif args.command == "read_channel":
        print(read_channel(limit=args.limit))


if __name__ == "__main__":
    main()
