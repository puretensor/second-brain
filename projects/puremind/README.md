# pureMind -- Second Brain

Sovereign second brain built on Claude Code CLI (Max 20x) + Obsidian + pgvector.

- **Status:** Phase 1 complete
- **PRD:** PT-2026-SB v2 (2026-04-04)
- **Repo:** github:puretensor/second-brain
- **Runtime:** Tensor-Core (vault), Ray Trinity (compute, Phase 3+)
- **Owner:** Heimir Helgason

## Architecture

- Single LLM: Claude Code (Max 20x subscription). No API keys, no local models.
- Knowledge: Obsidian vault (Markdown-native), Git-versioned.
- Search: pgvector + PostgreSQL FTS hybrid retrieval (Phase 3). Embeddings via sentence-transformers on Ray Trinity.
- Interaction: Claude Code CLI primary. Obsidian as visual canvas.
- Cron: Agent SDK for heartbeat (30min) and daily reflection (23:00 UTC) (Phase 2+).

## Phases

1. Memory Foundation (Days 1-3) -- **Complete**
2. Context Persistence & Hooks (Days 4-6) -- Planned
3. Memory Search & Hybrid RAG (Days 7-12) -- Planned
4. Direct Integrations (Days 13-18) -- Planned
5. Skills Framework (Days 19-24) -- Planned
6. Heartbeat & Proactive Agent (Days 25-30) -- Planned
7. Knowledge Graph & Advanced Retrieval (Days 31-40) -- Planned
8. Security Hardening (Days 41-48) -- Planned
9. Evaluation & Ops Maturity (Days 49-56) -- Planned
