---
name: reflect
description: Manually trigger the daily reflection/promotion pipeline
inputs: [date_override]
outputs: [reflection_summary]
writes_to: [memory/memory.md, memory/pending.md]
side_effects: [log_archival, git_commit, incremental_reindex]
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
- Always use `--dry-run` first if unsure about the changes. Dry-run shows proposed add/remove/pending changes without applying them.
- memory.md must stay under 5120 bytes. The script enforces this.
- **Idempotency note:** if `/reflect` runs at 14:00 and the cron fires at 23:00, the cron will re-process the same day's log. The reflection script is additive (promotes new items, resolves pending), so duplicate runs may propose the same promotions twice. Use `--dry-run` at 23:00 to check before the cron if you ran an earlier manual reflection.
- Show the operator the full dry-run output (proposed memory additions, removals, pending updates) before running without `--dry-run`.
