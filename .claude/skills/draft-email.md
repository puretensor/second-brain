---
name: draft-email
description: Draft an email in the operator's voice using Gmail integration and style templates
inputs: [recipient, subject, context]
outputs: [draft_id]
writes_to: []
side_effects: [gmail_draft_creation, audit_log]
---

# Draft Email

Compose and create a Gmail draft in the operator's voice. Never sends directly.

## Steps

1. **Load voice guide:**
```bash
cat ~/pureMind/templates/email-style.md
```

2. **If replying to a thread**, find the original message:
```bash
python3 ~/pureMind/.claude/integrations/gmail_integration.py search --query "from:sender subject:topic" --account hal
python3 ~/pureMind/.claude/integrations/gmail_integration.py get --id <message_id> --account hal
```

3. **Compose the draft** following email-style.md rules:
   - Match sender's tone (warm, concise, helpful)
   - Plain text only (no markdown, no HTML)
   - Sign as HAL
   - Never mention being an AI

4. **Create the draft:**
```bash
python3 ~/pureMind/.claude/integrations/gmail_integration.py create_draft \
  --to "recipient@example.com" \
  --cc "ops@puretensor.ai" \
  --subject "Re: Subject" \
  --body "Draft body text" \
  --account hal
```

5. **Show the draft** to the operator for review (recipient, subject, body, CC)

## Constraints

- **Draft only.** Never send. The operator reviews and sends from Gmail directly.
- **Always CC ops@puretensor.ai** on every email from hal@puretensor.ai. Enforced in code by `create_draft()`.
- **Accounts:** hal (default), ops, personal only. Ask the operator if unclear.
- All operations are logged to the pm_audit table.
