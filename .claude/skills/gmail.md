---
name: gmail
description: Search inbox, read emails, and create drafts via the pureMind Gmail integration
inputs: [query, account, message_id]
outputs: [messages, draft_id]
writes_to: []
side_effects: [gmail_draft_creation, audit_log]
---

# Gmail Integration

Search, read, and draft emails through the pureMind permission-enforced Gmail wrapper. Drafts only -- no direct sending.

## Available Operations

```bash
# Search inbox
python3 ~/pureMind/.claude/integrations/gmail_integration.py search --query "from:scan.co.uk invoice" --account hal

# List inbox (recent messages)
python3 ~/pureMind/.claude/integrations/gmail_integration.py list_inbox --account hal --limit 20

# List unread messages
python3 ~/pureMind/.claude/integrations/gmail_integration.py list_unread --account hal

# Read a specific message
python3 ~/pureMind/.claude/integrations/gmail_integration.py get --id <message_id> --account hal

# Create a draft (does NOT send)
python3 ~/pureMind/.claude/integrations/gmail_integration.py create_draft --to user@example.com --subject "Re: Quote" --body "Draft text" --account hal
```

## Accounts

- `hal` (default) -- hal@puretensor.ai (primary)
- `ops` -- ops@puretensor.ai
- `personal` -- heimir.helgason@gmail.com

## Constraints

- **No sending.** Drafts only. User reviews and sends from Gmail directly.
- **No reply/trash/delete/spam/filters.** Read and draft operations only.
- **Accounts:** hal (default), ops, personal only. Other accounts blocked.
- All operations are logged to the pm_audit table.
