# pureMind -- Second Brain

Sovereign second brain built on Claude Code CLI (Max 20x) + Obsidian + pgvector.

**PRD:** PT-2026-SB v2 (2026-04-04)
**Status:** Phase 1 in progress

## Architecture
- Single LLM: Claude Code (Max 20x subscription). No API keys, no local models.
- Knowledge: Obsidian vault (Markdown-native), Git-versioned.
- Search: pgvector + PostgreSQL FTS hybrid retrieval. Embeddings via sentence-transformers on Ray Trinity.
- Interaction: Claude Code CLI primary, Slack secondary, Obsidian as visual canvas.
- Cron: Anthropic Agent SDK for heartbeat (30min) and daily reflection (23:00 UTC).

## Phases
1. Memory Foundation (Days 1-3) -- IN PROGRESS
2. Context Persistence & Hooks (Days 4-6)
3. Memory Search & Hybrid RAG (Days 7-12) -- Ray Trinity for embeddings
4. Direct Integrations (Days 13-18)
5. Skills Framework (Days 19-24)
6. Heartbeat & Proactive Agent (Days 25-30)
7. Knowledge Graph & Advanced Retrieval (Days 31-40) -- Ray Trinity for entity extraction
8. Security Hardening (Days 41-48)
9. Evaluation & Ops Maturity (Days 49-56) -- Ray Trinity for RAGAS eval
