---
name: briefing
description: Morning briefing combining calendar, email, pending items, and GitHub activity
---

# Morning Briefing

Generate a morning briefing by querying all Phase 4 integrations and pureMind memory.

## Steps

1. **Calendar:** Get today's and tomorrow's events
```bash
python3 ~/pureMind/.claude/integrations/calendar_integration.py list_events --days 2 --account ops
```

2. **Email:** Check unread emails on hal account
```bash
python3 ~/pureMind/.claude/integrations/gmail_integration.py list_unread --account hal
```

3. **Pending items:** Read pending.md for time-sensitive follow-ups
```bash
cat ~/pureMind/memory/pending.md
```

4. **GitHub:** Check open PRs across key repos
```bash
python3 ~/pureMind/.claude/integrations/github_integration.py list_prs nexus --state open
```

5. **Memory:** Search for any relevant context
```bash
python3 ~/pureMind/tools/search.py "pending deadline overdue" --limit 3
```

## Output Format

Present a concise briefing with:
- Today's schedule (from calendar)
- Priority emails requiring attention
- Pending items with deadlines
- Open PRs/issues needing review
- Any overdue action items from memory

Keep it to one screen. Prioritise by urgency.
