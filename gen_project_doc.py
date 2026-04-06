#!/usr/bin/env python3
"""Generate pureMind Project Documentation PDF -- Part 1 (Pages 1-8)."""

import sys
sys.path.insert(0, "/home/puretensorai/tensor-scripts/templates")

from puretensor_doc_template import (
    PureTensorTemplate, build_styles, register_fonts,
    section_heading, styled_table, table_header_cell, table_body_cell,
    escape, Paragraph, Spacer, KeepTogether, HRFlowable,
    ACCENT_BLUE, DARK_BLUE, mm,
)
from reportlab.platypus import PageBreak
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib import colors

register_fonts()
styles = build_styles()

# Extra styles
code_style = ParagraphStyle(
    name="Code", fontName="DejaVuMono", fontSize=7.5,
    textColor=colors.HexColor("#333333"), leading=10,
    leftIndent=4*mm, spaceBefore=1*mm, spaceAfter=1*mm,
    backColor=colors.HexColor("#F5F7FA"),
)
callout_style = ParagraphStyle(
    name="CalloutBox", fontName="DejaVu-Bold", fontSize=9,
    textColor=DARK_BLUE, leading=13, alignment=TA_JUSTIFY,
    spaceBefore=3*mm, spaceAfter=3*mm, leftIndent=4*mm, rightIndent=4*mm,
    borderWidth=1, borderColor=ACCENT_BLUE, borderPadding=6,
    backColor=colors.HexColor("#F0F4F8"),
)

OUTPUT = "/home/puretensorai/pureMind/PureMind_Project_Documentation.pdf"

tpl = PureTensorTemplate(
    output_path=OUTPUT,
    title="pureMind",
    subtitle="Project Documentation -- Second Brain System",
    confidential=True,
)

story = []
e = escape
B = lambda t: f"<b>{e(t)}</b>"
I = lambda t: f"<i>{e(t)}</i>"
s = styles

# ============================================================
# META
# ============================================================
story.append(Paragraph(f"{I('Document Reference: PT-2026-SB-DOC | 5 April 2026')}", s["meta"]))
story.append(Paragraph(f"{I('Author: HAL (Heterarchical Agentic Layer) | Reviewed by: Heimir Helgason')}", s["meta"]))
story.append(Spacer(1, 4*mm))

# ============================================================
# 1. EXECUTIVE SUMMARY
# ============================================================
story.append(section_heading("1. Executive Summary", s))
story.append(Paragraph(
    "pureMind is a sovereign second brain system built for PureTensor's operational infrastructure. "
    "It transforms Claude Code from a stateless language model into a persistent, context-aware operational "
    "agent with long-term memory, proactive monitoring, and searchable institutional knowledge. "
    "The system was designed, built, and deployed in a single day (5 April 2026) across nine implementation "
    "phases, culminating in 106 Git commits and a production-live system with active heartbeat monitoring, "
    "hybrid RAG search, a knowledge graph, security hardening, and an evaluation framework.",
    s["body"],
))
story.append(Spacer(1, 2*mm))
story.append(Paragraph(
    "pureMind runs entirely on the Claude Code CLI (Max 20x subscription) with no external API keys, "
    "no local model inference, and no framework dependencies. The subscription is the infrastructure. "
    "All data remains on PureTensor's sovereign compute cluster. The system is Obsidian-compatible, "
    "Git-versioned, and designed for a single operator running a complex multi-node fleet.",
    s["body"],
))

# ============================================================
# 2. PROBLEM STATEMENT
# ============================================================
story.append(section_heading("2. Problem Statement", s))
story.append(Paragraph(
    "Modern AI assistants are stateless. Every conversation starts from zero -- no memory of prior "
    "sessions, no awareness of ongoing operations, no accumulated institutional knowledge. For an "
    "operator running a sovereign compute cluster with hundreds of cores, dozens of services, multiple "
    "corporate entities, and complex ongoing projects, this creates three critical problems:",
    s["body"],
))
story.append(Spacer(1, 1*mm))

problems = [
    ("Context Loss", "Every session requires re-briefing. Decisions made yesterday must be re-explained. "
     "Lessons learned from past mistakes are forgotten. The AI assistant provides generic advice "
     "instead of contextualised operational guidance."),
    ("Operational Blindness", "Between sessions, the AI has zero awareness of incoming emails, GitHub "
     "activity, calendar events, or infrastructure alerts. The operator must manually check everything "
     "and relay information back to the assistant."),
    ("Knowledge Fragmentation", "Institutional knowledge -- contacts, credentials, infrastructure details, "
     "project histories, corporate procedures -- lives scattered across flat files, human memory, and "
     "ephemeral conversation contexts. There is no searchable, structured, compounding knowledge base."),
]
for title, desc in problems:
    story.append(Paragraph(f"<bullet>&bull;</bullet> {B(title + ':')} {e(desc)}", s["bullet"]))

story.append(Spacer(1, 2*mm))
story.append(Paragraph(
    "The result: an AI that is powerful in any single conversation but provides no compounding value "
    "across sessions. Each interaction is isolated. The operator's growing expertise and context never "
    "transfers to the agent.",
    s["body"],
))

# ============================================================
# 3. OBJECTIVES
# ============================================================
story.append(section_heading("3. What We Set Out To Build", s))
story.append(Paragraph(
    "pureMind was designed to solve these problems by building a cognitive augmentation layer around "
    "Claude Code. The objectives were:",
    s["body"],
))
objectives = [
    "Persistent memory across all sessions -- the agent remembers everything, compounds intelligence over time",
    "Proactive operational awareness -- the agent monitors inboxes, repos, and calendar without being asked",
    "Searchable institutional knowledge -- hybrid retrieval (lexical + semantic + graph) over all accumulated knowledge",
    "Security hardening -- safe ingestion of external content without prompt injection risk",
    "Measurable quality -- evaluation framework with golden datasets, not vibes-based assessment",
    "Sovereign by default -- all data stays on-premises, no external API dependencies",
    "Obsidian-compatible -- the vault is portable, human-readable, and works with Obsidian's visual tooling",
    "Single LLM, no routing -- Claude Code (Max 20x) handles everything at flat-rate cost",
]
for obj in objectives:
    story.append(Paragraph(f"<bullet>&bull;</bullet> {e(obj)}", s["bullet"]))

# ============================================================
# 4. ARCHITECTURE
# ============================================================
story.append(section_heading("4. Architecture Overview", s))
story.append(Paragraph(
    "pureMind operates across five planes, all powered by a single LLM (Claude Code). There is no "
    "model routing, no API key management, and no token budgeting. The Max 20x subscription absorbs "
    "all inference cost at a flat rate.",
    s["body"],
))
story.append(Spacer(1, 2*mm))

arch_data = [
    [table_header_cell("Plane"), table_header_cell("Function"), table_header_cell("Implementation")],
    [table_body_cell("Capture"), table_body_cell("Connectors for raw artefacts"),
     table_body_cell("Python scripts, inotifywait file watchers, lifecycle hooks")],
    [table_body_cell("Processing"), table_body_cell("Parsing, chunking, embedding, entity extraction"),
     table_body_cell("sentence-transformers (CPU), Claude Code for summarisation")],
    [table_body_cell("Knowledge"), table_body_cell("Raw + canonical store, indexes, versioning"),
     table_body_cell("Obsidian vault, pgvector + PostgreSQL FTS, Git")],
    [table_body_cell("Interaction"), table_body_cell("Search, Q&A, writing, briefings"),
     table_body_cell("Claude Code CLI as primary interface, 15 skills")],
    [table_body_cell("Action"), table_body_cell("Agent workflows, proactive monitoring"),
     table_body_cell("Heartbeat agent, systemd timers, Claude CLI programmatic")],
]
story.append(styled_table(arch_data, [28*mm, 52*mm, None]))

story.append(Spacer(1, 3*mm))
story.append(Paragraph("4.1 Memory Hierarchy (MemGPT-Inspired)", s["h2"]))
story.append(Paragraph(
    "pureMind implements a three-tier memory model inspired by the MemGPT architecture, mapping "
    "computer memory concepts to agent cognition:",
    s["body"],
))

mem_data = [
    [table_header_cell("Tier"), table_header_cell("Analogy"), table_header_cell("Implementation"), table_header_cell("Behaviour")],
    [table_body_cell("Register"), table_body_cell("CPU register"),
     table_body_cell("Live conversation context"), table_body_cell("Ephemeral. Lost on session end.")],
    [table_body_cell("RAM"), table_body_cell("Working memory"),
     table_body_cell("memory.md (8K token cap)"), table_body_cell("Always loaded. Every session sees this.")],
    [table_body_cell("Disk"), table_body_cell("Long-term storage"),
     table_body_cell("daily-logs/, knowledge/, projects/"), table_body_cell("Searchable via hybrid RAG. Loaded on demand.")],
]
story.append(styled_table(mem_data, [20*mm, 24*mm, 48*mm, None]))

story.append(Spacer(1, 2*mm))
story.append(Paragraph(
    "The daily reflection cron (23:00 UTC) is the promotion engine: it reads the day's logs, scores "
    "items for durability and cross-topic relevance, and promotes high-signal knowledge from Disk to RAM. "
    "Low-relevance RAM entries are archived back to Disk. This is how the system compounds intelligence "
    "over time rather than starting fresh each day.",
    s["body"],
))

story.append(Spacer(1, 3*mm))
story.append(Paragraph("4.2 Core Stack", s["h2"]))
stack_items = [
    "Claude Code CLI (Max 20x subscription) -- sole LLM, no routing, no API keys",
    "Obsidian vault (Markdown-native) -- portable, diffable, Git-versioned",
    "pgvector + PostgreSQL FTS -- hybrid retrieval with Reciprocal Rank Fusion",
    "sentence-transformers (CPU) -- nomic-embed-text-v1.5 (768-dim) for embeddings",
    "Git -- every memory write commits with structured message",
    "systemd timers -- heartbeat (30 min), reflection (daily), eval (weekly), metrics (15 min)",
    "Telegram -- notification channel for heartbeat summaries and threshold alerts",
]
for item in stack_items:
    story.append(Paragraph(f"<bullet>&bull;</bullet> {e(item)}", s["bullet"]))

story.append(Spacer(1, 3*mm))
story.append(Paragraph("4.3 Vault Structure", s["h2"]))
vault_items = [
    "memory/ -- Core identity (soul.md, user.md, memory.md, pending.md)",
    "daily-logs/ -- Structured session logs per day, heartbeat JSONL",
    "knowledge/ -- Curated reference (company context, research, contacts)",
    "projects/ -- Active project context files",
    "templates/ -- Writing style exemplars, output templates",
    "tools/ -- Python tools (search, index, embed, extract, summarise, ingest, heartbeat, eval, metrics, sanitise, credentials)",
    "migrations/ -- PostgreSQL schema files (RAG, audit, knowledge graph, eval)",
    "tests/ -- Security and evaluation test suites",
    "ops/ -- Grafana dashboard, systemd units, operational runbook",
    ".claude/ -- Settings, skills (15), hooks, integrations (5)",
]
for item in vault_items:
    story.append(Paragraph(f"<bullet>&bull;</bullet> {e(item)}", s["bullet"]))

# ============================================================
# 5. DESIGN PRINCIPLES
# ============================================================
story.append(section_heading("5. Design Principles", s))
principles = [
    ("Single LLM, No Routing",
     "The Max 20x subscription at $200/month is a flat-rate ceiling. Heavy usage that would cost $1,000+ "
     "at API rates is absorbed. No token counting, no model selection, no cost management infrastructure."),
    ("Sovereign by Default",
     "All raw data stays on PureTensor's sovereign compute cluster. No data sent anywhere except through "
     "Claude Code's own connection to Anthropic (which is the subscription already being paid for)."),
    ("Markdown-Native",
     "Knowledge lives as plain Markdown in an Obsidian-compatible vault -- portable, diffable, "
     "Git-versioned. No proprietary formats, no database lock-in for the canonical store."),
    ("Simple Composable Patterns",
     "Claude Code + skills + hooks. No LangChain, no LlamaIndex, no framework bloat. Skills are "
     "Markdown instructions. Hooks are bash/Python scripts. The entire system is debuggable with cat and grep."),
    ("Incremental Trust",
     "Start read-only on all integrations. Add write capabilities per-service with explicit allowlists. "
     "The heartbeat starts at observer level and graduates through adviser to partner."),
    ("Compounding Memory",
     "Every conversation feeds the daily log. Daily reflection promotes durable knowledge. The system "
     "gets smarter with every session -- not because the model improves, but because the memory does."),
    ("Evaluation-Driven",
     "Retrieval quality is measured with golden datasets (Recall@k, MRR, nDCG), not vibed. "
     "Security is tested with adversarial payloads. Prompt injection success rate target: 0%."),
]
for title, desc in principles:
    story.append(Paragraph(f"{B(title + '.')} {e(desc)}", s["body"]))
    story.append(Spacer(1, 1*mm))

# ============================================================
# 6. BUILD PHASES
# ============================================================
story.append(section_heading("6. Build Phases", s))
story.append(Paragraph(
    "pureMind was built in nine sequential phases over a single day (5 April 2026). Each phase had "
    "explicit success criteria from the PRD (PT-2026-SB v2), was reviewed via Codex structured evaluation, "
    "and had fixes applied before proceeding to the next phase. Total: 106 Git commits.",
    s["body"],
))
story.append(Spacer(1, 2*mm))

# Phase 1
story.append(Paragraph("Phase 1: Memory Foundation", s["h2"]))
story.append(Paragraph(
    "Core identity files in a Git-backed vault. Three files form the persistent identity of pureMind: "
    "soul.md (agent constitution, red lines, decision framework), user.md (auto-evolving operator profile "
    "with projects, contacts, vocabulary), and memory.md (rolling promoted knowledge, 8K token cap). "
    "Vault directory structure created with 18 directories. Knowledge base seeded with PureTensor services "
    "(42 lesson entries), corporate details, and key contacts. Git repo initialised and pushed to GitHub.",
    s["body"],
))
story.append(Paragraph(f"{I('Success criterion: soul.md, user.md, memory.md in Git-backed vault. Claude Code can cat all three on session start.')}", s["meta"]))

# Phase 2
story.append(Spacer(1, 2*mm))
story.append(Paragraph("Phase 2: Context Persistence and Hooks", s["h2"]))
story.append(Paragraph(
    "Three lifecycle hooks make memory persistent across sessions. SessionStart loads the identity stack "
    "into Claude Code context with per-section byte budgets (identity 1800B, profile 1800B, memory 1800B). "
    "PreCompact fires before context compression, appending a compaction extract to the daily log to prevent "
    "knowledge loss. SessionEnd runs in background on exit, appending a session boundary and committing to Git. "
    "A daily reflection script (23:00 UTC via systemd timer) uses Claude CLI programmatically to analyse "
    "the day's log and run a structured promotion pipeline: extract, score, promote, update, commit, notify.",
    s["body"],
))
story.append(Paragraph(f"{I('Success criterion: Session-start loads memory. Session-end writes daily log. Reflection cron promotes items. Git history shows commits.')}", s["meta"]))

# Phase 3
story.append(Spacer(1, 2*mm))
story.append(Paragraph("Phase 3: Memory Search and Hybrid RAG", s["h2"]))
story.append(Paragraph(
    "The real power comes from searching all daily logs, knowledge docs, and project files. Hybrid retrieval "
    "uses pgvector (HNSW index, cosine distance) for semantic search and PostgreSQL tsvector for BM25 "
    "lexical search, fused via Reciprocal Rank Fusion (k=60). Embedding model: nomic-embed-text-v1.5 "
    "(768-dim) via sentence-transformers, running on CPU. Chunking: heading-aware markdown splitter with "
    "2048-char max and 20% overlap. Auto-indexing via PostToolUse hook on vault file changes. "
    "SHA-256 change detection for incremental re-indexing.",
    s["body"],
))
story.append(Paragraph(f"{I('Success criterion: pgvector + FTS populated. /search-memory returns relevant results for 10 test queries. MRR > 0.7.')}", s["meta"]))

# Phase 4
story.append(Spacer(1, 2*mm))
story.append(Paragraph("Phase 4: Direct Integrations", s["h2"]))
story.append(Paragraph(
    "Permission-enforced Python wrappers over existing tools (Gmail, GitHub, Calendar, Telegram). "
    "Each wrapper exposes a small API matching a strict permission model: Gmail (read + draft only, no send), "
    "GitHub (read + comment only, no merge/push), Calendar (read-only), Telegram (alerts chat only). "
    "All calls logged to pm_audit table via @audited decorator. Write operations fail closed when audit DB "
    "is unavailable. File-based rate limiter (per-user, mode 0700) prevents runaway agent loops. "
    "Parameter sanitisation strips sensitive keys and truncates content fields in audit logs.",
    s["body"],
))
story.append(Paragraph(f"{I('Success criterion: Gmail read+draft, GitHub read+comment, Calendar read, Telegram alert all functional. All calls in audit log.')}", s["meta"]))

# Phase 5
story.append(Spacer(1, 2*mm))
story.append(Paragraph("Phase 5: Skills Framework", s["h2"]))
story.append(Paragraph(
    "15 Claude Code skills defined as Markdown instructions with YAML frontmatter (inputs, outputs, "
    "writes_to, side_effects). Skills compose existing tools and integrations without code changes. "
    "Key skills: /briefing (morning briefing from all integrations), /puremind-search (hybrid RAG with "
    "--graph and --hyde modes), /draft-email (compose in operator's voice), /ingest (PDF/URL/doc ingestion "
    "with provenance), /self-evolve (pureMind creates its own new skills by analysing existing patterns), "
    "/heartbeat (manual trigger for proactive agent). Content ingestion tool supports PDF (pdfplumber), "
    "markdown, text, and URL sources with YAML provenance frontmatter.",
    s["body"],
))
story.append(Paragraph(f"{I('Success criterion: 6+ skills operational. /briefing produces useful output. /self-evolve creates a working new skill.')}", s["meta"]))

# Phase 6
story.append(Spacer(1, 2*mm))
story.append(Paragraph("Phase 6: Heartbeat and Proactive Agent", s["h2"]))
story.append(Paragraph(
    "The heartbeat transforms pureMind from reactive to proactive. A 30-minute systemd timer runs a "
    "four-step loop: Gather (deterministic API calls to all integrations), Reason (Claude CLI single-turn "
    "with gathered context + soul.md + memory.md), Act (within permission boundaries), Notify (Telegram "
    "summary). Three proactivity levels: observer (read + log + alert), adviser (+ drafts + pending updates), "
    "partner (+ PR/issue comments). The heartbeat currently runs at observer level. Three-layer action "
    "validation: level check, permission check, rate check. Results logged to heartbeat-log.jsonl.",
    s["body"],
))
story.append(Paragraph(f"{I('Success criterion: Cron runs every 30 min. Telegram alert posted. Draft email created for real scenario.')}", s["meta"]))

# Phase 7
story.append(Spacer(1, 2*mm))
story.append(Paragraph("Phase 7: Knowledge Graph and Advanced Retrieval", s["h2"]))
story.append(Paragraph(
    "Entity-relationship graph over vault content, stored in PostgreSQL JSONB adjacency lists (no Neo4j "
    "needed at this scale). Entity extraction via Claude CLI processes vault files to identify people, "
    "projects, technologies, concepts, decisions, and events, plus their relationships (mentions, depends_on, "
    "part_of, works_on, uses, decided, created_by). Graph-augmented search traverses entities via recursive "
    "CTE and fuses graph-sourced chunks with hybrid results. HyDE search generates hypothetical answers "
    "via Claude CLI for improved retrieval on vague queries. RAPTOR-style hierarchical summaries at file, "
    "project, and vault levels with their own embeddings. Multilingual FTS via unaccent extension.",
    s["body"],
))
story.append(Paragraph(f"{I('Success criterion: Entity graph populated. Relationship query returns meaningful connected results.')}", s["meta"]))

# Phase 8
story.append(Spacer(1, 2*mm))
story.append(Paragraph("Phase 8: Security Hardening", s["h2"]))
story.append(Paragraph(
    "Systematic defence against the lethal trifecta (private data access + untrusted content + exfiltration "
    "vectors). Credential externalisation: secrets resolved via env var > secrets.env (0600) > fail closed "
    "(RuntimeError). Content sanitisation pipeline: 4 layers (NFKC + control char removal, narrowed injection "
    "pattern stripping, case-insensitive fence escaping, size enforcement). Applied in extract.py, "
    "summarize.py, heartbeat.py, ingest.py. Prompt injection test suite: 8 attack categories (direct override, "
    "role injection, fence escape, JSON injection, Unicode smuggling, social engineering, markdown injection, "
    "context flooding) with 30 fast tests and Claude CLI integration tests. Audit hardening: JSONL fallback "
    "when DB unavailable, per-user rate limiter, connect_timeout. All dependencies pinned to exact versions.",
    s["body"],
))
story.append(Paragraph(f"{I('Success criterion: Prompt injection tests pass (0% attacker success). All tool calls logged. Sanitisation active.')}", s["meta"]))

# Phase 9
story.append(Spacer(1, 2*mm))
story.append(Paragraph("Phase 9: Evaluation and Ops Maturity", s["h2"]))
story.append(Paragraph(
    "Measurable quality via a weekly evaluation harness assessing 6 metrics: retrieval quality (Recall@5, "
    "MRR, nDCG@5), generation faithfulness, personalisation, latency (P50/P95), security (test pass rate), "
    "and cost (Claude CLI calls in 7 days). Golden dataset: 55 QA pairs with ground-truth chunk IDs for "
    "retrieval evaluation. Metrics collector runs every 15 minutes, writes system health to pm_metrics, "
    "and fires Telegram alerts on threshold breaches (with 1-hour deduplication). Grafana dashboard: "
    "6-row overview (health, retrieval, generation, latency, security, freshness). Operational runbook "
    "documents service map, troubleshooting procedures, alerting matrix, and recovery procedures.",
    s["body"],
))
story.append(Paragraph(f"{I('Success criterion: Grafana live. Eval harness running weekly. Subscription usage tracked. Runbook documented.')}", s["meta"]))

# ============================================================
# 7. DATABASE SCHEMA
# ============================================================
story.append(section_heading("7. Database Schema", s))
story.append(Paragraph(
    "pureMind uses four PostgreSQL tables in the existing vantage database (fox-n1:30433), sharing the "
    "instance with PureClaw. The pgvector extension provides HNSW indexing for dense vectors.",
    s["body"],
))
story.append(Spacer(1, 2*mm))

schema_data = [
    [table_header_cell("Table"), table_header_cell("Phase"), table_header_cell("Purpose"), table_header_cell("Key Columns")],
    [table_body_cell("puremind_chunks"), table_body_cell("3"),
     table_body_cell("Chunked vault content with embeddings"),
     table_body_cell("file_path, heading_path, content, embedding(768), content_tsv, file_hash")],
    [table_body_cell("pm_audit"), table_body_cell("4"),
     table_body_cell("Integration call audit trail"),
     table_body_cell("integration, function, params, result, detail, latency_ms")],
    [table_body_cell("pm_entities"), table_body_cell("7"),
     table_body_cell("Knowledge graph entities"),
     table_body_cell("name, entity_type, description, source_chunk_ids")],
    [table_body_cell("pm_relationships"), table_body_cell("7"),
     table_body_cell("Entity relationships (directed edges)"),
     table_body_cell("source_id, target_id, rel_type, weight, evidence_chunk_ids")],
    [table_body_cell("pm_summaries"), table_body_cell("7"),
     table_body_cell("Hierarchical summaries with embeddings"),
     table_body_cell("scope, scope_key, summary, embedding(768)")],
    [table_body_cell("pm_eval_runs"), table_body_cell("9"),
     table_body_cell("Weekly evaluation results"),
     table_body_cell("recall_at_5, mrr, ndcg_at_5, faithfulness_score, security_pass")],
    [table_body_cell("pm_metrics"), table_body_cell("9"),
     table_body_cell("15-minute health snapshots"),
     table_body_cell("chunk_count, entity_count, search_latency_ms, audit_errors")],
]
story.append(styled_table(schema_data, [28*mm, 12*mm, 42*mm, None]))

# ============================================================
# 8. SECURITY MODEL
# ============================================================
story.append(section_heading("8. Security Model", s))
story.append(Paragraph(
    "pureMind addresses the lethal trifecta -- the intersection of private data access, untrusted content "
    "ingestion, and exfiltration vectors (tool calls) -- through a layered defence model.",
    s["body"],
))
story.append(Spacer(1, 2*mm))

sec_data = [
    [table_header_cell("Surface"), table_header_cell("Threats"), table_header_cell("Mitigations")],
    [table_body_cell("Data Plane"), table_body_cell("Credential leakage, unauthorised vault access"),
     table_body_cell("Credentials externalised (secrets.env 0600). .gitignore blocks sensitive patterns. Tailscale segmentation.")],
    [table_body_cell("Model Plane"), table_body_cell("Prompt injection via ingested content"),
     table_body_cell("4-layer content sanitisation. <document> fencing. UNTRUSTED DATA markers. soul.md always wins.")],
    [table_body_cell("Tool Plane"), table_body_cell("Unauthorised integration calls, scope escalation"),
     table_body_cell("Python wrapper allowlists. @audited decorator. Rate limiting. Write ops fail closed.")],
    [table_body_cell("Governance"), table_body_cell("Unlogged operations, stale credentials"),
     table_body_cell("JSONL audit fallback. Dependency pinning. Quarterly review checklist.")],
]
story.append(styled_table(sec_data, [24*mm, 40*mm, None]))

story.append(Spacer(1, 2*mm))
story.append(Paragraph("8.1 Content Sanitisation Pipeline", s["h2"]))
sanitise_items = [
    "Layer 1: Control character removal + Unicode normalisation (NFKC). Strips null bytes, ASCII control chars, zero-width/format characters (RTL override, ZWS, ZWNJ)",
    "Layer 2: Injection pattern stripping -- instruction overrides, role injection, token boundary markers (OpenAI, Llama), prompt leaking attempts. Narrowed patterns to avoid false positives",
    "Layer 3: Fence escaping -- <document>, <system>, <instructions> tags neutralised (case-insensitive, with attribute handling). javascript: and data: URIs blocked",
    "Layer 4: Size enforcement -- hard truncation with marker. Configurable per-tool (30K default, 5K for heartbeat state)",
]
for item in sanitise_items:
    story.append(Paragraph(f"<bullet>&bull;</bullet> {e(item)}", s["bullet"]))

story.append(Spacer(1, 2*mm))
story.append(Paragraph("8.2 Permission Model", s["h2"]))
perm_data = [
    [table_header_cell("Integration"), table_header_cell("Read"), table_header_cell("Write"), table_header_cell("Blocked")],
    [table_body_cell("Gmail"), table_body_cell("search, get, list"), table_body_cell("create_draft only"),
     table_body_cell("send, reply, trash, delete")],
    [table_body_cell("GitHub"), table_body_cell("repos, PRs, issues"), table_body_cell("comment_pr, comment_issue, create_issue"),
     table_body_cell("merge, push, close, delete")],
    [table_body_cell("Calendar"), table_body_cell("list, get, search"), table_body_cell("None (read-only)"),
     table_body_cell("create, update, delete")],
    [table_body_cell("Telegram"), table_body_cell("read_channel"), table_body_cell("post_alert (alerts chat)"),
     table_body_cell("DMs, other chats")],
]
story.append(styled_table(perm_data, [24*mm, 34*mm, 40*mm, None]))

# ============================================================
# 9. VALUE PROPOSITION
# ============================================================
story.append(section_heading("9. Value Proposition", s))
story.append(Paragraph("9.1 Internal Value (PureTensor Operations)", s["h2"]))
internal_values = [
    ("Session Continuity", "Every session benefits from all prior sessions. Lessons learned, decisions made, "
     "contacts discovered, infrastructure changes -- all are permanently recorded and automatically loaded."),
    ("Operational Awareness", "The 30-minute heartbeat monitors Gmail, GitHub, Calendar, Telegram, and "
     "pending items. The operator receives Telegram summaries of what needs attention, even outside of "
     "active Claude Code sessions."),
    ("Institutional Knowledge", "Searchable hybrid retrieval over the entire operational history. "
     "Graph-augmented search understands relationships between entities. HyDE improves retrieval on "
     "vague or abstract queries."),
    ("Mistake Prevention", "Lessons from past incidents (rsync --delete, quantisation failures, wrong "
     "account deployments) are permanently in memory. The agent won't repeat mistakes."),
    ("Cost Efficiency", "Flat $200/month for unlimited LLM inference. No per-token costs, no API key "
     "management. Embeddings run on CPU (free). PostgreSQL shared with existing infrastructure."),
    ("Security", "All external content sanitised before Claude sees it. All integration calls audited. "
     "Credentials externalised. Prompt injection tested with adversarial payloads."),
]
for title, desc in internal_values:
    story.append(Paragraph(f"{B(title + '.')} {e(desc)}", s["body"]))
    story.append(Spacer(1, 0.5*mm))

story.append(Spacer(1, 2*mm))
story.append(Paragraph("9.2 External Value (Adaptable System)", s["h2"]))
story.append(Paragraph(
    "pureMind's architecture is deliberately simple and transferable. Any operation with a Claude Code "
    "Max subscription (or equivalent LLM access) can adapt the system. Key transferable components:",
    s["body"],
))
external_values = [
    "MemGPT-style memory hierarchy (Register/RAM/Disk) with daily reflection promotion",
    "Hybrid RAG pattern (pgvector + BM25 + RRF) that works at any scale",
    "Permission-enforced integration wrappers with audit logging",
    "Content sanitisation pipeline against prompt injection",
    "Graduated proactivity (observer > adviser > partner) for autonomous agents",
    "Evaluation framework with golden datasets for measurable retrieval quality",
    "Skills-as-Markdown pattern -- no framework dependencies, just instructions",
]
for item in external_values:
    story.append(Paragraph(f"<bullet>&bull;</bullet> {e(item)}", s["bullet"]))

story.append(Spacer(1, 2*mm))
story.append(Paragraph(
    "The system is LLM-agnostic at the skill/hook layer. While built for Claude Code, the patterns "
    "(Markdown skills, Python tools, PostgreSQL storage, systemd scheduling) work with any LLM that "
    "supports tool calling and file operations.",
    s["body"],
))

# ============================================================
# 10. OPERATIONAL GUIDE
# ============================================================
story.append(section_heading("10. Operational Guide", s))
story.append(Paragraph("10.1 Service Map", s["h2"]))

svc_data = [
    [table_header_cell("Component"), table_header_cell("Host"), table_header_cell("Schedule"), table_header_cell("Timer")],
    [table_body_cell("Heartbeat agent"), table_body_cell("TC (systemd)"),
     table_body_cell("Every 30 min (07:00-23:00 UTC)"), table_body_cell("puremind-heartbeat.timer")],
    [table_body_cell("Daily reflection"), table_body_cell("TC (systemd)"),
     table_body_cell("23:00 UTC daily"), table_body_cell("puremind-reflect.timer")],
    [table_body_cell("Eval harness"), table_body_cell("TC (systemd)"),
     table_body_cell("Saturday 04:00 UTC"), table_body_cell("puremind-eval.timer")],
    [table_body_cell("Metrics collector"), table_body_cell("TC (systemd)"),
     table_body_cell("Every 15 min"), table_body_cell("puremind-metrics.timer")],
    [table_body_cell("PostgreSQL"), table_body_cell("fox-n1:30433"),
     table_body_cell("Always-on (K3s)"), table_body_cell("K3s pod")],
    [table_body_cell("Grafana"), table_body_cell("fox-n1:30302"),
     table_body_cell("Always-on (K3s)"), table_body_cell("K3s pod")],
]
story.append(styled_table(svc_data, [28*mm, 28*mm, 42*mm, None]))

story.append(Spacer(1, 2*mm))
story.append(Paragraph("10.2 Daily Operations (Automatic)", s["h2"]))
daily_ops = [
    "Heartbeat runs every 30 min during waking hours, posts Telegram summary",
    "Metrics collected every 15 min, stored in pm_metrics, alerts on threshold breach",
    "Daily reflection at 23:00 UTC promotes knowledge from daily logs to memory.md",
    "Vault changes auto-indexed into pgvector via PostToolUse hook",
    "All file changes auto-committed to Git",
]
for item in daily_ops:
    story.append(Paragraph(f"<bullet>&bull;</bullet> {e(item)}", s["bullet"]))

story.append(Spacer(1, 2*mm))
story.append(Paragraph("10.3 Weekly Operations", s["h2"]))
weekly_ops = [
    "Review eval harness results (Saturday morning after 04:00 UTC run)",
    "Check pm_audit table for anomalies or error spikes",
    "Verify heartbeat-log.jsonl shows consistent 30-min runs",
    "Review and prune memory.md if approaching 8K token cap",
]
for item in weekly_ops:
    story.append(Paragraph(f"<bullet>&bull;</bullet> {e(item)}", s["bullet"]))

story.append(Spacer(1, 2*mm))
story.append(Paragraph("10.4 Quarterly Operations", s["h2"]))
quarterly_ops = [
    "Rotate DB password (update secrets.env, restart timers)",
    "Update pinned dependencies (pip install --upgrade, re-run tests)",
    "Evaluate embedding model against MTEB leaderboard, re-index if changed",
    "Run full security test suite (unit + Claude CLI integration tests)",
    "Review pm_audit for unusual patterns, check JSONL fallback file",
    "Verify .gitignore patterns cover all sensitive files",
]
for item in quarterly_ops:
    story.append(Paragraph(f"<bullet>&bull;</bullet> {e(item)}", s["bullet"]))

# ============================================================
# 11. TROUBLESHOOTING
# ============================================================
story.append(section_heading("11. Troubleshooting Guide", s))

troubles = [
    ("Heartbeat Not Firing",
     "Check timer status: systemctl status puremind-heartbeat.timer. Verify waking hours (07:00-23:00 UTC). "
     "Test manually: python3 ~/pureMind/tools/heartbeat.py --dry-run. Check DB connectivity: "
     "python3 -c \"from tools.db import get_conn; print(get_conn())\"."),
    ("Retrieval Degradation (Recall/MRR Drop)",
     "Check index freshness via pm_metrics or direct query on puremind_chunks (count, max updated_at). "
     "Re-index: python3 ~/pureMind/tools/index.py --full. Verify embedding model loads: "
     "python3 ~/pureMind/tools/embed.py \"test\". Expand golden dataset if coverage is thin."),
    ("Audit Errors or Missing Logs",
     "Check DB connectivity to fox-n1:30433. Review pm_audit WHERE result='error'. Check JSONL fallback: "
     "cat ~/.cache/puremind/audit_fallback.jsonl. If fallback has entries, DB was unavailable during those calls."),
    ("High Search Latency (P95 > 5s)",
     "Check active DB connections via pg_stat_activity. Review slow queries in pm_audit (avg/max latency_ms). "
     "Run VACUUM ANALYZE on puremind_chunks and pm_entities. If persistent, check HNSW index health."),
    ("Security Test Failure",
     "Run tests verbosely: pytest tests/test_sanitize.py -v --tb=long. Check if sanitize.py was modified "
     "(git diff). Verify payload coverage in tests/payloads.json. If a new attack vector was found, "
     "add pattern to Layer 2 and add test case."),
    ("Grafana Dashboard Not Loading",
     "Check Grafana health: curl -u admin:consort-crazy-curl http://100.103.248.9:30302/api/health. "
     "Re-deploy: bash ~/pureMind/ops/deploy_dashboard.sh. Verify PostgreSQL datasource configuration."),
    ("Memory.md Approaching Token Cap",
     "Run token count estimate. Archive low-signal entries to daily-logs/. The daily reflection is supposed "
     "to manage this automatically -- check if puremind-reflect.timer is running and if the reflection "
     "script is successfully archiving old entries."),
    ("Entity Graph Stale or Incorrect",
     "Run full re-extraction: python3 ~/pureMind/tools/extract.py --full. Review extracted entities "
     "in pm_entities for duplicates or incorrect types. Prune manually via SQL if needed."),
]
for title, desc in troubles:
    story.append(Paragraph(f"{B(title)}", s["h3"]))
    story.append(Paragraph(e(desc), s["body"]))
    story.append(Spacer(1, 1*mm))

# ============================================================
# 12. ALERTING MATRIX
# ============================================================
story.append(section_heading("12. Alerting Matrix", s))
alert_data = [
    [table_header_cell("Metric"), table_header_cell("Threshold"), table_header_cell("Action")],
    [table_body_cell("chunk_count"), table_body_cell("< 50"), table_body_cell("Index likely broken. Re-index immediately.")],
    [table_body_cell("audit_errors_1h"), table_body_cell("> 5"), table_body_cell("Check DB, review error details in pm_audit.")],
    [table_body_cell("search_latency_p95"), table_body_cell("> 10,000ms"), table_body_cell("VACUUM ANALYZE. Check connections.")],
    [table_body_cell("heartbeat_ok_24h"), table_body_cell("< 1"), table_body_cell("Check timer, verify waking hours window.")],
    [table_body_cell("embedding_freshness"), table_body_cell("> 48 hours"), table_body_cell("Check indexer. Run manual re-index.")],
    [table_body_cell("summary_freshness"), table_body_cell("> 168 hours"), table_body_cell("Run summarize.py --build-all.")],
    [table_body_cell("fallback_lines"), table_body_cell("> 0"), table_body_cell("DB was unavailable. Check connectivity.")],
]
story.append(styled_table(alert_data, [32*mm, 24*mm, None]))

# ============================================================
# 13. HOW-TO MANUAL FOR ENGINEERS
# ============================================================
story.append(section_heading("13. How-To Manual for Future Engineers", s))
story.append(Paragraph(
    "This section provides practical guidance for engineers who need to maintain, extend, or adapt "
    "the pureMind system.",
    s["body"],
))

story.append(Paragraph("13.1 Adding a New Integration", s["h2"]))
steps_integration = [
    "Create a new Python module in .claude/integrations/ following the pattern of gmail_integration.py",
    "Define allowed operations in an ALLOWED_OPS set. Use the @audited decorator from base.py on every function",
    "Add rate limit entry in base.py RATE_LIMITS dict",
    "If write operations exist, add to base.py WRITE_OPS dict (these fail closed when audit DB is unavailable)",
    "Create a Claude Code skill in .claude/skills/ describing the available functions and constraints",
    "Add the integration to heartbeat_config.json if the heartbeat should monitor it",
    "Test: run the integration CLI, verify audit entries appear in pm_audit",
]
for i, step in enumerate(steps_integration, 1):
    story.append(Paragraph(f"<bullet>{i}.</bullet> {e(step)}", s["bullet"]))

story.append(Spacer(1, 2*mm))
story.append(Paragraph("13.2 Adding a New Skill", s["h2"]))
steps_skill = [
    "Create a Markdown file in .claude/skills/ with YAML frontmatter (name, description, inputs, outputs, writes_to, side_effects)",
    "Describe the skill's steps as a sequence of tool/script invocations Claude Code should execute",
    "Reference existing tools (search.py, integrations) rather than writing new code",
    "Or use /self-evolve -- pureMind can create skills by analysing existing patterns in .claude/skills/",
    "Test: invoke the skill via Claude Code and verify it produces the expected output",
]
for i, step in enumerate(steps_skill, 1):
    story.append(Paragraph(f"<bullet>{i}.</bullet> {e(step)}", s["bullet"]))

story.append(Spacer(1, 2*mm))
story.append(Paragraph("13.3 Expanding the Golden Dataset", s["h2"]))
story.append(Paragraph(
    "The evaluation harness depends on ground-truth QA pairs for retrieval metrics. To expand:",
    s["body"],
))
steps_golden = [
    "Run: python3 ~/pureMind/tools/eval_golden.py seed --count 20",
    "This uses Claude CLI to generate QA pairs from the indexed vault content",
    "Review generated pairs for quality (remove ambiguous or multi-answer questions)",
    "Ground-truth chunk IDs are automatically assigned via search verification",
    "Re-run eval: python3 ~/pureMind/tools/eval_harness.py to see updated metrics",
]
for i, step in enumerate(steps_golden, 1):
    story.append(Paragraph(f"<bullet>{i}.</bullet> {e(step)}", s["bullet"]))

story.append(Spacer(1, 2*mm))
story.append(Paragraph("13.4 Changing the Embedding Model", s["h2"]))
steps_embed = [
    "Check MTEB leaderboard for candidates (balance quality vs speed for CPU inference)",
    "Update MODEL_NAME and MODEL_REVISION in tools/embed.py",
    "Update the vector dimension in migrations/ if the new model has different dimensionality",
    "Run full re-index: python3 ~/pureMind/tools/index.py --full",
    "Run full re-extraction for summaries: python3 ~/pureMind/tools/summarize.py --build-all",
    "Run eval harness and compare metrics against previous model",
]
for i, step in enumerate(steps_embed, 1):
    story.append(Paragraph(f"<bullet>{i}.</bullet> {e(step)}", s["bullet"]))

story.append(Spacer(1, 2*mm))
story.append(Paragraph("13.5 Graduating the Heartbeat Proactivity Level", s["h2"]))
story.append(Paragraph(
    "The heartbeat starts at observer level (read-only, log + alert). To graduate:",
    s["body"],
))
steps_graduate = [
    "Run at observer for 2+ weeks. Review heartbeat-log.jsonl for consistency and accuracy",
    "To promote to adviser: edit heartbeat_config.json, set proactivity_level to \"adviser\"",
    "At adviser: the heartbeat can create Gmail drafts and update pending.md. It still cannot send",
    "Monitor adviser behaviour for 2+ weeks. Check drafts for quality, pending updates for accuracy",
    "To promote to partner: set proactivity_level to \"partner\". Now it can comment on PRs/issues",
    "Never go directly from observer to partner. Each level must be proven stable",
]
for i, step in enumerate(steps_graduate, 1):
    story.append(Paragraph(f"<bullet>{i}.</bullet> {e(step)}", s["bullet"]))

story.append(Spacer(1, 2*mm))
story.append(Paragraph("13.6 Recovery Procedures", s["h2"]))
story.append(Paragraph(f"{B('Vault Recovery (from Git):')}", s["body"]))
story.append(Paragraph(
    "The vault is fully Git-versioned. Use git log --oneline -20 to find a good state, "
    "git stash to save current changes, git checkout <commit> to restore. Every write is committed, "
    "so time-travel is always available.",
    s["body"],
))
story.append(Paragraph(f"{B('Database Recovery:')}", s["body"]))
story.append(Paragraph(
    "PostgreSQL runs on K3s with Ceph-backed PVCs. If data loss occurs, restore from Ceph snapshot, "
    "then re-index (python3 tools/index.py --full), re-extract entities (python3 tools/extract.py --full), "
    "and rebuild summaries (python3 tools/summarize.py --build-all).",
    s["body"],
))
story.append(Paragraph(f"{B('Full Re-Index:')}", s["body"]))
story.append(Paragraph(
    "If search quality degrades or the database is rebuilt: run index.py --full (chunks + embeddings), "
    "extract.py --full (entity extraction), summarize.py --build-all (hierarchical summaries). "
    "This takes 10-30 minutes depending on vault size.",
    s["body"],
))

# ============================================================
# 14. KEY FILES REFERENCE
# ============================================================
story.append(section_heading("14. Key Files Reference", s))
files_data = [
    [table_header_cell("Path"), table_header_cell("Purpose")],
    [table_body_cell("memory/soul.md"), table_body_cell("Agent constitution, red lines, decision framework")],
    [table_body_cell("memory/user.md"), table_body_cell("Auto-evolving operator profile")],
    [table_body_cell("memory/memory.md"), table_body_cell("Promoted durable knowledge (8K cap)")],
    [table_body_cell("tools/search.py"), table_body_cell("Hybrid BM25+vector search with RRF, --graph, --hyde")],
    [table_body_cell("tools/index.py"), table_body_cell("Incremental + full indexing with SHA-256 change detection")],
    [table_body_cell("tools/embed.py"), table_body_cell("nomic-embed-text-v1.5 embedding via sentence-transformers")],
    [table_body_cell("tools/extract.py"), table_body_cell("Entity extraction via Claude CLI")],
    [table_body_cell("tools/summarize.py"), table_body_cell("RAPTOR-style hierarchical summaries")],
    [table_body_cell("tools/heartbeat.py"), table_body_cell("Proactive agent (gather/reason/act/notify)")],
    [table_body_cell("tools/sanitize.py"), table_body_cell("4-layer content sanitisation pipeline")],
    [table_body_cell("tools/credentials.py"), table_body_cell("Secret resolution (env > file > fail closed)")],
    [table_body_cell("tools/ingest.py"), table_body_cell("PDF/URL/doc ingestion with provenance")],
    [table_body_cell("tools/eval_harness.py"), table_body_cell("Weekly 6-metric evaluation")],
    [table_body_cell("tools/eval_golden.py"), table_body_cell("Golden QA dataset builder (55 pairs)")],
    [table_body_cell("tools/metrics_collector.py"), table_body_cell("15-min health checks + Telegram alerts")],
    [table_body_cell(".claude/integrations/base.py"), table_body_cell("Audit logging, rate limiting, @audited decorator")],
    [table_body_cell(".claude/integrations/*_integration.py"), table_body_cell("Gmail, GitHub, Calendar, Telegram wrappers")],
    [table_body_cell(".claude/skills/*.md"), table_body_cell("15 Claude Code skills (Markdown instructions)")],
    [table_body_cell("ops/RUNBOOK.md"), table_body_cell("Operational runbook")],
    [table_body_cell("ops/grafana/puremind-overview.json"), table_body_cell("Grafana dashboard definition")],
    [table_body_cell("SECURITY.md"), table_body_cell("Threat model and security procedures")],
    [table_body_cell("~/.config/puremind/secrets.env"), table_body_cell("Credentials (0600, outside vault)")],
]
story.append(styled_table(files_data, [58*mm, None]))

# ============================================================
# 15. CONCLUSION
# ============================================================
story.append(section_heading("15. Conclusion", s))
story.append(Paragraph(
    "pureMind transforms Claude Code from a stateless language model into a persistent, context-aware "
    "operational partner. Built in a single day across nine rigorous phases, the system provides:",
    s["body"],
))
conclusion_items = [
    "Compounding intelligence -- every session makes the next one better",
    "Proactive awareness -- the heartbeat watches when the operator is away",
    "Searchable institutional memory -- hybrid RAG with graph-augmented retrieval",
    "Layered security -- sanitisation, audit logging, permission enforcement, adversarial testing",
    "Measurable quality -- golden datasets, evaluation harness, Grafana monitoring",
    "Zero marginal cost -- flat-rate subscription absorbs all inference",
    "Full sovereignty -- all data on-premises, no external API dependencies",
]
for item in conclusion_items:
    story.append(Paragraph(f"<bullet>&bull;</bullet> {e(item)}", s["bullet"]))

story.append(Spacer(1, 3*mm))
story.append(Paragraph(
    "The architecture is deliberately simple: Claude Code + Markdown skills + Python tools + PostgreSQL. "
    "No framework dependencies, no model routing, no token budgets. The system is debuggable with cat "
    "and grep, extensible via new skills and integrations, and transferable to any operation with "
    "equivalent LLM access.",
    s["body"],
))
story.append(Spacer(1, 2*mm))
story.append(Paragraph(
    "pureMind is not a chatbot wrapper. It is a cognitive augmentation system that captures an evolving "
    "worldview, retrieves it under time pressure, and helps its operator act. The longer it runs, "
    "the more valuable it becomes.",
    s["body"],
))

story.append(Spacer(1, 6*mm))
story.append(Paragraph(f"{I('PT-2026-SB-DOC | 5 April 2026 | PureTensor, Inc.')}", s["meta"]))
story.append(Paragraph(f"{I('Classification: CONFIDENTIAL')}", s["meta"]))

# Build
tpl.build(story)
print(f"Generated: {OUTPUT}")
