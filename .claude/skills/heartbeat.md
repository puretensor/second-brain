---
name: heartbeat
description: Manually trigger the proactive heartbeat agent (gather/reason/act loop)
inputs: [proactivity_level_override]
outputs: [heartbeat_summary, actions_taken]
writes_to: [daily-logs/, memory/pending.md]
side_effects: [gmail_draft, pr_comment, telegram_alert, audit_log]
---

# Heartbeat

Manually trigger the pureMind heartbeat agent. The heartbeat gathers state from all integrations, sends it to Claude for reasoning, executes allowed actions within the configured proactivity level, and posts a summary to Telegram.

## Usage

### Preview (dry run -- no Claude call, no actions)
```bash
python3 ~/pureMind/tools/heartbeat.py --dry-run
```

### Normal run (uses config proactivity level)
```bash
python3 ~/pureMind/tools/heartbeat.py
```

### Override proactivity level
```bash
python3 ~/pureMind/tools/heartbeat.py --level adviser
python3 ~/pureMind/tools/heartbeat.py --level partner
```

### Force run outside waking hours
```bash
python3 ~/pureMind/tools/heartbeat.py --force
```

## Proactivity Levels

| Level | Can Do | Cannot Do |
|---|---|---|
| **observer** | Read all, log observations | No drafts, no comments, no issues. Telegram summary posted automatically. |
| **adviser** | Observer + create email drafts, update pending | No PR/issue comments, no issue creation |
| **partner** | Adviser + comment on PRs/issues, create issues | No send, no merge, no delete |

The level is set in `~/pureMind/.claude/integrations/heartbeat_config.json` and can be overridden per-run.

## What It Gathers

1. Calendar events (today)
2. Unread emails (hal account)
3. Open PRs across watched repos
4. Recent Telegram alerts
5. Pending items from pending.md
6. Vault search for deadline/overdue context

## Cron Schedule

The heartbeat runs automatically every 30 minutes from 07:00-22:30 UTC via `puremind-heartbeat.timer`. Use `/heartbeat` for manual triggers outside the schedule.

## Constraints

- All actions respect Phase 4 integration permissions (draft-only for email, read+comment for GitHub, read-only for calendar)
- All integration calls are logged to pm_audit via @audited decorator
- Claude CLI invoked via `claude -p --output-format json --max-turns 1` (single-turn, bounded)
- Results logged to heartbeat-log.jsonl and daily log
