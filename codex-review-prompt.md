# Codex Review: pureMind Phase 3 -- Memory Search & Hybrid RAG

## Your Role

You are a senior systems architect reviewing Phase 3 of **pureMind**, a sovereign second brain project. Your review is constructive and actionable. You do NOT make any changes -- you read, analyze, and produce structured suggestions.

## Context

pureMind is a cognitive augmentation system built on:
- **Claude Code CLI** (Max 20x subscription) as the sole LLM
- **Obsidian-compatible vault** (Markdown-native, Git-versioned) at `~/pureMind/`
- **pgvector + PostgreSQL FTS** for hybrid retrieval (this phase)
- **sentence-transformers on CPU** for embeddings (nomic-embed-text-v1.5, 768-dim)
- **Ray cluster** (160 CPUs, 2 GPUs, 200 GbE) as compute backbone (not yet used -- local embedding is <2s for current corpus)

Phase 1 (Memory Foundation) created the vault skeleton. Phase 2 (Context Persistence & Hooks) wired lifecycle hooks and daily reflection cron. Both were Codex-reviewed with fixes applied.

Phase 3 (Memory Search & Hybrid RAG) adds hybrid search over the vault so Claude Code can retrieve relevant knowledge on demand. The vault currently has 17 markdown files (~54KB) producing 106 chunks. The PRD defines 9 phases over 56 days. Phases 1-3 are complete. Phases 4-9 are planned.

### Phase 3 Deliverables

1. **Database schema** (`~/pureMind/migrations/001_puremind_rag.sql`) -- `puremind_chunks` table in the existing `vantage` database (PostgreSQL 15.4, pgvector 0.5.1). Columns: id, file_path, heading_path, chunk_index, content, embedding vector(768), content_tsv tsvector (generated), file_hash, timestamps. UNIQUE(file_path, chunk_index). 4 indexes: HNSW cosine (m=16, ef_construction=200), GIN on tsvector, btree on file_path, btree on file_hash.

2. **Heading-aware chunker** (`~/pureMind/tools/chunker.py`) -- Splits markdown on heading boundaries (#{1-4}), tracks heading breadcrumb paths ("## Section > ### Subsection"), merges sections <100 chars with previous, falls back to fixed-window splitting (2048-char max, 20% overlap) for oversized sections.

3. **Embedding module** (`~/pureMind/tools/embed.py`) -- nomic-ai/nomic-embed-text-v1.5 via sentence-transformers. Three entry points: `embed_batch()` (raw, no prefix), `embed_query()` (search_query prefix), `embed_documents()` (search_document prefix). Singleton model loading via `@lru_cache`. `embedding_to_pgvector()` converts to pgvector literal format.

4. **Indexing script** (`~/pureMind/tools/index.py`) -- Full re-index (`--full`) or incremental mode (SHA-256 change detection). Glob patterns for indexable files, explicit exclusion of soul.md/user.md. Per-file pipeline: read -> hash -> chunk -> embed_documents -> DELETE old -> INSERT with ON CONFLICT UPDATE. Orphan cleanup for removed files. Modes: `--full`, `--verbose`, `--quiet`.

5. **Hybrid search tool** (`~/pureMind/tools/search.py`) -- BM25 (tsvector + plainto_tsquery + ts_rank_cd) + vector (pgvector cosine distance) with Reciprocal Rank Fusion (k=60). Overfetch 3x for better fusion. CLI with `--limit`, `--json`, `--file-filter` options. Synchronous psycopg2 (not async -- simpler for Claude Code Bash calls).

6. **Claude Code skill** (`~/pureMind/.claude/skills/puremind-search.md`) -- Skill definition wrapping search.py. Symlinked to `~/.claude/skills/` for global availability.

7. **Auto-index hook** (`~/tensor-scripts/hooks/puremind_index.sh`) -- PostToolUse hook for Edit/Write events. Triggers incremental re-index in background when vault .md files change. Registered in `~/.claude/settings.json`.

8. **Reflection RAG enhancement** (`~/pureMind/.claude/hooks/daily_reflect.py`) -- Modified existing Phase 2 script. `extract_topics()` grabs headings + bold terms from daily log. `get_rag_context()` calls search.py as subprocess to fetch historical context. RAG results injected into the Claude reflection prompt via `{historical_context}` placeholder.

9. **Documentation updates** -- CLAUDE.md (search tool docs, indexing commands, component list), README.md (Phase 3 status, updated "What is live now"), project README (Phase 3 complete), daily log (Phase 3 session entry).

### Database Environment

- **Host:** fox-n1 (K3s), accessible at 100.103.248.9:30433 (NodePort)
- **Database:** `vantage` (shared with Alexandria/Nexus -- separate tables)
- **User:** `raguser` / `REDACTED_DB_PASSWORD`
- **Existing tables:** `facts` (Nexus memory_rag), `rag_documents`, `rag_chunks` (Alexandria)
- **New table:** `puremind_chunks` (this phase)
- **pgvector version:** 0.5.1

### Production RAG Reference

The existing Nexus RAG at `~/nexus/memory_rag.py` (329 lines) was used as the reference pattern. It uses: asyncpg, async BM25+vector, RRF k=60, nomic-embed-text via Ollama/vLLM. pureMind uses the same RRF logic but synchronous psycopg2 and sentence-transformers directly (Ollama is down).

## What to Review

### 1. Read the full GitHub repo

Clone or read every file in `puretensor/second-brain`. Also read `tensor-scripts/hooks/puremind_index.sh`. Understand the data flow: vault files -> chunker -> embed -> pgvector -> search -> RRF fusion -> formatted output.

### 2. Evaluate against these criteria

**A. Schema Design (001_puremind_rag.sql)**
- Is the UNIQUE(file_path, chunk_index) constraint correct? What happens if a file is re-chunked with more/fewer chunks than before (e.g., after content editing)?
- Is `bigserial` appropriate for the id column given the corpus size (~100 chunks, growing to ~1000)?
- Is `smallint` for chunk_index sufficient? What if a very long file produces >32767 chunks?
- Are the HNSW index parameters (m=16, ef_construction=200) appropriate for the corpus scale?
- Is the `content_tsv` GENERATED ALWAYS column correct? Does it handle edge cases (empty content, non-English text)?
- Is there a missing `updated_at` trigger? The default is `now()` at insert, but the ON CONFLICT UPDATE in index.py sets it explicitly. Is that consistent?
- Should there be a NOT NULL constraint on `embedding`? Currently nullable -- is that intentional for partial indexing?

**B. Chunking Quality (chunker.py)**
- Is the heading regex (`^#{1,4}\s+`) correct? Does it handle edge cases: headings in code blocks, headings with inline code, headings with links, `#####` or `######` headings?
- Is the 100-char merge threshold appropriate? Could it create chunks that lose semantic coherence by merging unrelated short sections?
- Does the fixed-window fallback handle multi-byte characters correctly? (pos/end are char indices, but content may have unicode)
- Is the overlap calculation (20%) correct? Does it create natural break points or split mid-word/mid-line?
- What happens with files that have no headings at all (e.g., a template or flat markdown)?
- Is the `file_path` parameter used? It's passed but not referenced in the function body.

**C. Embedding Pipeline (embed.py)**
- Is the `@lru_cache` singleton safe for the sentence-transformers model? Could it leak memory in long-running processes (e.g., hooks)?
- Is `trust_remote_code=True` a security concern? What does it enable?
- The `embed_batch()` function does NOT use the "search_document:" prefix, but `embed_documents()` does. Is this inconsistency intentional? Is `embed_batch()` ever called, or is it dead code?
- Is `normalize_embeddings=True` correct for cosine distance in pgvector? (Cosine on normalized vectors = dot product)
- Is the 8-decimal precision in `embedding_to_pgvector()` sufficient for retrieval quality?
- Error handling: what happens if the model fails to load (disk full, corrupted cache, incompatible transformers version)?

**D. Indexing Correctness (index.py)**
- The incremental mode compares SHA-256 hashes. Is there a race condition where a file is modified between `collect_files()` and `file_hash()`?
- The DELETE + INSERT pattern for re-indexing a file: is it correct that it deletes ALL chunks first, then inserts? If the embed step fails between DELETE and INSERT, the file loses all chunks. Should this be wrapped in a transaction?
- Is `conn.commit()` per file the right granularity? Would a single transaction for the whole batch be safer or riskier?
- The `get_stored_hashes()` uses `SELECT DISTINCT file_path, file_hash`. If a file has multiple chunks with different hashes (shouldn't happen, but edge case), which hash wins?
- Is the `sys.path.insert(0, str(TOOLS_DIR))` for importing chunker/embed a clean pattern? Could it cause import shadowing?
- DB connection string is hardcoded. Same pattern as Nexus, but worth noting for Phase 8 (Security Hardening)?
- What happens if the database is unreachable? Is the error message useful?
- The orphan cleanup iterates `stored_files - current_files`. If the vault has a new glob pattern added later, does this delete chunks for files that are valid but not matched by old patterns?

**E. Search Quality (search.py)**
- Is the RRF fusion implementation correct? Compare against the Nexus `memory_rag.py` pattern line-by-line.
- Is the BM25 overfetch (3x) sufficient? With a small corpus of 106 chunks, does overfetch even matter?
- Is the cosine score calculation `1 - (embedding <=> %s::vector)` correct for pgvector's cosine distance operator?
- Does `plainto_tsquery` handle edge cases well (e.g., queries with special characters, very short queries like "GPU")?
- Is the file_filter using `LIKE %s` with a user-provided prefix safe from SQL injection? (psycopg2 parameterizes, but double-check)
- The format_results truncates content at 500 chars. Is this the right balance for Claude Code context consumption?
- Connection management: a new psycopg2 connection per search call. Is this acceptable for the expected call frequency?
- What happens when the table is empty (first run before any indexing)?

**F. Auto-Index Hook (puremind_index.sh)**
- The hook runs `python3 index.py --quiet &` (background). Could this create a race condition where two concurrent edits trigger two parallel indexing runs?
- Is `$CLAUDE_FILE_PATH` always set by Claude Code for Edit/Write events? What if it's empty or contains spaces?
- The glob pattern `*/pureMind/*.md` -- does this match subdirectories correctly? What about `~/pureMind/knowledge/puretensor/lessons.md`?
- Should the hook debounce? If Claude writes 10 files in quick succession, 10 index.py processes spawn in parallel.
- What happens if the hook fails (Python not found, psycopg2 not installed)? Does it block Claude Code?

**G. Reflection RAG Enhancement (daily_reflect.py modifications)**
- `extract_topics()` grabs headings and bold terms. Is this sufficient for generating good RAG queries? Are there better heuristics?
- `get_rag_context()` joins top 5 topics into a single query string. Is this optimal? Would multiple targeted queries produce better results?
- The subprocess call uses `sys.executable` (correct) but hardcodes `--limit 5`. Is this the right balance between context size and relevance?
- What happens if search.py times out (30s timeout)? Does it degrade gracefully to "(RAG search error)"?
- The RAG context is injected into the reflection prompt. Could a very long RAG result (5 chunks * 300 chars = 1500 chars) push the total prompt over Claude CLI's limits?
- Is the dry-run mode correctly updated to show RAG context extraction?

**H. Code Quality & Patterns**
- Are all imports clean? Any unused imports?
- Error handling: are database errors caught and reported clearly?
- Is the `sys.path.insert` pattern used in index.py and search.py the best approach for local imports?
- Are there any potential memory leaks (model caching, connection leaks)?
- Is the logging consistent across all tools (print vs stderr)?
- Are there type hints that are missing or incorrect?
- Is the CLI argument parsing robust? What about invalid args?

**I. Phase 4 Readiness**
- Does Phase 3's output create the right foundation for Phase 4 (Direct Integrations)?
- Is the search tool easily callable from new integration scripts?
- Are the embedding and chunking modules reusable for new content sources (emails, calendar events)?
- Are there structural decisions in Phase 3 that will create friction in later phases (especially Phase 7: Knowledge Graph)?
- Is the database schema extensible for metadata columns that Phase 4+ might need?

### 3. Produce structured output

Format your review as follows. This exact format is required -- the operator will copy-paste it into Claude Code for triage and execution.

```
## PHASE 3 REVIEW: pureMind Memory Search & Hybrid RAG

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

### Phase 4 Readiness Score
[X/10] -- [one sentence justification]

### Missing from Phase 3
[list anything the PRD specified for Phase 3 that was not delivered]
```

## Constraints

- **DO NOT modify any files.** This is a read-only review.
- **DO NOT create branches, PRs, or issues.** Output is text only.
- Be specific. "Improve error handling" is not actionable. "Wrap the `embed_documents()` call at index.py:146 in a try/except that catches RuntimeError and logs the file path + chunk count before re-raising" is.
- Reference specific files and line numbers where relevant.
- Assume the reviewer (the operator) is deeply technical. No need to explain basic concepts.
- The project is for a real company (PureTensor, Inc.), not a hobby. Treat it accordingly.
- The Ray cluster (160 CPUs, 2 GPUs, 200 GbE) is the compute backbone for Phases 7 and 9. Note any Phase 3 decisions that help or hinder distributed processing later.
- The Nexus RAG (`~/nexus/memory_rag.py`) is the production reference. Deviations from that pattern should be justified or flagged.
- The hook scripts live in TWO repos: `tensor-scripts` (puremind_index.sh) and `second-brain` (vault, tools, daily_reflect.py). Review both.
- Credentials are hardcoded in tool scripts (DB_DSN). This is acceptable for sovereign infrastructure and matches the Nexus pattern. Do not flag it as a security issue unless you have a specific attack scenario.
