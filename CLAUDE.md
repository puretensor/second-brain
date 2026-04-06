# pureMind Vault

This is the pureMind second brain vault. When working in this directory:

1. Always load memory/soul.md, memory/user.md, memory/memory.md at session start.
2. Every file change is auto-committed to Git via PostToolUse hook.
3. Never store credentials, passwords, API keys, or tokens in this vault. They live in `~/.config/puremind/secrets.env` (resolved via `tools/credentials.py`).
4. memory.md must stay under 8K tokens (~5KB text). Curate aggressively.
5. Daily logs go in daily-logs/YYYY-MM-DD.md.
6. Knowledge files go in knowledge/ with clean markdown and no credential data.
7. Project context goes in projects/{name}/README.md.
8. Templates in templates/ are style guides, not executable code.

## Credential Safety
This vault is a Git repository. Everything committed becomes permanent history. Credentials are externalized to `~/.config/puremind/secrets.env` (mode 0600, outside vault) and resolved via `tools/credentials.py`. The `.gitignore` blocks `*credentials*`, `*secrets*`, `*.env`. Never hardcode secrets in Git-tracked files.

## Memory Hierarchy (MemGPT-inspired)
- **Register:** Live conversation context (ephemeral)
- **RAM:** memory/memory.md (always loaded, <8K tokens)
- **Disk:** daily-logs/, knowledge/, projects/ (searchable, not always loaded)

## Wiki Layer (Phase 10)

The wiki layer adds structure to the knowledge/ directory. Raw sources are registered in sources/, then synthesized into canonical wiki pages in knowledge/. This is a wiki-first system: answer from wiki pages first, fall back to raw sources or RAG only when wiki coverage is insufficient.

### Directory Structure

- `sources/` -- Immutable raw material (manifests, snapshots). Never edit after registration.
- `sources/manifests/` -- One .md manifest per registered source (YAML frontmatter with provenance)
- `sources/snapshots/` -- Captured markdown renderings of external content
- `sources/index.md` -- Append-only source registry
- `knowledge/index.md` -- Navigation entrypoint for the wiki (browse here first)
- `knowledge/log.md` -- Append-only changelog of wiki modifications

### Rules

1. **Register before synthesize.** External content must be registered as a source (manifest in sources/manifests/) before creating or updating wiki pages from it.
2. **Sources are immutable.** Once a manifest or snapshot is committed, it is never edited. Corrections go in new sources.
3. **knowledge/ pages are canonical.** Wiki pages in knowledge/ are the authoritative, curated content. They are the first place to look for answers.
4. **Wiki-first answering.** When answering questions, check knowledge/ wiki pages first. Use raw sources (sources/) second. Fall back to RAG search third.
5. **Append-only changelog.** Every wiki modification (create, update, archive) gets an entry in knowledge/log.md.
6. **Cross-link with wikilinks.** Use `[[page-name]]` to link between knowledge/ pages. Page names match filenames without the .md extension.
7. **Frontmatter required.** New wiki pages must include the wiki frontmatter schema (title, page_type, status, source_refs, aliases, updated). See templates/wiki-page.md.
8. **No binaries in Git.** PDFs, images, and large files stay on Ceph or external storage. Source manifests link to them via origin_path.

### Wiki Page Frontmatter

```yaml
---
title: "..."
page_type: entity|concept|overview|comparison|project|source-summary
status: seed|active|needs-review
source_refs: []
aliases: []
updated: YYYY-MM-DD
---
```

Pages created by `tools/ingest.py` retain their ingest frontmatter. Wiki fields are added alongside, not as replacements.

### Source Manifest Frontmatter

```yaml
---
source_id: src-YYYYMMDD-slug
title: "..."
origin_url: ""
origin_path: ""
captured_at: YYYY-MM-DDTHH:MM:SSZ
content_type: pdf|markdown|text|html|stdin
blob_sha256: ""
untrusted_source: true|false
snapshot_path: "sources/snapshots/..."
---
```

### Templates

- `templates/wiki-page.md` -- Wiki page template with frontmatter schema and body structure
- `templates/source-manifest.md` -- Source manifest template with field definitions

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
python3 ~/pureMind/.claude/integrations/fleet_health_integration.py quick_check --json
python3 ~/pureMind/.claude/integrations/fleet_health_integration.py deep_check --json
```

### Skills
- `/gmail` -- search inbox, read threads, create drafts
- `/github` -- list PRs/issues, read details, comment
- `/calendar` -- list upcoming events, search events
- `/alerts` -- post to pureMind Telegram alerts channel
- `/briefing` -- morning briefing combining all integrations

### Components
- `.claude/integrations/base.py` -- audit logging, rate limiting, @audited decorator
- `.claude/integrations/{gmail,github,calendar,telegram,fleet_health}_integration.py` -- wrappers
- `migrations/002_audit_log.sql` -- pm_audit table schema

## Skills Framework (Phase 5)

17 skills in `.claude/skills/`. Skills are markdown instructions that compose existing tools and integrations. All have machine-readable YAML frontmatter (inputs, outputs, writes_to, side_effects).

### Skill Library

| Skill | What It Does |
|---|---|
| `/briefing` | Morning briefing: calendar + email + pending + GitHub |
| `/puremind-search` | Hybrid RAG search with optional --graph, --hyde, --lang |
| `/gmail` | Gmail read + draft operations |
| `/github` | GitHub read + comment operations |
| `/calendar` | Calendar read-only operations |
| `/alerts` | Telegram alerts to operator |
| `/draft-email` | Compose email in operator's voice, create Gmail draft |
| `/reflect` | Manual trigger for daily reflection/promotion pipeline |
| `/project-status` | Project summary from vault, daily logs, and GitHub |
| `/diagram` | Generate Mermaid/Excalidraw diagrams |
| `/write` | Long-form writing with style templates |
| `/research` | Parallel research pipeline (quick/deep) with multi-source cross-checking |
| `/ingest` | Ingest URLs, PDFs, docs into knowledge base with provenance |
| `/self-evolve` | Create or modify skills by analyzing existing patterns |
| `/heartbeat` | Manually trigger the proactive heartbeat agent |
| `/health-sweep` | Deep fleet health sweep with parallel per-node diagnostics |
| `/migrate` | Test-driven infrastructure migration with acceptance tests |

### Content Ingestion
```bash
python3 ~/pureMind/tools/ingest.py document.pdf --title "Title" --category research --tags tag1,tag2
python3 ~/pureMind/tools/ingest.py --from-stdin --title "Title" --source-url https://example.com
```
Supports PDF (pdfplumber/PyMuPDF), markdown, text. Adds YAML frontmatter with provenance. Auto-indexes.

## Heartbeat & Proactive Agent (Phase 6)

Proactive agent running on a 30-minute systemd timer during waking hours (07:00-22:30 UTC). Four-step loop: Gather -> Reason (Claude CLI) -> Act (within permissions) -> Notify (Telegram).

### Proactivity Levels

| Level | Can Do | Start |
|---|---|---|
| **observer** | Read all, log observations. Telegram summary automatic. | Default |
| **adviser** | Observer + create email drafts, update pending | After stable observer |
| **partner** | Adviser + comment on PRs/issues, create issues | After 2+ weeks stable |

Level configured in `.claude/integrations/heartbeat_config.json`. Override per-run with `--level`.

### Usage
```bash
python3 ~/pureMind/tools/heartbeat.py                   # Normal run
python3 ~/pureMind/tools/heartbeat.py --dry-run          # Preview gathered state
python3 ~/pureMind/tools/heartbeat.py --level adviser    # Override level
python3 ~/pureMind/tools/heartbeat.py --force            # Run outside waking hours
```

### Integration JSON Output (J-01)
All integrations support `--json` flag for structured output:
```bash
python3 ~/pureMind/.claude/integrations/gmail_integration.py list_unread --account hal --json
python3 ~/pureMind/.claude/integrations/calendar_integration.py list_events --days 1 --json
python3 ~/pureMind/.claude/integrations/github_integration.py list_prs PureClaw --state open --json
python3 ~/pureMind/.claude/integrations/telegram_integration.py read_channel --json
```

### Fleet Health Monitoring

The heartbeat includes fleet-wide health checks via `fleet_health_integration.py`. Every 30-minute cycle, all 10 nodes are checked in parallel (<1s) for reachability, disk usage, and load average. Fleet alerts appear alongside email/GitHub/calendar in the Claude reasoning prompt.

```bash
python3 ~/pureMind/.claude/integrations/fleet_health_integration.py quick_check --json  # <30s heartbeat mode
python3 ~/pureMind/.claude/integrations/fleet_health_integration.py deep_check --json   # 2-3 min full sweep
python3 ~/pureMind/.claude/integrations/fleet_health_integration.py quick_check --node fox-n1 --json
```

### Migration Test Runner

Test-driven migration validation tool. Discovers `test_*` bash functions, runs them, and implements 3-consecutive-failure stop logic.

```bash
python3 ~/pureMind/tools/migrate_test_runner.py /tmp/tests.sh --json     # Run all tests
python3 ~/pureMind/tools/migrate_test_runner.py /tmp/tests.sh --test test_dns  # Single test
```

### Components
- `tools/heartbeat.py` -- main orchestrator (gather/reason/act/notify loop)
- `tools/migrate_test_runner.py` -- bash test discovery and execution with stop logic
- `.claude/integrations/heartbeat_config.json` -- repos, accounts, thresholds, fleet health config
- `.claude/integrations/fleet_health_integration.py` -- parallel SSH fleet health checks
- `puremind-heartbeat.timer` + `.service` -- systemd timer (every 30 min, 07:00-22:30 UTC)
- `daily-logs/heartbeat-log.jsonl` -- structured heartbeat result log

## Knowledge Graph & Advanced Retrieval (Phase 7)

Entity-relationship graph over vault content, stored in PostgreSQL JSONB adjacency lists. Enables relationship-aware retrieval, HyDE for vague queries, and hierarchical summaries.

### Entity Graph
```bash
python3 ~/pureMind/tools/extract.py                    # Incremental extraction
python3 ~/pureMind/tools/extract.py --full              # Full re-extraction
python3 ~/pureMind/tools/extract.py --file <path>       # Single file
```

Entity types: person, project, technology, concept, decision, event.
Relationship types: mentions, depends_on, part_of, works_on, uses, decided, created_by.

### Graph-Augmented Search
```bash
python3 ~/pureMind/tools/search.py "query" --graph      # Traverse entity graph + hybrid
python3 ~/pureMind/tools/search.py "query" --hyde        # Hypothetical document embeddings
python3 ~/pureMind/tools/search.py "query" --lang simple # Non-English FTS (unaccent)
```

### Hierarchical Summaries
```bash
python3 ~/pureMind/tools/summarize.py --file <path>     # File-level summary
python3 ~/pureMind/tools/summarize.py --project <name>  # Project-level summary
python3 ~/pureMind/tools/summarize.py --period START END # Date range summary
python3 ~/pureMind/tools/summarize.py --build-all       # Full summary tree
```

### Schema
- `pm_entities` -- entities with types, descriptions, source chunk references
- `pm_relationships` -- directed edges with types, weights, evidence chunks
- `pm_summaries` -- hierarchical summaries (file/project/period/vault) with embeddings
- `migrations/003_knowledge_graph.sql` -- schema definition

### Components
- `tools/extract.py` -- entity extraction via Claude CLI (single-turn)
- `tools/summarize.py` -- RAPTOR-style hierarchical summaries
- `tools/search.py` -- graph_search(), hyde_search(), --lang support added
- `tools/db.py` -- shared DB connection (Phase 7 H-02 refactor)
- Daily reflection auto-extracts entities from today's log

## Security Hardening (Phase 8)

Credentials, content sanitization, audit hardening, and injection testing. Full details in `SECURITY.md`.

### Credential Management
Secrets resolved via `tools/credentials.py`: env var > `~/.config/puremind/secrets.env` (0600) > fail closed (RuntimeError). Never hardcode credentials in Git-tracked files.

### Content Sanitization
All external content passes through `tools/sanitize.py` before entering Claude prompts. Four layers: control char removal, injection pattern stripping, fence escaping, size enforcement. Applied in extract.py, summarize.py, heartbeat.py, ingest.py.

### Audit Trail
Every integration call logged to `pm_audit`. JSONL fallback at `~/.cache/puremind/audit_fallback.jsonl` when DB unavailable. Rate limiter in `$XDG_RUNTIME_DIR/puremind_rate/` (0700).

### Testing
```bash
python3 -m pytest tests/test_sanitize.py -v    # Fast (30 tests, <1s)
python3 -m pytest tests/test_injection.py -v   # Integration (Claude CLI)
```

### Components
- `tools/credentials.py` -- secret resolution (env > file > fallback)
- `tools/sanitize.py` -- content sanitization pipeline
- `tests/payloads.json` -- 8-category attack payload library
- `tests/test_sanitize.py` -- fast sanitization unit tests
- `tests/test_injection.py` -- Claude CLI integration tests
- `requirements.txt` -- pinned dependency versions
- `SECURITY.md` -- threat model, quarterly review checklist

## Evaluation & Ops Maturity (Phase 9)

Measurable quality, monitoring, and operational documentation.

### Eval Harness
Weekly evaluation of 6 metrics: retrieval quality (Recall@k, MRR, nDCG), generation faithfulness, personalisation, latency, security, cost. Results in `pm_eval_runs` table.
```bash
python3 ~/pureMind/tools/eval_harness.py              # Full eval (weekly timer)
python3 ~/pureMind/tools/eval_harness.py --dry-run     # Preview
python3 ~/pureMind/tools/eval_harness.py --json        # JSON output
```

### Golden Dataset
50+ query-answer pairs with ground-truth chunk IDs for retrieval evaluation.
```bash
python3 ~/pureMind/tools/eval_golden.py stats          # Dataset stats
python3 ~/pureMind/tools/eval_golden.py seed --count 20  # Generate more pairs
python3 ~/pureMind/tools/eval_golden.py --list          # List all pairs
```

### Metrics & Monitoring
15-minute collector writes system health to `pm_metrics` table. Grafana dashboard at fox-n1:30302.
```bash
python3 ~/pureMind/tools/metrics_collector.py --json   # Current metrics
bash ~/pureMind/ops/deploy_dashboard.sh                # Deploy/update Grafana dashboard
```

### Alerting
Threshold-based alerts via Telegram (@puretensor_alert_bot). Deduplication: 1 alert/metric/hour.

### Systemd Timers
| Timer | Schedule |
|---|---|
| `puremind-eval.timer` | Saturday 04:00 UTC (weekly) |
| `puremind-metrics.timer` | Every 15 minutes |

### Testing
```bash
python3 -m pytest tests/test_eval.py -v               # Eval metric tests (22 tests)
```

### Components
- `tools/eval_harness.py` -- weekly evaluation (6 metrics)
- `tools/eval_golden.py` -- golden QA dataset builder
- `tools/metrics_collector.py` -- 15-min health collector + alerting
- `ops/grafana/puremind-overview.json` -- Grafana dashboard
- `ops/deploy_dashboard.sh` -- dashboard deployment script
- `ops/RUNBOOK.md` -- operational runbook
- `tests/test_eval.py` -- eval metric unit tests
- `migrations/004_eval_ops.sql` -- database schema
