---
title: "LLM OS Pattern"
page_type: concept
status: seed
source_refs: [src-20260406-karpathy-llm-os-pattern]
aliases: [llm-os, karpathy-os-pattern]
updated: 2026-04-06
---

# LLM OS Pattern

> Architectural pattern framing LLMs as operating system kernels that orchestrate memory, tools, and I/O.

## Overview

Proposed by Andrej Karpathy, the LLM OS pattern reframes language models from chatbots to kernel processes. The LLM sits at the center of a system, routing between memory tiers, tool invocations, and user interaction -- analogous to how a traditional OS kernel manages hardware resources.

## Key Analogies

- **LLM as kernel** -- the model is the central process, dispatching to subsystems
- **Context window as RAM** -- volatile working memory; what doesn't fit must be paged to disk
- **Tool use as syscalls** -- external tool invocations (search, code execution, APIs) map to system calls
- **RAG as virtual memory** -- retrieval-augmented generation pages in relevant information on demand
- **Persistent memory** -- files, databases, and embeddings form the filesystem layer

## Implications for Agent Design

Agents built on this pattern tend to implement:
1. A memory hierarchy (register/RAM/disk) inspired by MemGPT
2. Tool orchestration with permission models
3. Proactive scheduling (cron-like heartbeats)
4. Self-improvement loops (reflection, evaluation, knowledge promotion)

## Related

- [[puremind-architecture]] -- pureMind's implementation of this pattern
- [[services]] -- the tool/syscall layer in PureTensor infrastructure

## Sources

- src-20260406-karpathy-llm-os-pattern -- Karpathy's LLM OS framing and its relation to pureMind
