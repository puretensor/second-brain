# pureMind -- Second Brain Multi-Phase Implementation Plan

**PT-2026-SB v2 | 2026-04-04 | Confidential**
Author: Helgi Heimir Helgason, Founder & CEO

A sovereign second brain built on **Claude Code CLI (Max 20x subscription)** and **Obsidian**, running on PureTensor's TRINITY cluster. No external API calls, no local model inference -- the Max 20x subscription is the sole LLM layer. Claude Code is both the interface and the engine. Enriched with OpenClaw-inspired memory architecture, pgvector hybrid RAG, and systematic security hardening against the lethal trifecta.

**Core stack:** Claude Code CLI (Max 20x) | Obsidian vault (Markdown-native) | pgvector + PostgreSQL FTS on TRINITY | sentence-transformers (CPU) for embeddings | Anthropic Agent SDK for programmatic invocation | Git for versioning | Slack for notifications

---

## 1. Design Principles

pureMind is a cognitive augmentation system -- not a chatbot wrapper. It captures your evolving worldview, retrieves it under time pressure, and helps you act. The architecture follows one overriding constraint: **Claude Code CLI on your Max 20x subscription is the only LLM**. No API keys, no token counting, no model routing. You talk to Claude Code; Claude Code talks to your vault.

- **Single LLM, no routing.** Claude Code (Max 20x) handles everything: reasoning, summarisation, extraction, writing, agent planning. The subscription absorbs all inference cost at a flat $200/month. The Agent SDK invokes Claude Code programmatically for cron-driven tasks (heartbeat, reflection).
- **Sovereign by default.** All raw data stays on TRINITY. No data sent anywhere except through Claude Code's own connection to Anthropic (which is the subscription you're already paying for).
- **Markdown-native.** Knowledge lives as plain Markdown in Obsidian -- portable, diffable, Git-versioned.
- **Simple composable patterns.** Claude Code + skills + hooks. No framework bloat. No LangChain, no LlamaIndex. Skills are Markdown instructions. Hooks are bash/Python scripts.
- **Incremental trust.** Start read-only on all integrations. Add write capabilities per-service with explicit allowlists.
- **Compounding memory.** Every conversation feeds the daily log. Daily reflection promotes durable knowledge. The system gets smarter with every session.
- **Provenance as content.** Every chunk, every agent action has source, timestamp, and transformation lineage.
- **Evaluation-driven.** Retrieval quality measured, not vibed. Regression tests for RAG. Adversarial tests for security.

---

## 2. Architecture Overview

Five planes, one LLM. Claude Code is the reasoning layer across all of them.

| Plane | Function | Implementation |
|-------|----------|----------------|
| Capture | Connectors and inboxes for raw artefacts | Python scripts called by Claude Code skills. OAuth tokens managed locally. File watchers (inotifywait) for Obsidian vault changes. |
| Processing | Parsing, chunking, embedding, entity extraction | sentence-transformers (CPU, on TRINITY) for embeddings. Claude Code for summarisation, entity extraction, metadata enrichment. Apache Tika for format detection. |
| Knowledge | Raw store + canonical store + indexes + versioning | Obsidian vault (canonical Markdown). pgvector for dense vectors. PostgreSQL FTS for lexical. Ceph for raw binary artefacts. Git for versioning. |
| Interaction | Search, Q&A, writing, meeting prep | Claude Code CLI as primary interface. Slack bot (via Agent SDK) as secondary. Obsidian as visual canvas. |
| Action | Agent workflows, tool execution, memory write-back | Claude Code skills + hooks. Agent SDK for programmatic invocation (heartbeat, reflection crons). All actions logged. |

### Why Max 20x Instead of API

The Max 20x subscription at $200/month is a flat-rate ceiling. Heavy Claude Code usage that would cost $1,000+ at API rates is absorbed by the subscription. The Agent SDK can invoke Claude Code programmatically for background tasks (heartbeat, daily reflection) without API keys or token budgets. This eliminates an entire class of cost management, routing, and credential infrastructure. The tradeoff is rate limits -- but Max 20x provides 20x Pro capacity with weekly resets, which is ample for a single-user second brain with well-designed caching and context management.

> *Embedding is the one function Claude Code cannot do natively. We use sentence-transformers on CPU (TRINITY has 128 cores) for embedding generation. This is a lightweight, zero-cost addition that runs entirely locally.*

---

## Phase 1 -- Memory Foundation

*Days 1-3 | Prerequisite: None | Outcome: Core memory layer operational in Obsidian*

OpenClaw-inspired memory files in a Git-backed Obsidian vault. These three files are the persistent identity of pureMind.

- **soul.md** -- Agent constitution. Communication style, decision-making frameworks, risk tolerance, explicit red lines (never send without approval, never delete production data, never expose credentials). This is your agent's personality and constraints.
- **user.md** -- Auto-evolving profile. Current projects, preferences, communication style exemplars, domain vocabulary, key contacts, schedule patterns. Starts manually seeded from existing pureClaw/Immune context.
- **memory.md** -- Rolling promoted knowledge. Key decisions, lessons, facts, project state, pending items. Target: 8K tokens max. Oldest entries archived. Always loaded into every Claude Code session.

### Vault Directory Layout

```
pureMind/
  memory/
    soul.md          # Agent constitution and red lines
    user.md          # Auto-evolving owner profile
    memory.md        # Promoted durable knowledge (8K cap)
  daily-logs/
    2026-04-04.md    # Raw conversation dumps per day
  knowledge/
    puretensor/      # Company context, infra docs
    research/        # Papers, technical notes
    contacts/        # Key people and relationships
  projects/
    pureclaw/        # Active project context files
    immune-system/
    puremind/
  templates/
    email-style.md   # Writing style exemplars
    briefing-note.md # Output templates
  .claude/
    settings.json    # Claude Code project config
    commands/        # Slash commands
    skills/          # Claude Code skill definitions
    hooks/           # session-start, pre-compact, session-end
```

- **Vault structure** -- `pureMind/memory/` (core files), `daily-logs/` (one file per day), `knowledge/` (curated reference), `projects/` (active project context), `templates/` (style packs, output templates), `.claude/` (settings, hooks, skills).
- **Git init.** Entire vault is a Git repo. Every memory write commits with a structured message. Time-travel over your knowledge base. Consistent with versioned-knowledge principles (Delta Lake / lakeFS pattern).

---

## Phase 2 -- Context Persistence & Hooks

*Days 4-6 | Prerequisite: Phase 1 | Outcome: Automatic memory loading, conversation capture, promotion pipeline*

Claude Code hooks make memory persistent across sessions. Three hooks form the core loop. A daily cron runs the reflection/promotion process via the Agent SDK.

### Hook Definitions

- **session-start** -- Bash script in `.claude/hooks/`. Reads soul.md + user.md + memory.md and injects into Claude Code context as a structured prefix. Also loads today's daily log (if exists) and any active project context from projects/.
- **pre-compact** -- Triggered when conversation approaches context limits. Appends the full conversation (with timestamps) to today's daily log before compaction. Extracts explicit decisions, action items, new facts. Prevents knowledge loss.
- **session-end** -- On /exit or termination: dump conversation to daily log. Run quick extraction (Claude Code itself does this as a final prompt) to identify: key decisions, new facts, preference signals, action items. Stage extracted items for daily reflection. Git commit the vault.

### Daily Reflection (Cron)

A cron job (23:00 UTC daily) invokes Claude Code via the **Anthropic Agent SDK** programmatically -- not an interactive session. It reads today's daily log and runs a structured promotion pipeline:

- **Extract** -- Key decisions, lessons, important facts, preference updates, project state changes.
- **Score** -- Each candidate scored for promotion (recency, frequency of reference, explicit emphasis, cross-topic relevance).
- **Promote** -- High-score items added to memory.md. Displaced items archived to `memory-archive/`.
- **Update** -- user.md refreshed if new preferences or context detected.
- **Commit** -- Git commit with structured message: `reflect: promoted 4 items, updated user.md`.
- **Notify** -- Optional Slack message: 'Daily reflection complete. Promoted N items.'

> *This implements the MemGPT memory hierarchy: daily logs = disk, memory.md = RAM (always in context), live conversation = register. The reflection process is the single most important mechanism for long-term compounding intelligence.*

---

## Phase 3 -- Memory Search & Hybrid RAG

*Days 7-12 | Prerequisite: Phase 2 | Outcome: Searchable indexed memory with hybrid retrieval*

memory.md can only hold ~8K tokens. The real power comes from searching all daily logs, knowledge docs, and project files. Hybrid retrieval on pgvector (already deployed for pureClaw) plus PostgreSQL full-text search.

### Schema (PostgreSQL + pgvector)

```sql
CREATE TABLE pm_documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_path TEXT NOT NULL,       -- vault-relative path
  chunk_index INT NOT NULL,
  content TEXT NOT NULL,
  embedding vector(768),           -- all-MiniLM-L6-v2 or similar
  content_tsv tsvector GENERATED ALWAYS AS
    (to_tsvector('english', content)) STORED,
  source_type TEXT,                -- daily-log|knowledge|project|template
  metadata JSONB,                  -- provenance, tags, entities
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_pm_embedding ON pm_documents USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_pm_fts ON pm_documents USING gin (content_tsv);
CREATE INDEX idx_pm_source ON pm_documents (source_type, created_at DESC);
```

### Embedding Pipeline

sentence-transformers on CPU (TRINITY's 128 cores handle this trivially). Model: all-MiniLM-L6-v2 (768-dim, fast, good baseline) -- evaluate alternatives via MTEB later. File watcher (inotifywait) triggers re-embedding on vault file changes. Chunking: semantic paragraphs, 512-token target, 128-token overlap. Nightly batch re-index as safety net.

### Retrieval Pipeline

- **Hybrid search.** Execute vector similarity (pgvector HNSW, cosine) and lexical search (PostgreSQL FTS, ts_rank) in parallel. Combine via Reciprocal Rank Fusion (RRF).
- **Metadata filtering.** Scope by source_type, date range, JSONB fields. 'Only daily logs from this week', 'only pureClaw project docs'.
- **Reranking.** Claude Code itself acts as the reranker -- present top-k candidates in context and ask it to select the most relevant. No separate reranker model needed.
- **Context packing.** Selected chunks formatted with source citations and injected into Claude Code's context alongside the user's query. Claude Code generates grounded answers.

> *The key insight: Claude Code itself is the reranker and generator. No separate model needed. A Claude Code skill (`/search-memory`) wraps the entire pipeline: query -> Python script does pgvector+FTS search -> results injected into Claude Code context -> Claude Code reasons over them and answers with citations.*

---

## Phase 4 -- Direct Integrations

*Days 13-18 | Prerequisite: Phase 1 | Outcome: Controlled read/write access to external services*

The lethal trifecta (private data access + untrusted content + exfiltration vectors) is always present in a useful second brain. Every integration is exposed via a thin Python wrapper that Claude Code skills call. Permissions are hardcoded in the wrapper -- Claude Code cannot bypass them.

### Permission Model

| Integration | Read | Write | Constraints |
|---|---|---|---|
| Gmail | Inbox search, thread reading | Draft only (no send) | Drafts require explicit /approve command before send. |
| Slack | All channels | #puremind-alerts only | Cannot DM. Cannot post to external channels. |
| GitHub | Repos, PRs, issues | Comments on PRs, create issues | Cannot merge. Cannot push to main. |
| Google Calendar | Event listing | None | Read-only. No event creation. |
| Obsidian vault | Full vault | Via Git commits | All writes committed with provenance. |
| Cluster monitoring | Status, logs, metrics | None | Read-only. Fleet actions go through Immune system. |

### Integration Pattern

Each integration is a standalone Python module in `.claude/integrations/`. OAuth tokens stored in local keyring (never in code). Each module exposes a small set of functions matching the permission model above. A Claude Code skill describes the available functions and their constraints. Claude Code calls the Python module via bash -- the module enforces boundaries.

- **Consistent interface.** Every integration module exposes: `list()`, `get(id)`, `search(query)`, and optionally `create_draft()` / `comment()`. Claude Code can one-shot new integrations by referencing existing ones.
- **Audit logging.** Every call logged to PostgreSQL: timestamp, integration, function, parameters, result status.
- **Rate limiting.** Per-integration rate limits in the Python wrapper prevent runaway agent loops.
- **Token hygiene.** OAuth refresh handled by the module. Tokens stored in OS keyring, never in Obsidian vault or Git.

---

## Phase 5 -- Skills Framework

*Days 19-24 | Prerequisite: Phases 1-4 | Outcome: Library of Claude Code skills for repeatable capabilities*

Skills are Markdown instructions in `.claude/skills/` that Claude Code loads on demand. No MCP servers needed. The memory layer powers all skills with personalised context.

| Skill | What It Does | Memory Integration |
|---|---|---|
| /research | Deep research: vault first, then web. Produces Obsidian note with citations. | Checks knowledge/ for priors. References user.md focus areas. |
| /draft-email | Draft email in your voice via Gmail integration. | Loads templates/email-style.md and user.md communication prefs. |
| /briefing | Morning briefing: calendar, priority emails, project status, pending items. | Reads memory.md for pending items. Queries integrations for live state. |
| /reflect | Manual trigger for the daily reflection/promotion process. | Full promotion pipeline, same as the nightly cron. |
| /project-status | Project summary from daily logs, GitHub, project context. | Scoped search of daily-logs/ and projects/ for named project. |
| /diagram | Mermaid/Excalidraw diagrams from natural language. | References existing diagrams for style consistency. |
| /write | Long-form writing in your voice. Blog posts, docs, reports. | Loads style exemplars from templates/. Applies user.md tone. |
| /ingest | Manually ingest a URL, PDF, or doc into the knowledge base. | Parses, chunks, embeds, stores with provenance metadata. |
| /search-memory | Explicit hybrid search across the full indexed vault. | Full Phase 3 retrieval pipeline with formatted results. |
| /self-evolve | pureMind creates or modifies its own skills based on usage patterns. | References .claude/skills/ to maintain consistent patterns. |

> */self-evolve is the compounding mechanism. pureMind creates new integrations and skills by referencing its own codebase and memory of past implementations. This is how the system grows capabilities without you writing boilerplate.*

---

## Phase 6 -- Heartbeat & Proactive Agent

*Days 25-30 | Prerequisite: Phases 1-5 | Outcome: pureMind acts proactively without prompting*

The heartbeat transforms pureMind from reactive to proactive. A cron-triggered process gathers state from all integrations, invokes Claude Code via the Agent SDK to reason about it, acts within permission boundaries, and notifies you via Slack.

- **Gather (deterministic).** Python script on cron (every 30 min, waking hours). Queries each integration for current state: unread emails, pending PRs, calendar events, Slack mentions, GitHub notifications, cluster health. Pure API calls, no LLM.
- **Reason (Claude Code via Agent SDK).** Gathered context + soul.md + memory.md sent to Claude Code programmatically. Structured prompt: What needs attention? What can I handle within my permissions? What should I alert about?
- **Act (bounded).** Within Phase 4 permissions: draft replies, comment on PRs, update project status in Obsidian, log decisions to daily log. All actions logged.
- **Notify.** Structured summary to #puremind-alerts in Slack. Actions taken, items needing your attention, priority ranking. Reply in Slack thread to continue.

### Proactivity Levels

| Level | Description | Start Here? |
|---|---|---|
| Observer | Read-only. Reports state, never acts. | Good for week 1 of heartbeat. |
| Adviser | Reads + drafts. Never sends or publishes. | **Default target.** Drafts for approval. |
| Partner | Acts within tight boundaries (e.g., auto-label emails, post status updates). | Earn this after 2+ weeks of Adviser with no incidents. |
| Autonomous | Full delegation in defined domains. Escalates only novel situations. | Future state. Requires strong eval framework (Phase 9). |

---

## Phase 7 -- Knowledge Graph & Advanced Retrieval

*Days 31-40 | Prerequisite: Phase 3 | Outcome: Relationship-aware retrieval*

Your ideas are linked by narrative ('what led me to believe X?'), not just topical similarity. A knowledge graph adds relationship-first reasoning on top of hybrid retrieval.

- **Entity extraction.** Claude Code processes vault content (via /ingest or batch) to extract entities (people, projects, technologies, decisions, concepts) and relationships. Store as a property graph in PostgreSQL JSONB adjacency lists -- no Neo4j needed at this scale.
- **GraphRAG retrieval.** For relationship queries, traverse the graph to find connected entities, then retrieve their source chunks via pgvector. Augments similarity search with structural context.
- **Auto-update.** Daily reflection also extracts entities/relationships from new daily logs.
- **HyDE.** For ambiguous queries: Claude Code generates a hypothetical answer, Python embeds it, uses that embedding for retrieval. Improves recall on vague questions.
- **Hierarchical summaries (RAPTOR-style).** Build tree-structured summaries over long document collections (e.g., all daily logs for a project). Retrieve at the right abstraction level.

---

## Phase 8 -- Security Hardening

*Days 41-48 | Prerequisite: Phases 1-6 | Outcome: Systematic lethal trifecta defence*

| Surface | Threats | Mitigations |
|---|---|---|
| Data plane | Unauthorised vault access. Embedding/backup leakage. | Disk encryption (LUKS). Tailscale network segmentation. Ceph RBAC. Backup encryption. |
| Model plane | Prompt injection via ingested emails/web. System prompt leakage. | Input sanitisation before context injection. Instruction hierarchy (soul.md always wins). No secrets in prompts. |
| Tool plane | Agent calls dangerous API. Supply chain compromise. | Python wrapper allowlists (Phase 4). Human-in-the-loop for send/delete/publish. Dependency pinning. |
| Governance | Ingesting restricted data. Retention violations. Audit gaps. | Source classification labels. Retention policies. Full audit logging. Quarterly review. |

- **Content sanitisation.** All external content (emails, web) passes through a sanitisation step before entering any Claude Code context. Strip instruction-like patterns.
- **Instruction hierarchy.** soul.md always takes precedence. Ingested content explicitly framed as 'data to reason about', never 'instructions to follow'.
- **Output validation.** Agent tool calls validated against allowlist before execution.
- **Red team testing.** Monthly: craft malicious emails with prompt injection payloads. Verify no escape.

---

## Phase 9 -- Evaluation & Operational Maturity

*Days 49-56 | Prerequisite: All phases | Outcome: Measurable quality, monitoring, sustainable ops*

| Metric | What to Measure | Tooling |
|---|---|---|
| Retrieval quality | Recall@k, MRR, nDCG over internal test queries from actual usage. | RAGAS eval harness. 50+ query-answer pairs from daily logs. |
| Generation quality | Faithfulness, attribution accuracy, refusal correctness. | RAGAS faithfulness. Weekly manual spot-checks. |
| Personalisation | Style consistency vs exemplars. Preference adherence. | Embedding similarity to templates/. Periodic blind tests. |
| Latency | P50/P95 for interactive queries. Target sub-5s end-to-end. | Prometheus on PostgreSQL and embedding pipeline. |
| Security | Prompt injection success rate (target: 0%). Audit completeness. | Monthly red team. Automated injection test suite. |
| Cost | Max 20x usage against weekly limits. Headroom monitoring. | Track via Claude Code /cost. Alert at 70% weekly consumption. |

- **Structured logging.** All components log to PostgreSQL: timestamp, component, action, latency, success/failure.
- **Grafana dashboards.** Query latency, retrieval recall, embedding freshness, heartbeat status, subscription usage.
- **Alerting.** Slack alerts for: heartbeat failures, retrieval degradation, unexpected tool calls, vault corruption.

---

## 12. Infrastructure Mapping

| Component | Where | Resources |
|---|---|---|
| PostgreSQL + pgvector | Tensor-Core (container) | Shared with pureClaw. Separate pm_ tables. |
| sentence-transformers | Any TRINITY node (CPU) | Lightweight. Batch jobs, not latency-critical. |
| Obsidian vault | Tensor-Core (NVMe) | Local filesystem. Git-backed. SSH/Tailscale for GUI. |
| Integration wrappers | Tensor-Core (local Python) | Called by Claude Code via bash. No K3s needed. |
| Heartbeat cron | Tensor-Core (systemd timer or crontab) | Python + Agent SDK. Runs every 30 min. |
| Daily reflection cron | Tensor-Core (crontab) | Python + Agent SDK. Runs at 23:00 UTC. |
| Ceph (raw artefact store) | Full fleet (170TB) | Separate pool for pureMind binaries. |
| Audit log (PostgreSQL) | Tensor-Core | Same PG instance. Separate pm_audit table. |

---

## 13. Risk Register

| Risk | L | I | Mitigation |
|---|---|---|---|
| Prompt injection via ingested emails causing unintended tool calls | M | H | Content sanitisation. Tool allowlists. Output validation. Monthly red team. |
| memory.md bloat degrades Claude Code context quality | H | M | Strict 8K cap. Aggressive archival. Promotion scoring with confidence thresholds. |
| Max 20x rate limits hit during heavy heartbeat + interactive use | M | M | Heartbeat runs during off-peak. /cost monitoring. Queue heartbeat if approaching limits. |
| Embedding model degrades as corpus grows | M | M | MTEB eval quarterly. Model rotation plan. Multi-model ensemble option. |
| Daily reflection hallucinates or promotes incorrect knowledge | L | H | Reflection output reviewed weekly. Git versioning enables rollback. |
| Obsidian vault corruption or data loss | L | C | Git versioning. Ceph backup (separate pool). Daily snapshot. |
| Claude Code subscription plan changes or pricing shifts | L | M | Architecture is LLM-agnostic at the skill/hook layer. Could swap to API or local models. |

---

## 14. Success Metrics

| Phase | Done When |
|---|---|
| 1 -- Memory Foundation | soul.md, user.md, memory.md in Git-backed Obsidian vault. Claude Code can cat all three on session start. |
| 2 -- Hooks & Persistence | Session-start loads memory. Session-end writes daily log. Reflection cron promotes items. Git history shows commits. |
| 3 -- Hybrid RAG | pgvector + FTS populated. /search-memory returns relevant results for 10 test queries. MRR > 0.7. |
| 4 -- Integrations | Gmail read+draft, Slack read+alert, GitHub read+comment functional. All calls in audit log. |
| 5 -- Skills | 6+ skills operational. /briefing produces useful output. /self-evolve creates a working new skill. |
| 6 -- Heartbeat | Cron runs every 30 min. Slack alert posted. Draft email created for real scenario. |
| 7 -- Knowledge Graph | Entity graph populated. Relationship query returns meaningful connected results. |
| 8 -- Security | Prompt injection tests pass (0% attacker success). All tool calls logged. Sanitisation active. |
| 9 -- Ops Maturity | Grafana live. Eval harness running weekly. Subscription usage tracked. Runbook documented. |

---

*pureMind runs entirely on Claude Code CLI (Max 20x) + Obsidian + pgvector. No API keys, no local models, no framework dependencies. The subscription is the infrastructure.*

PT-2026-SB v2 | 2026-04-04 | PureTensor, Inc.
