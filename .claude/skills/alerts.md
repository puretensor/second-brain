---
name: alerts
description: Post alerts to the pureMind Telegram alerts channel
---

# pureMind Alerts

Post notifications to the dedicated pureMind Telegram alerts channel.

## Available Operations

```bash
# Post an alert
python3 ~/pureMind/.claude/integrations/telegram_integration.py post_alert "Phase 4 deployment complete"

# Read recent alerts
python3 ~/pureMind/.claude/integrations/telegram_integration.py read_channel --limit 10
```

## Constraints

- **Alerts channel only.** Cannot DM users or post to other channels.
- Messages are prefixed with `[pureMind]` automatically.
- All operations are logged to the pm_audit table.
