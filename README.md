# pureMind

**A sovereign second brain built on Claude Code and Obsidian.**

pureMind is a cognitive augmentation system -- not a chatbot wrapper. It captures an evolving worldview, retrieves it under time pressure, and helps you act. Built for a single operator running a sovereign compute cluster with hundreds of cores, TBs of RAM, and PB-scale storage.

## Architecture

Five planes, one LLM. Claude Code is the reasoning layer across all of them.

| Plane | Function | Implementation |
|-------|----------|----------------|
| **Capture** | Connectors and inboxes for raw artefacts | Python scripts, file watchers (inotifywait) |
| **Processing** | Parsing, chunking, embedding, entity extraction | sentence-transformers (CPU), Claude Code for summarisation |
| **Knowledge** | Raw store + canonical store + indexes + versioning | Obsidian vault, pgvector, PostgreSQL FTS, Git |
| **Interaction** | Search, Q&A, writing, meeting prep | Claude Code CLI as primary interface |
| **Action** | Agent workflows, tool execution, memory write-back | Claude Code skills + hooks, Agent SDK for cron |

## Core Stack

- **Claude Code CLI** (Max 20x subscription) -- single LLM, no routing, no API keys
- **Obsidian vault** (Markdown-native) -- portable, diffable, Git-versioned
- **pgvector + PostgreSQL FTS** -- hybrid retrieval with Reciprocal Rank Fusion
- **sentence-transformers** (CPU) -- all-MiniLM-L6-v2 for embeddings, distributed via Ray
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
    YYYY-MM-DD.md    # Raw conversation dumps per day
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
| 2 | Context Persistence & Hooks | 4-6 | Planned |
| 3 | Memory Search & Hybrid RAG | 7-12 | Planned |
| 4 | Direct Integrations | 13-18 | Planned |
| 5 | Skills Framework | 19-24 | Planned |
| 6 | Heartbeat & Proactive Agent | 25-30 | Planned |
| 7 | Knowledge Graph & Advanced Retrieval | 31-40 | Planned |
| 8 | Security Hardening | 41-48 | Planned |
| 9 | Evaluation & Ops Maturity | 49-56 | Planned |

## License

Proprietary. Copyright 2026 PureTensor, Inc. All rights reserved.
