---
name: alerts
description: Post alerts to the pureMind Telegram alerts channel
---

# pureMind Alerts

Post notifications to the pureMind Telegram alerts endpoint (operator DM via @puretensor_alert_bot).

## Available Operations

```bash
# Post an alert
python3 ~/pureMind/.claude/integrations/telegram_integration.py post_alert "Phase 4 deployment complete"

# Read recent alerts
python3 ~/pureMind/.claude/integrations/telegram_integration.py read_channel --limit 10
```

## Constraints

- **Configured chat only.** Posts to the operator alerts endpoint (chat_id in telegram_config.json). Cannot message other chats.
- Messages are prefixed with `[pureMind]` automatically.
- All operations are logged to the pm_audit table.
