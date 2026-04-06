# pureMind

**A sovereign second brain built on Claude Code and Obsidian.**

pureMind is a cognitive augmentation system -- not a chatbot wrapper. It captures an evolving worldview, retrieves it under time pressure, and helps you act. Built for a single operator running a sovereign compute cluster with hundreds of cores, TBs of RAM, and PB-scale storage.

## Architecture

Five planes, one LLM. Claude Code is the reasoning layer across all of them.

| Plane | Function | Implementation | Phase |
|-------|----------|----------------|-------|
| **Capture** | Connectors and inboxes for raw artefacts | Python scripts, file watchers (inotifywait) | 2, 4 |
| **Processing** | Parsing, chunking, embedding, entity extraction | sentence-transformers (CPU), Claude Code for summarisation | 3 |
| **Knowledge** | Raw store + canonical store + indexes + versioning | Obsidian vault (live), pgvector + PostgreSQL FTS + Git (live) | 1, 3 |
| **Interaction** | Search, Q&A, writing, meeting prep | Claude Code CLI as primary interface | 1 (live), 5 |
| **Action** | Agent workflows, tool execution, memory write-back | Claude Code skills + hooks, Agent SDK for cron | 2, 5, 6 |

### What is live now (Phases 1-9 + Insights)
- Git-backed Obsidian-compatible vault with core identity files (soul.md, user.md, memory.md)
- Auto-commit hook, SessionStart/PreCompact/SessionEnd hooks, daily reflection cron (23:00 UTC)
- Hybrid RAG search (BM25 + pgvector semantic with RRF fusion) over all vault content
- Graph-augmented search: entity traversal via recursive CTE, fused with hybrid results
- HyDE search: hypothetical document embeddings for vague queries
- Multilingual FTS: unaccent extension for non-English content
- Auto-indexing on file changes via PostToolUse hook
- Entity extraction from vault files via Claude CLI, stored in PostgreSQL knowledge graph
- Hierarchical summaries: RAPTOR-style tree (file -> project -> vault) with embeddings
- Permission-enforced integrations: Gmail (read+draft), GitHub (read+comment), Calendar (read), Telegram (alerts)
- Audit logging: every integration call tracked in pm_audit table with latency, params, result
- 17 skills: briefing, search, gmail, github, calendar, alerts, draft-email, reflect, project-status, diagram, write, research (quick/deep), ingest, self-evolve, heartbeat, health-sweep, migrate
- Content ingestion tool: PDF, markdown, text, URL ingestion with provenance frontmatter
- Self-evolving skill creation: pureMind creates its own new skills by analyzing existing patterns
- Proactive heartbeat agent: 30-minute cron gathers state from all integrations + fleet health (parallel SSH to 10 nodes in <1s), reasons via Claude, acts within permissions, posts Telegram summary
- Fleet health integration: parallel node checks (reachability, disk, load, services) via Tailscale SSH
- Test-driven migration runner: bash test_* discovery, per-step validation, 3-consecutive-failure stop logic
- Graduated proactivity: observer (report) -> adviser (draft) -> partner (act) -- config-driven trust levels
- Credential externalization: secrets resolved via env var > file > fail closed (no hardcoded fallback)
- Content sanitization pipeline: 4-layer sanitization on all Claude-facing prompts (NFKC + Unicode stripping, narrowed injection patterns, case-insensitive fence escaping, size limits)
- Prompt injection test suite: 10-category attack payloads with 30 fast tests + Claude CLI integration tests
- Audit hardening: JSONL fallback when DB unavailable, per-user rate limiter (0700), connect_timeout
- Dependency pinning: all Python packages pinned to exact versions
- PDF resource limits: 120s timeout, 200-page cap
- Evaluation harness: weekly 6-metric assessment (retrieval, generation, personalisation, latency, security, cost)
- Golden dataset: 55 QA pairs with ground-truth chunk IDs for retrieval metrics (Recall@k, MRR, nDCG)
- Metrics collector: 15-minute health checks to PostgreSQL with threshold-based Telegram alerts
- Grafana dashboard: 6-row overview (health, retrieval, generation, latency, security, freshness)
- Operational runbook: service map, troubleshooting, alerting matrix, recovery procedures

## Core Stack

- **Claude Code CLI** (Max 20x subscription) -- single LLM, no routing, no API keys
- **Obsidian vault** (Markdown-native) -- portable, diffable, Git-versioned
- **pgvector + PostgreSQL FTS** *(Phase 3)* -- hybrid retrieval with Reciprocal Rank Fusion
- **sentence-transformers** (CPU) *(Phase 3)* -- nomic-embed-text-v1.5 (768-dim) for embeddings, local on TC
- **Git** -- every memory write commits with structured message

## Design Principles

- **Single LLM, no routing.** The Max 20x subscription absorbs all inference cost at a flat rate.
- **Sovereign by default.** All raw data stays on-premises. No data sent anywhere except through Claude Code's own connection to Anthropic.
- **Markdown-native.** Knowledge lives as plain Markdown in Obsidian -- portable, diffable, Git-versioned.
- **Simple composable patterns.** Claude Code + skills + hooks. No LangChain, no LlamaIndex. Skills are Markdown instructions. Hooks are bash/Python scripts.
- **Incremental trust.** Start read-only on all integrations. Add write capabilities per-service with explicit allowlists.
- **Compounding memory.** Every conversation feeds the daily log. Daily reflection promotes durable knowledge. The system gets smarter with every session.
- **Evaluation-driven.** Retrieval quality measured, not vibed. Regression tests for RAG. Adversarial tests for security.

## Memory Hierarchy

Inspired by MemGPT's tiered memory model:

- **Register** -- live conversation context (ephemeral, in Claude Code's context window)
- **RAM** -- `memory/memory.md` (always loaded, capped at 8K tokens)
- **Disk** -- `daily-logs/`, `knowledge/`, `projects/` (searchable via hybrid RAG, not always loaded)

The daily reflection cron is the promotion mechanism: high-signal items graduate from disk to RAM. Low-relevance items are archived. This is how the system compounds intelligence over time.

## Vault Structure

```
pureMind/
  memory/
    soul.md          # Agent constitution and red lines
    user.md          # Auto-evolving owner profile
    memory.md        # Promoted durable knowledge (8K cap)
  daily-logs/
    YYYY-MM-DD.md    # Structured session logs per day
  knowledge/
    puretensor/      # Company context, infra docs
    research/        # Papers, technical notes
    contacts/        # Key people and relationships
  projects/
    pureclaw/        # Active project context
    immune-system/
    puremind/
  templates/
    email-style.md   # Writing style exemplars
    briefing-note.md # Output templates
  .claude/
    settings.json    # Project-level Claude Code config
    skills/          # Claude Code skill definitions
    hooks/           # Lifecycle hook scripts
```

## Phases

| # | Phase | Days | Status |
|---|-------|------|--------|
| 1 | Memory Foundation | 1-3 | Complete |
| 2 | Context Persistence & Hooks | 4-6 | Complete |
| 3 | Memory Search & Hybrid RAG | 7-12 | Complete |
| 4 | Direct Integrations | 13-18 | Complete |
| 5 | Skills Framework | 19-24 | Complete |
| 6 | Heartbeat & Proactive Agent | 25-30 | Complete |
| 7 | Knowledge Graph & Advanced Retrieval | 31-40 | Complete |
| 8 | Security Hardening | 41-48 | Complete |
| 9 | Evaluation & Ops Maturity | 49-56 | Complete |

## License

Proprietary. Copyright 2026 PureTensor, Inc. All rights reserved.
