# Karpathy's LLM OS Pattern

Andrej Karpathy proposed framing LLMs as operating systems rather than chatbots. The core insight: an LLM is a kernel process that orchestrates memory, tools, and I/O -- much like a traditional OS kernel manages hardware resources.

## Key Concepts

- **LLM as kernel**: The language model sits at the center, routing between memory systems, tool calls, and user interaction.
- **Context window as RAM**: The token window is volatile working memory. What doesn't fit must be paged to disk (vector stores, files).
- **Tool use as syscalls**: External tool invocations (search, code execution, API calls) are analogous to system calls.
- **RAG as virtual memory**: Retrieval-augmented generation extends the context window by paging in relevant information on demand.
- **Persistent memory**: Long-term storage (files, databases, embeddings) serves as the filesystem layer.

## Implications for Agent Design

Agents built on this pattern tend to have:
1. A memory hierarchy (register/RAM/disk, like MemGPT)
2. Tool orchestration with permission models
3. Proactive scheduling (cron-like heartbeats)
4. Self-improvement loops (reflection, eval, knowledge promotion)

## Relation to pureMind

The pureMind vault implements this pattern directly:
- Claude Code is the kernel process
- memory.md is RAM (<8K tokens, always loaded)
- knowledge/ and daily-logs/ are disk (searchable via RAG)
- tools/ provides the syscall interface
- The heartbeat agent adds proactive scheduling

The wiki layer (Phase 10) extends the disk tier with structured, interlinked knowledge pages and immutable source registration.
