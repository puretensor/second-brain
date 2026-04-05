# pureMind Vault

This is the pureMind second brain vault. When working in this directory:

1. Always load memory/soul.md, memory/user.md, memory/memory.md at session start.
2. Every file change is auto-committed to Git via PostToolUse hook.
3. Never store credentials, passwords, API keys, or tokens in this vault. They live in ~/.claude/ memory only.
4. memory.md must stay under 8K tokens (~5KB text). Curate aggressively.
5. Daily logs go in daily-logs/YYYY-MM-DD.md.
6. Knowledge files go in knowledge/ with clean markdown and no credential data.
7. Project context goes in projects/{name}/README.md.
8. Templates in templates/ are style guides, not executable code.

## Credential Safety
This vault is a Git repository. Everything committed becomes permanent history. The .gitignore blocks common patterns, but the primary defence is discipline: never write credentials here. Reference them by pointer ("see ~/.claude/ memory") instead.

## Memory Hierarchy (MemGPT-inspired)
- **Register:** Live conversation context (ephemeral)
- **RAM:** memory/memory.md (always loaded, <8K tokens)
- **Disk:** daily-logs/, knowledge/, projects/ (searchable, not always loaded)

## Daily Log Schema

Each file in `daily-logs/` is named `YYYY-MM-DD.md`. Logs are structured capture appended throughout the day. Phase 2 hooks write to these automatically.

```markdown
# YYYY-MM-DD

## Session: <session-id or time>
**Context:** <what was the user working on>

### Work Done
- <concrete action taken>

### Decisions
- <decision made and rationale>

### New Facts
- <facts learned that may be promoted to memory.md>

### Pending
- [ ] <action item carried forward>
```

Multiple sessions per day append new `## Session:` blocks. Session boundaries are marked by `---` separators (written by SessionEnd hook).

## Lifecycle Hooks (Phase 2)

Lifecycle hooks are registered in `~/.claude/settings.json`. The three CC event hooks live at `~/tensor-scripts/hooks/`. The daily reflection script lives at `~/pureMind/.claude/hooks/daily_reflect.py` and runs via systemd timer, not CC events.

### SessionStart (`cc_session_start.py`)
Loads identity stack into context with per-section byte budgets (identity 1800B, profile 1800B, memory 1800B, pending 400B, daily logs 1800B, Nexus 400B). Source resolution: pureMind vault first (`~/pureMind/memory/soul.md`, `user.md`, `memory.md`), legacy `~/.claude/` fallback. Also loads `pending.md` and `hal_digest.md` (from Nexus, legacy path only).

### PreCompact (`cc_pre_compact.py`)
Fires before context compression. Appends `### Compaction Extract` to today's daily log (pureMind primary). Optional Nemotron fact extraction. Git commits the daily log. Injects recovery context (soul.md + recent activity + TOOLS.md) for post-compact continuity.

### SessionEnd (`cc_session_end.py`)
Runs in background on exit. Appends `---` session boundary to daily log. Git commits. Logs metadata to `~/.claude/session_log.jsonl`.

### Daily Reflection (`daily_reflect.py`)
Systemd timer at 23:00 UTC (`puremind-reflect.timer`). Uses Claude CLI (`claude -p`) to analyze today's daily log against current memory.md. Fetches historical context via RAG search before reflection (Phase 3). Promotes durable knowledge to RAM, resolves pending items, archives logs >30 days old. Dry-run: `python3 ~/pureMind/.claude/hooks/daily_reflect.py --dry-run`.

## Search & Retrieval (Phase 3)

Hybrid RAG using pgvector + PostgreSQL FTS with Reciprocal Rank Fusion. Data stored in `puremind_chunks` table in the `vantage` database (fox-n1:30433).

### Search
```bash
python3 ~/pureMind/tools/search.py "<query>" --limit 5
```
Options: `--json`, `--file-filter prefix`, `--limit N`. Also available as `/puremind-search` skill.

### Indexing
Auto-indexes on vault file changes via PostToolUse hook. Manual:
```bash
python3 ~/pureMind/tools/index.py            # Incremental (changed files)
python3 ~/pureMind/tools/index.py --full      # Full re-index
```

### Components
- `tools/chunker.py` -- heading-aware markdown chunker (2048-char max, 20% overlap)
- `tools/embed.py` -- nomic-embed-text-v1.5 (768-dim) via sentence-transformers
- `tools/index.py` -- full + incremental indexing with SHA-256 change detection
- `tools/search.py` -- hybrid BM25+vector search with RRF fusion (k=60)
- `migrations/001_puremind_rag.sql` -- database schema

## Direct Integrations (Phase 4)

Permission-enforced wrappers in `.claude/integrations/` over existing tools. Every call logged to `pm_audit` table.

### Permission Model

| Integration | Read | Write | Blocked |
|---|---|---|---|
| Gmail | search, get, list_inbox, list_unread | create_draft only | send, reply, trash, delete, spam, filters |
| GitHub | list_repos, list_prs, list_issues, get_pr, get_issue | comment_pr, comment_issue, create_issue | merge, push, close, delete |
| Calendar | list_events, get_event, search_events | None (read-only) | create, update, delete |
| Telegram | read_channel (filtered to alerts chat) | post_alert (configured chat only) | DMs, other chats |

Gmail accounts restricted to: hal (default), ops, personal. Write ops fail closed if audit DB unavailable.

### Usage
```bash
python3 ~/pureMind/.claude/integrations/gmail_integration.py search --query "invoice" --account hal
python3 ~/pureMind/.claude/integrations/github_integration.py list_prs PureClaw --state open
python3 ~/pureMind/.claude/integrations/calendar_integration.py list_events --days 2 --account ops
python3 ~/pureMind/.claude/integrations/telegram_integration.py post_alert "Deployment complete"
```

### Skills
- `/gmail` -- search inbox, read threads, create drafts
- `/github` -- list PRs/issues, read details, comment
- `/calendar` -- list upcoming events, search events
- `/alerts` -- post to pureMind Telegram alerts channel
- `/briefing` -- morning briefing combining all integrations

### Components
- `.claude/integrations/base.py` -- audit logging, rate limiting, @audited decorator
- `.claude/integrations/{gmail,github,calendar,telegram}_integration.py` -- wrappers
- `migrations/002_audit_log.sql` -- pm_audit table schema

## Skills Framework (Phase 5)

14 skills in `.claude/skills/`. Skills are markdown instructions that compose existing tools and integrations.

### Skill Library

| Skill | What It Does |
|---|---|
| `/briefing` | Morning briefing: calendar + email + pending + GitHub |
| `/puremind-search` | Hybrid RAG search over vault (BM25 + pgvector) |
| `/gmail` | Gmail read + draft operations |
| `/github` | GitHub read + comment operations |
| `/calendar` | Calendar read-only operations |
| `/alerts` | Telegram alerts to operator |
| `/draft-email` | Compose email in operator's voice, create Gmail draft |
| `/reflect` | Manual trigger for daily reflection/promotion pipeline |
| `/project-status` | Project summary from vault, daily logs, and GitHub |
| `/diagram` | Generate Mermaid/Excalidraw diagrams |
| `/write` | Long-form writing with style templates |
| `/research` | Vault-first deep research with web fallback and citations |
| `/ingest` | Ingest URLs, PDFs, docs into knowledge base with provenance |
| `/self-evolve` | Create or modify skills by analyzing existing patterns |

### Content Ingestion
```bash
python3 ~/pureMind/tools/ingest.py document.pdf --title "Title" --category research --tags tag1,tag2
python3 ~/pureMind/tools/ingest.py --from-stdin --title "Title" --source-url https://example.com
```
Supports PDF (pdfplumber/PyMuPDF), markdown, text. Adds YAML frontmatter with provenance. Auto-indexes.
