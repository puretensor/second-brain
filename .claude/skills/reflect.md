---
name: reflect
description: Manually trigger the daily reflection/promotion pipeline
---

# Reflect

Run the daily reflection process on demand. Analyzes today's (or a specific day's) daily log, promotes high-signal items to memory.md, updates pending.md, and archives old logs.

## Usage

### Preview changes (dry run)
```bash
python3 ~/pureMind/.claude/hooks/daily_reflect.py --dry-run
```

### Run reflection for today
```bash
python3 ~/pureMind/.claude/hooks/daily_reflect.py
```

### Run reflection for a specific date
```bash
python3 ~/pureMind/.claude/hooks/daily_reflect.py --date 2026-04-05
```

## What It Does

1. Reads the daily log for the target date
2. Extracts topics and searches vault via hybrid RAG for historical context
3. Invokes Claude CLI to analyze: key decisions, lessons, facts, preference updates
4. Promotes high-signal items to `memory/memory.md` (enforces 5120-byte cap)
5. Updates `memory/pending.md` with new action items or resolved items
6. Archives daily logs older than 30 days to `knowledge/archive/`
7. Git commits changes and triggers incremental re-index

## After Running

Show the operator:
- Items added to memory.md
- Items removed from memory.md
- Pending items updated
- Summary of the reflection

## Constraints

- The nightly cron runs this automatically at 23:00 UTC. Use `/reflect` for on-demand runs.
- Always use `--dry-run` first if unsure about the changes.
- memory.md must stay under 5120 bytes. The script enforces this.
