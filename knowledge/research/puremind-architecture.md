---
title: "pureMind Architecture"
page_type: overview
status: seed
source_refs: [src-20260406-karpathy-llm-os-pattern]
aliases: [puremind-arch, vault-architecture]
updated: 2026-04-06
---

# pureMind Architecture

> How pureMind implements the LLM OS pattern as a persistent second brain for PureTensor infrastructure.

## Overview

pureMind is a production vault that implements the [[llm-os-pattern]] directly. Claude Code serves as the kernel process, with a MemGPT-inspired memory hierarchy and tool-based syscall interface. The wiki layer (Phase 10) extends the disk tier with structured, interlinked knowledge pages.

## Memory Hierarchy

| Tier | Analogy | Implementation |
|------|---------|----------------|
| Register | CPU registers | Live conversation context (ephemeral) |
| RAM | Main memory | memory.md (<8K tokens, always loaded) |
| Disk | Filesystem | knowledge/, daily-logs/, projects/ (searchable via RAG) |

## Subsystems

- **Search (Phase 3)** -- hybrid RAG with pgvector + BM25 + RRF fusion
- **Integrations (Phase 4)** -- permission-enforced wrappers for Gmail, GitHub, Calendar, Telegram
- **Skills (Phase 5)** -- 17+ composable skill instructions
- **Heartbeat (Phase 6)** -- proactive 30-minute agent loop (gather/reason/act/notify)
- **Knowledge graph (Phase 7)** -- entity-relationship extraction over vault content
- **Wiki layer (Phase 10)** -- immutable sources, canonical wiki pages, catalog, lint

## Related

- [[llm-os-pattern]] -- the conceptual foundation
- [[services]] -- PureTensor service registry
- [[corporate]] -- PureTensor entity details

## Sources

- src-20260406-karpathy-llm-os-pattern -- architectural mapping from LLM OS to pureMind
