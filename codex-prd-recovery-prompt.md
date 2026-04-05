# PRD Recovery: pureMind PT-2026-SB v2

## Your Task

You helped build Phases 1-3 of **pureMind**, PureTensor's sovereign second brain project. The original PRD (PT-2026-SB v2, dated 2026-04-04) was discussed in our earlier sessions but was never committed to the repo as a standalone document. Codex flagged this as a missing artifact in the Phase 1 review (Issue I-01).

We are now about to start Phase 4 (Direct Integrations) and need the detailed scope for Phases 4-9. The phase names and day ranges are known, but the specific deliverables, acceptance criteria, and integration targets are not in the repo.

## What We Know

From the READMEs and daily logs, the 9-phase structure is:

| # | Phase | Days | Status |
|---|-------|------|--------|
| 1 | Memory Foundation | 1-3 | Complete |
| 2 | Context Persistence & Hooks | 4-6 | Complete |
| 3 | Memory Search & Hybrid RAG | 7-12 | Complete |
| 4 | Direct Integrations | 13-18 | Planned |
| 5 | Skills Framework | 19-24 | Planned |
| 6 | Heartbeat & Proactive Agent | 25-30 | Planned |
| 7 | Knowledge Graph & Advanced Retrieval | 31-40 | Planned |
| 8 | Security Hardening | 41-48 | Planned |
| 9 | Evaluation & Ops Maturity | 49-56 | Planned |

From the architecture table in README.md, we know Phase 4 maps to the **Capture** plane ("Connectors and inboxes for raw artefacts -- Python scripts, file watchers").

Design principles that constrain all phases:
- Single LLM (Claude Code, Max 20x). No API keys, no local models, no routing.
- Sovereign by default. All raw data on-premises.
- Markdown-native. Obsidian vault.
- Simple composable patterns. Claude Code + skills + hooks. No LangChain, no LlamaIndex.
- **Incremental trust. Start read-only on all integrations. Add write capabilities per-service with explicit allowlists.**
- Compounding memory. Every conversation feeds the daily log.

Infrastructure available:
- Ray Trinity: 160 CPUs, 110GB RAM, 2 GPUs, 200 GbE (TC + fox-n0 + fox-n1)
- pgvector in K3s (vantage DB, fox-n1:30433). Hybrid RAG already live.
- Google Workspace (hal@puretensor.ai): Gmail, Calendar, Drive, Admin SDK
- Telegram/PureClaw (Nexus, K3s): already running, has its own memory_rag.py
- GitHub + Gitea: 56 repos
- Existing tools: gmail.py, gdrive.py, x_post.py, gadmin.py
- MCP servers available: Gmail, Google Calendar, Playwright, Hugging Face

## What We Need

Do you have the detailed Phase 4-9 breakdown from the original PRD (PT-2026-SB v2) in your context or memory? If so, reproduce it in full.

If you do not have it, say so clearly -- do not fabricate one. We will reconstruct it from first principles.

## Output Format

If you have it, reproduce the full PRD section for Phases 4-9 with:
- Phase name, days, and description
- Specific deliverables (files, scripts, schemas)
- Acceptance criteria (testable, not vague)
- Dependencies on previous phases
- Infrastructure requirements

If you don't have it, respond with exactly: "I do not have the PT-2026-SB v2 PRD in my context or memory."
