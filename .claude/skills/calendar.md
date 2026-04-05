---
name: calendar
description: List and search Google Calendar events (read-only) via the pureMind Calendar integration
---

# Calendar Integration (Read-Only)

View upcoming events and search calendar. No event creation or modification in Phase 4.

## Available Operations

```bash
# List upcoming events (next 7 days)
python3 ~/pureMind/.claude/integrations/calendar_integration.py list_events --days 7 --account ops

# Get event details
python3 ~/pureMind/.claude/integrations/calendar_integration.py get <event_id> --account ops

# Search events
python3 ~/pureMind/.claude/integrations/calendar_integration.py search "standup" --account ops
```

## Account

Always use `ops` (ops@puretensor.ai) -- single calendar, no separate personal calendar.

## Constraints

- **Read-only.** No event creation, update, or deletion in Phase 4.
- All operations are logged to the pm_audit table.
