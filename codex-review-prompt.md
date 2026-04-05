# Codex Review: pureMind Phase 5 -- Skills Framework

## Your Role

You are a senior systems architect reviewing Phase 5 of **pureMind**, a sovereign second brain project. Your review is constructive and actionable. You do NOT make any changes -- you read, analyze, and produce structured suggestions.

## Context

pureMind is a cognitive augmentation system built on:
- **Claude Code CLI** (Max 20x subscription) as the sole LLM
- **Obsidian-compatible vault** (Markdown-native, Git-versioned) at `~/pureMind/`
- **pgvector + PostgreSQL FTS** for hybrid retrieval (Phase 3)
- **sentence-transformers on CPU** for embeddings (nomic-embed-text-v1.5, 768-dim)
- **Permission-enforced integrations** (Phase 4): Gmail, GitHub, Calendar, Telegram with audit logging
- **Ray cluster** (160 CPUs, 2 GPUs, 200 GbE) as compute backbone

Phases 1-4 are complete and Codex-reviewed with fixes applied:
- Phase 1: Memory Foundation (vault, identity files, Git)
- Phase 2: Context Persistence & Hooks (session hooks, daily reflection cron)
- Phase 3: Memory Search & Hybrid RAG (pgvector + BM25, search/index/chunker/embed tools)
- Phase 4: Direct Integrations (Gmail/GitHub/Calendar/Telegram wrappers, audit logging, rate limiting, permission enforcement)

Phase 5 (Skills Framework) extends the skill library from 6 to 14 skills, adds one new Python tool (`ingest.py`), and delivers the `/self-evolve` meta-skill.

### Phase 5 Deliverables

1. **Writing style template** (`~/pureMind/templates/writing-style.md`) -- Long-form writing conventions: output types with word count targets (blog 1200-1600, report 800-1200, memo 200-500, technical unbounded), voice rules (no em dashes, concise, technical, numbers over narratives).

2. **8 new skill files** in `~/pureMind/.claude/skills/`:

   | Skill | Type | What It Composes |
   |---|---|---|
   | `/draft-email` | Pure markdown | gmail_integration.py + templates/email-style.md |
   | `/reflect` | Pure markdown | daily_reflect.py (standalone CLI, --dry-run, --date) |
   | `/project-status` | Pure markdown | search.py + github_integration.py + pending.md |
   | `/diagram` | Pure markdown | Mermaid generation instructions + save to knowledge/diagrams/ |
   | `/write` | Pure markdown | templates/writing-style.md + user.md + search.py |
   | `/research` | Pure markdown | search.py (vault-first) + WebSearch/WebFetch (web) + save to knowledge/research/ |
   | `/ingest` | Pure markdown + Python tool | tools/ingest.py for file handling, WebFetch for URLs |
   | `/self-evolve` | Pure markdown meta-skill | Reads existing skills, creates new .md files following patterns |

3. **Ingestion tool** (`~/pureMind/tools/ingest.py`, ~200 lines) -- CLI tool for ingesting external content into the vault:
   - Input: PDF (pdfplumber/PyMuPDF extraction), markdown, text, stdin (piped from WebFetch)
   - Output: Markdown file in `knowledge/<category>/<slug>.md` with YAML provenance frontmatter
   - Auto-triggers incremental re-index via index.py
   - Guards: 1MB text size limit, slug collision handling, no binary storage in vault

4. **Documentation updates** -- CLAUDE.md (Phase 5 skills section with all 14 skills), README.md (Phase 5 status), project README.

### Existing Infrastructure (from Phases 1-4)

**Skills pattern:** Markdown files in `.claude/skills/` with YAML frontmatter (`name`, `description`), bash code blocks for CLI invocations, and a Constraints section. Auto-discovered by Claude Code.

**Tools (Python CLIs in `tools/`):**
- `search.py` -- hybrid RAG (BM25 + pgvector, RRF fusion k=60). CLI: `python3 search.py "<query>" --limit 5 --json --file-filter prefix`
- `index.py` -- full/incremental vault indexing (SHA-256 change detection). Glob: `knowledge/**/*.md`, `projects/**/*.md`, `daily-logs/*.md`, etc.
- `chunker.py` -- heading-aware markdown chunker (2048-char max, 20% overlap, fence-aware)
- `embed.py` -- nomic-embed-text-v1.5 embeddings via sentence-transformers

**Integration wrappers (`.claude/integrations/`):**
- `base.py` -- @audited decorator (inspect.signature for arg capture), file-based rate limiter (/tmp/puremind_rate/), audit logging to pm_audit, deny() raises PermissionError, write ops fail closed
- `gmail_integration.py` -- search, get, list_inbox, list_unread, create_draft. Account allowlist (hal, ops, personal). Blocks send/reply/trash/delete/spam/filters.
- `github_integration.py` -- list_repos (limit 100), list_prs, get_pr, list_issues, get_issue, comment_pr, comment_issue, create_issue. Blocks merge/push/close/delete.
- `calendar_integration.py` -- list_events (days mapping: 1->today, >1->upcoming --limit), get_event, search_events. Blocks create/update/delete.
- `telegram_integration.py` -- post_alert (chat_id enforced at API layer), read_channel (filtered to alerts chat). Blocks DMs/other chats.

**Daily reflection** (`daily_reflect.py`):
- Systemd timer at 23:00 UTC
- Invokes `claude -p --output-format json --max-turns 1`
- Parses JSON: add_to_memory, remove_from_memory, pending_updates, summary
- Enforces memory.md 5120-byte cap
- RAG context from search.py before reflection
- Archives logs >30 days, commits, re-indexes

**Templates:**
- `templates/email-style.md` -- Email voice (warm, concise, match sender tone, CC ops@, plain text, draft-first)
- `templates/briefing-note.md` -- Briefing format (attention items first, numbers > narratives)
- `templates/writing-style.md` -- Long-form writing (NEW in Phase 5)

### PRD Success Metric (p16)

> "6+ skills operational. /briefing produces useful output. /self-evolve creates a working new skill."

Current state: 14 skills operational. /briefing tested and working. /self-evolve instructions and guard rails in place.

## What to Review

### 1. Read the full Phase 5 codebase

Read every file in `~/pureMind/.claude/skills/`, `~/pureMind/tools/ingest.py`, and `~/pureMind/templates/writing-style.md`. Also read the Phase 5 sections in `~/pureMind/CLAUDE.md` and `~/pureMind/README.md`. Understand how skills compose the existing tools and integrations.

### 2. Evaluate against these criteria

**A. Skill Quality & Completeness**
- Do the skill instructions actually work? For each skill, trace the bash commands: do the CLI paths exist, are the flags correct, do the tools accept those arguments?
- Are there any skills that promise capabilities the underlying tools don't support? (e.g., does `/research` reference WebSearch/WebFetch correctly? Does `/reflect` use the right flags for daily_reflect.py?)
- Is the `/draft-email` skill correctly enforcing the CC ops@puretensor.ai rule, or does it just mention it in prose?
- Does `/project-status` correctly map project names to GitHub repo names? Is the mapping table accurate?
- Are the skill instructions clear enough that Claude Code can follow them without ambiguity, or are there vague steps that could produce inconsistent results?
- Is there unnecessary duplication between skills? Do any skills overlap in a way that creates confusion?

**B. Ingestion Tool (ingest.py)**
- Is the PDF extraction robust? What happens with scanned PDFs (image-only, no text layer)? Does pdfplumber handle this, or does it silently return empty text?
- Is the slug generation safe? What about titles with only non-ASCII characters (e.g., Icelandic "Sjovarpakkning")? Does the regex strip everything, producing "untitled"?
- Is the `--from-stdin` mode correctly handling piped content? What if the pipe is empty or the content is binary?
- Is the 1MB size guard checked at the right point? (After extraction but before file write?)
- Is the frontmatter generation correct YAML? What if the title contains quotes, colons, or other YAML-special characters?
- Does the collision handling (-2, -3 suffix) have a bounded loop, or could it spin indefinitely?
- Is the incremental re-index trigger correct? Does it call index.py with the right arguments? Could it create a race condition with the PostToolUse hook's own index trigger?
- Is `_read_source()` handling file encodings correctly? What about UTF-16 or Latin-1 encoded files?
- Error handling: are all failure modes (file not found, permission denied, PDF parse failure, disk full) caught with useful messages?
- Is there any path traversal risk in the `--category` argument? Could `--category ../../.ssh` write outside the knowledge directory?

**C. Self-Evolve Skill (self-evolve.md)**
- Are the guard rails sufficient? Could Claude Code be convinced by a user to create a skill that bypasses the permission model (e.g., a skill that calls `_call_gmail('hal', 'send', ...)` directly)?
- Is the "CANNOT create new Python tools autonomously" rule enforceable? The skill says to draft code for review, but Claude Code could just write the file anyway.
- Does the skill provide enough pattern context for Claude Code to create consistent, high-quality skills, or would the output be unpredictable?
- Is the example in the skill (creating a `/cluster-status` skill) syntactically valid and would it work if executed?
- Should /self-evolve log to the audit table (pm_audit) when a new skill is created? Currently it only logs to the daily log.

**D. Research Skill (research.md)**
- The vault-first protocol says "always search vault before web." Is this enforceable, or just advisory? Could Claude Code skip the vault search?
- Is the citation format well-defined enough for consistent output? The skill shows numbered references but doesn't specify how to format vault citations vs web citations.
- The skill saves to `knowledge/research/<topic-slug>.md`. Who generates the slug -- Claude Code or a tool? Is there a risk of inconsistent naming?
- Is the YAML frontmatter template in the skill syntactically correct? Would Claude Code produce valid YAML from it?
- Could web research introduce prompt injection content into the vault? (External web pages could contain instruction-like text that gets saved and later retrieved via RAG.)

**E. Template Quality (writing-style.md)**
- Are the word count targets realistic and consistent with how Claude Code generates content?
- Does the template cover enough voice rules to produce consistent output, or is it too vague?
- Is the "no em dashes" rule from CLAUDE.md correctly replicated here?
- For Bretalon blog posts, the template says "the operator must approve before publishing." Is this just prose, or is there a mechanism?
- Should the template reference the PureTensor branded PDF template for report output?

**F. Reflect Skill (reflect.md)**
- The skill says to run `daily_reflect.py` directly. What happens if the user runs `/reflect` at 14:00 and then the cron fires at 23:00 -- does the cron re-process the same day, potentially overwriting the manual reflection's changes?
- Does `--dry-run` show enough information for the operator to evaluate the proposed changes?
- What happens if daily_reflect.py is run for a date that has no daily log?
- Is there a risk of memory.md exceeding the 5120-byte cap if /reflect is run multiple times in one day?

**G. Diagram Skill (diagram.md)**
- Does the skill handle the `knowledge/diagrams/` directory creation? What if it doesn't exist yet?
- Is the heredoc pattern in the skill correct? The fenced code block inside a heredoc could cause shell parsing issues.
- Does the skill give enough guidance for Claude Code to produce correct Mermaid syntax, or is it too open-ended?
- Should diagrams reference a color scheme from a template file?

**H. Code Quality & Patterns**
- Does ingest.py follow the same patterns as the existing tools (search.py, index.py)? Or does it introduce inconsistencies?
- Are all paths in skill files absolute (`~/pureMind/...`), or are some relative? Relative paths could break if the working directory changes.
- Is the skill YAML frontmatter consistent across all 14 skills? Do all have `name` and `description`?
- Are there any unused imports or dead code in ingest.py?
- Is the skill documentation in CLAUDE.md consistent with the actual skill files?

**I. Security Considerations**
- Could a malicious PDF exploit pdfplumber/PyMuPDF to execute code during ingestion?
- Could web content ingested via /ingest (piped from WebFetch) contain prompt injection payloads that persist in the vault and activate during later RAG retrieval?
- Does /self-evolve create a privilege escalation path? A skill created by /self-evolve has the same execution context as any other skill.
- Are the YAML frontmatter fields in ingested documents sanitized? Could a crafted title or source_url inject YAML that alters the frontmatter parsing?
- Does the `--category` parameter in ingest.py allow writing outside the knowledge/ directory?

**J. Phase 6 Readiness**
- Phase 6 is "Heartbeat & Proactive Agent" -- a cron-triggered process that gathers state from all integrations, reasons via Claude, acts within permissions, and notifies. Do the Phase 5 skills provide the right building blocks?
- Is `/briefing` a good starting template for the heartbeat's "gather" phase? What would need to change?
- Are the skill instructions machine-readable enough for the heartbeat agent to invoke them programmatically, or are they designed only for interactive use?
- Could the heartbeat agent use `/self-evolve` to create its own skills? Is that desirable or dangerous?
- The PRD specifies proactivity levels (Observer -> Adviser -> Partner -> Autonomous). Do the Phase 5 skills map cleanly to these levels?

### 3. Produce structured output

Format your review as follows. This exact format is required -- the operator will copy-paste it into Claude Code for triage and execution.

```
## PHASE 5 REVIEW: pureMind Skills Framework

### Overall Assessment
[2-3 sentences: overall quality, biggest strength, biggest concern]

### Critical Issues (fix now)
- [ ] **[ISSUE-ID]:** [description] | File: [path] | Why: [reason]
- [ ] ...

### Important Improvements (should do)
- [ ] **[ISSUE-ID]:** [description] | File: [path] | Why: [reason]
- [ ] ...

### Nice-to-Haves (consider for later)
- [ ] **[ISSUE-ID]:** [description] | File: [path] | Why: [reason]
- [ ] ...

### Structural Observations
[bullet list of architectural observations -- things that aren't wrong but worth noting for future phases]

### Phase 6 Readiness Score
[X/10] -- [one sentence justification]

### Missing from Phase 5
[list anything the PRD specified for Phase 5 that was not delivered]
```

## Constraints

- **DO NOT modify any files.** This is a read-only review.
- **DO NOT create branches, PRs, or issues.** Output is text only.
- Be specific. "Improve the research skill" is not actionable. "The /research skill at research.md:35 saves to `knowledge/research/<topic-slug>.md` but Claude Code generates the slug ad-hoc with no slugification function -- use ingest.py's `_slugify()` for consistency" is.
- Reference specific files and line numbers where relevant.
- Assume the reviewer (the operator) is deeply technical. No need to explain basic concepts.
- The project is for a real company (PureTensor, Inc.), not a hobby. Treat it accordingly.
- Skills are markdown instructions, not executable code. They guide Claude Code's behavior. Evaluate them as instructions, not programs.
- The Ray cluster (160 CPUs, 2 GPUs, 200 GbE) is the compute backbone for later phases. Note any Phase 5 decisions that help or hinder distributed processing.
- The /self-evolve skill is the most architecturally significant deliverable. Give it disproportionate attention.
- Credentials are hardcoded in tool scripts (DB_DSN). This matches the sovereign infrastructure pattern. Do not flag it as a security issue unless you have a specific attack scenario.
- The ingestion tool deliberately does NOT fetch URLs itself (Claude Code's WebFetch handles that). This is a design decision, not a gap.
