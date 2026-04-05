You are reviewing Phase 7 (Knowledge Graph & Advanced Retrieval) of pureMind, a sovereign second brain system. This phase adds entity extraction from vault content, a PostgreSQL knowledge graph, graph-augmented search, HyDE (hypothetical document embeddings), hierarchical summaries, and multilingual FTS. All Claude interactions use the single-turn CLI pattern: `claude -p --output-format json --max-turns 1`.

Score each area 1-10 and provide specific, actionable findings. For each finding, classify severity as Critical (C), Important (I), or Nice-to-have (N). Use IDs like A-01, B-02, etc.

## Evaluation Areas

A. Entity Extraction Pipeline (extract.py architecture, Claude CLI prompt design, JSON parsing, validation, upsert logic)
B. Graph Traversal (recursive CTE correctness, cycle handling, depth limiting, performance at scale)
C. Graph-Augmented Search (entity matching from query text, 3-way RRF fusion, graph+hybrid result merging)
D. HyDE Implementation (hypothetical document generation, embedding strategy, fallback behavior, BM25+HyDE fusion)
E. Hierarchical Summaries (RAPTOR-style tree, file/project/period/vault levels, embedding of summaries, build_summary_tree)
F. Multilingual FTS (unaccent usage, language parameter handling, SQL injection surface in lang parameter)
G. Database Schema & Migrations (pm_entities, pm_relationships, pm_summaries table design, indexes, constraints)
H. Connection Management (db.py shared connection, connection lifecycle across tools, connection leaks)
I. Daily Reflection Integration (entity extraction hook in daily_reflect.py, failure isolation, import safety)
J. Edge Cases & Resilience (empty graphs, no entity matches, Claude CLI failures, large vaults, concurrent runs)

## Test Results (from build session)

- **Module import:** `from tools.search import search, graph_search, hyde_search` -- OK
- **Entity extraction (single file):** `extract.py --file knowledge/puretensor/lessons.md` -- 34 entities, 38 relationships
- **Full extraction:** `extract.py --full` -- 176 entities, 288 relationships across vault
  - Entity types: technology=78, concept=39, project=26, person=17, event=11, decision=5
  - Relationship types: uses=136, part_of=62, mentions=50, depends_on=21, works_on=14, decided=3, created_by=2
- **Graph search:** `search.py "How is PureClaw connected to pgvector?" --graph` -- returned graph entities (PureClaw, fox-n1, HAL, K3s, Telegram, etc.) with graph-sourced chunks fused via RRF
- **HyDE search:** `search.py "What should I focus on next week?" --hyde` -- returned relevant daily log entries for vague query
- **Standard search unchanged:** `search.py "pgvector" --limit 3 --json` -- same results as pre-Phase 7
- **Multilingual:** `search.py "Sjova" --lang simple` -- found Icelandic contact (Thorir Oskarsson at Sjova-Almennar)
- **Summarization:** `summarize.py --file projects/puremind/README.md` -- 690-char summary generated and stored
- **Schema:** All 3 tables created with indexes, pm_summaries has HNSW index on embedding column

## What To Look For

1. **SQL injection in lang parameter:** The `lang` variable is interpolated into an f-string SQL query. Is this safe? Only `'simple'` goes through unaccent; other values are used as PostgreSQL FTS config names via f-string.
2. **Recursive CTE termination:** Does the `UNION` (not `UNION ALL`) guarantee termination? What happens with cycles in the graph?
3. **Connection lifecycle:** graph_search() opens a connection, closes it, then calls search() which opens another. Is this wasteful? Are there leak paths?
4. **Entity name matching:** extract_query_entities uses `LIKE '%' || name || '%'` which is a full table scan. At 176 entities this is fine -- at 10K?
5. **Prompt injection surface:** extract.py passes vault file content directly into Claude CLI prompt. Could a malicious markdown file manipulate extraction?
6. **Summary embedding cost:** summarize_file calls embed_query (loads model) per file. build_summary_tree could call this dozens of times. Is the model cached?
7. **Error handling in daily_reflect integration:** The try/except catches all exceptions silently. Is this the right tradeoff?

## Files Under Review

### tools/extract.py (NEW -- ~370 lines, entity extraction pipeline)
```python
#!/usr/bin/env python3
"""pureMind entity extraction -- extract entities and relationships from vault content.

Uses Claude CLI (single-turn) to extract structured entities and relationships,
then stores them in pm_entities and pm_relationships tables for GraphRAG traversal.

Usage:
    python3 extract.py                          # Incremental (changed files)
    python3 extract.py --full                   # Full re-extraction
    python3 extract.py --file memory/memory.md  # Single file
"""

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# H-02: ensure parent dir is on path so `from tools.x` works when invoked directly
_PARENT = str(Path(__file__).resolve().parent.parent)
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

import psycopg2

from tools.db import get_conn

PUREMIND_ROOT = Path(__file__).resolve().parent.parent
VAULT_ROOT = PUREMIND_ROOT

# Files to extract entities from (same patterns as index.py)
EXTRACT_PATTERNS = [
    "knowledge/**/*.md",
    "projects/**/*.md",
    "daily-logs/*.md",
    "memory/memory.md",
    "memory/pending.md",
    "templates/*.md",
]

# Excluded from extraction (loaded at session start, identity-level)
EXCLUDE_FILES = {"memory/soul.md", "memory/user.md"}

ENTITY_TYPES = {"person", "project", "technology", "concept", "decision", "event"}
REL_TYPES = {"mentions", "depends_on", "part_of", "works_on", "uses", "decided", "created_by"}

EXTRACTION_PROMPT = """\
Analyze this document and extract entities and relationships.

Entity types: person, project, technology, concept, decision, event.
Relationship types: mentions, depends_on, part_of, works_on, uses, decided, created_by.

Return a JSON object with exactly these keys:
{{
  "entities": [
    {{"name": "exact canonical name", "type": "person|project|technology|concept|decision|event", "description": "one-line description"}}
  ],
  "relationships": [
    {{"source": "entity name", "target": "entity name", "type": "mentions|depends_on|part_of|works_on|uses|decided|created_by", "weight": 0.3-1.0}}
  ]
}}

Rules:
- Be selective. Only extract entities that are important for understanding the document.
- Normalize names consistently: "PureClaw" not "pureclaw", "Heimir Helgason" not "Heimir".
- Weight: 1.0 = central topic of the document, 0.5 = significantly mentioned, 0.3 = briefly referenced.
- Both source and target in relationships must appear in the entities list.
- Output ONLY valid JSON. No markdown fencing, no commentary.

Source file: {source_file}

Document content:
{content}
"""


def _get_vault_files() -> list[Path]:
    """Get all extractable vault files."""
    files = set()
    for pattern in EXTRACT_PATTERNS:
        for f in VAULT_ROOT.glob(pattern):
            rel = str(f.relative_to(VAULT_ROOT))
            if rel not in EXCLUDE_FILES and f.is_file():
                files.add(f)
    return sorted(files)


def _file_hash(path: Path) -> str:
    """SHA-256 hash of file content."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _get_stored_hashes(conn) -> dict[str, str]:
    """Get file hashes from pm_entities metadata to detect changes."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT metadata->>'source_file' as f, metadata->>'file_hash' as h
            FROM pm_entities WHERE metadata->>'source_file' IS NOT NULL
        """)
        return {row[0]: row[1] for row in cur.fetchall() if row[0] and row[1]}


def call_claude_extract(content: str, source_file: str) -> dict | None:
    """Call Claude CLI to extract entities and relationships from content."""
    # Truncate very long content to avoid context issues
    if len(content) > 30000:
        content = content[:30000] + "\n\n[...truncated...]"

    prompt = EXTRACTION_PROMPT.format(source_file=source_file, content=content)

    try:
        result = subprocess.run(
            ["claude", "-p", "--output-format", "json", "--max-turns", "1"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            print(f"  ERROR: Claude CLI exited {result.returncode}", file=sys.stderr)
            return None

        outer = json.loads(result.stdout)
        text = outer.get("result", "")
        if not text:
            return None

        # Strip markdown fencing
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            return None

        # Validate structure
        entities = parsed.get("entities", [])
        relationships = parsed.get("relationships", [])

        valid_entities = []
        for e in entities:
            if (isinstance(e, dict) and isinstance(e.get("name"), str)
                    and e.get("type") in ENTITY_TYPES):
                valid_entities.append(e)

        entity_names = {e["name"] for e in valid_entities}
        valid_rels = []
        for r in relationships:
            if (isinstance(r, dict)
                    and r.get("source") in entity_names
                    and r.get("target") in entity_names
                    and r.get("type") in REL_TYPES):
                weight = r.get("weight", 0.5)
                if isinstance(weight, (int, float)):
                    r["weight"] = max(0.1, min(1.0, float(weight)))
                else:
                    r["weight"] = 0.5
                valid_rels.append(r)

        return {"entities": valid_entities, "relationships": valid_rels}

    except subprocess.TimeoutExpired:
        print(f"  ERROR: Claude CLI timed out", file=sys.stderr)
        return None
    except (json.JSONDecodeError, KeyError) as e:
        print(f"  ERROR: Failed to parse Claude output: {e}", file=sys.stderr)
        return None


def _find_chunk_ids(conn, file_path: str) -> list[int]:
    """Find chunk IDs in puremind_chunks for a given file."""
    rel_path = file_path
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM puremind_chunks WHERE file_path = %s", (rel_path,))
        return [row[0] for row in cur.fetchall()]


def upsert_entity(conn, name: str, entity_type: str, description: str,
                  chunk_ids: list[int], source_file: str, file_hash: str) -> int:
    """Insert or update an entity. Returns entity ID."""
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO pm_entities (name, entity_type, description, source_chunk_ids, metadata, updated_at)
            VALUES (%s, %s, %s, %s, %s, now())
            ON CONFLICT (name, entity_type) DO UPDATE SET
                description = COALESCE(EXCLUDED.description, pm_entities.description),
                source_chunk_ids = (
                    SELECT ARRAY(SELECT DISTINCT unnest FROM unnest(
                        pm_entities.source_chunk_ids || EXCLUDED.source_chunk_ids
                    ))
                ),
                metadata = pm_entities.metadata || EXCLUDED.metadata,
                updated_at = now()
            RETURNING id
        """, (name, entity_type, description, chunk_ids,
              json.dumps({"source_file": source_file, "file_hash": file_hash})))
        return cur.fetchone()[0]


def upsert_relationship(conn, source_id: int, target_id: int, rel_type: str,
                        weight: float, chunk_ids: list[int]) -> int:
    """Insert or update a relationship. Returns relationship ID."""
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO pm_relationships (source_id, target_id, rel_type, weight, evidence_chunk_ids)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (source_id, target_id, rel_type) DO UPDATE SET
                weight = GREATEST(pm_relationships.weight, EXCLUDED.weight),
                evidence_chunk_ids = (
                    SELECT ARRAY(SELECT DISTINCT unnest FROM unnest(
                        pm_relationships.evidence_chunk_ids || EXCLUDED.evidence_chunk_ids
                    ))
                )
            RETURNING id
        """, (source_id, target_id, rel_type, weight, chunk_ids))
        return cur.fetchone()[0]


def extract_from_file(conn, file_path: Path, file_hash: str, verbose: bool = False) -> tuple[int, int]:
    """Extract entities and relationships from a single file.

    Returns (entity_count, relationship_count).
    """
    rel_path = str(file_path.relative_to(VAULT_ROOT))
    content = file_path.read_text(encoding="utf-8", errors="replace")

    if len(content.strip()) < 50:
        if verbose:
            print(f"  Skipping {rel_path} (too short)")
        return 0, 0

    if verbose:
        print(f"  Extracting from {rel_path}...")

    result = call_claude_extract(content, rel_path)
    if not result:
        return 0, 0

    chunk_ids = _find_chunk_ids(conn, rel_path)
    entity_ids = {}

    # Upsert entities
    for e in result["entities"]:
        eid = upsert_entity(
            conn, e["name"], e["type"], e.get("description", ""),
            chunk_ids, rel_path, file_hash
        )
        entity_ids[e["name"]] = eid

    # Upsert relationships
    rel_count = 0
    for r in result["relationships"]:
        src_id = entity_ids.get(r["source"])
        tgt_id = entity_ids.get(r["target"])
        if src_id and tgt_id:
            upsert_relationship(conn, src_id, tgt_id, r["type"], r["weight"], chunk_ids)
            rel_count += 1

    return len(result["entities"]), rel_count


def extract_from_text(conn, text: str, source_hint: str = "inline") -> tuple[int, int]:
    """Extract entities from arbitrary text (for daily reflection integration)."""
    result = call_claude_extract(text, source_hint)
    if not result:
        return 0, 0

    entity_ids = {}
    for e in result["entities"]:
        eid = upsert_entity(conn, e["name"], e["type"], e.get("description", ""),
                            [], source_hint, "")
        entity_ids[e["name"]] = eid

    rel_count = 0
    for r in result["relationships"]:
        src_id = entity_ids.get(r["source"])
        tgt_id = entity_ids.get(r["target"])
        if src_id and tgt_id:
            upsert_relationship(conn, src_id, tgt_id, r["type"], r["weight"], [])
            rel_count += 1

    return len(result["entities"]), rel_count


def extract_all(full: bool = False, verbose: bool = True) -> tuple[int, int]:
    """Extract entities from all vault files.

    Args:
        full: If True, re-extract all files. If False, skip unchanged (SHA-256).
        verbose: Print progress.

    Returns:
        (total_entities, total_relationships)
    """
    conn = get_conn()
    if conn is None:
        return 0, 0

    files = _get_vault_files()
    if verbose:
        print(f"Found {len(files)} extractable files")

    stored_hashes = {} if full else _get_stored_hashes(conn)
    total_entities = 0
    total_rels = 0
    extracted = 0

    for f in files:
        rel_path = str(f.relative_to(VAULT_ROOT))
        current_hash = _file_hash(f)

        if not full and stored_hashes.get(rel_path) == current_hash:
            continue

        e_count, r_count = extract_from_file(conn, f, current_hash, verbose)
        total_entities += e_count
        total_rels += r_count
        extracted += 1

        if verbose and e_count:
            print(f"    -> {e_count} entities, {r_count} relationships")

    conn.close()

    if verbose:
        print(f"\nExtraction complete: {extracted} files processed, "
              f"{total_entities} entities, {total_rels} relationships")

    return total_entities, total_rels


def main():
    parser = argparse.ArgumentParser(description="pureMind entity extraction")
    parser.add_argument("--full", action="store_true",
                        help="Re-extract all files (ignore change detection)")
    parser.add_argument("--file", type=str,
                        help="Extract from a single file (vault-relative path)")
    parser.add_argument("--verbose", "-v", action="store_true", default=True,
                        help="Print progress (default: True)")
    parser.add_argument("--quiet", "-q", action="store_true",
                        help="Suppress output")

    args = parser.parse_args()
    verbose = not args.quiet

    if args.file:
        # Single file extraction
        file_path = VAULT_ROOT / args.file
        if not file_path.exists():
            print(f"ERROR: File not found: {file_path}", file=sys.stderr)
            sys.exit(1)
        conn = get_conn()
        if conn is None:
            sys.exit(1)
        fhash = _file_hash(file_path)
        e, r = extract_from_file(conn, file_path, fhash, verbose)
        conn.close()
        if verbose:
            print(f"Extracted {e} entities, {r} relationships from {args.file}")
    else:
        extract_all(full=args.full, verbose=verbose)


if __name__ == "__main__":
    main()
```

### tools/search.py (MODIFIED -- +280 lines: graph_search, hyde_search, --lang)
```python
#!/usr/bin/env python3
"""pureMind hybrid search -- BM25 + vector with RRF fusion.

Searches the puremind_chunks table in the vantage database using both
full-text (BM25 via tsvector) and semantic (pgvector cosine) search,
fused via Reciprocal Rank Fusion (k=60).

Usage:
    python3 search.py "query text"                  # Default: 5 results
    python3 search.py "query text" --limit 10       # Custom limit
    python3 search.py "query text" --json           # JSON output
    python3 search.py "query text" --file-filter knowledge/  # Filter by path prefix
"""

import json
import subprocess
import sys
from pathlib import Path

# H-02: ensure parent dir is on path so `from tools.x` works when invoked directly
_PARENT = str(Path(__file__).resolve().parent.parent)
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

import psycopg2

from tools.db import DB_DSN, get_conn
from tools.embed import embed_query, embedding_to_pgvector
RRF_K = 60  # RRF constant (matches Nexus)


def search(query: str, limit: int = 5, file_filter: str | None = None,
           lang: str = "english") -> list[dict]:
    """Hybrid search: BM25 + vector similarity fused via RRF.

    Args:
        lang: FTS language config. Use 'simple' for non-English or mixed content.
    """
    overfetch = limit * 3
    conn = get_conn()
    if conn is None:
        return []

    try:
        # Build optional WHERE clause for file filter
        where_extra = ""
        params_extra = []
        if file_filter:
            where_extra = " AND file_path LIKE %s"
            params_extra = [f"{file_filter}%"]

        # 1. BM25 search via tsvector
        # For non-English, use unaccent to strip diacritics
        if lang == "simple":
            tsquery_expr = "plainto_tsquery('simple', unaccent(%s))"
        else:
            tsquery_expr = f"plainto_tsquery('{lang}', %s)"

        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, file_path, heading_path, chunk_index, content,
                       ts_rank_cd(content_tsv, {tsquery_expr}) AS score
                FROM puremind_chunks
                WHERE content_tsv @@ {tsquery_expr}{where_extra}
                ORDER BY score DESC
                LIMIT %s
                """,
                [query, query] + params_extra + [overfetch],
            )
            bm25_rows = [
                {"id": r[0], "file_path": r[1], "heading_path": r[2],
                 "chunk_index": r[3], "content": r[4], "score": float(r[5])}
                for r in cur.fetchall()
            ]

        # 2. Vector search via pgvector
        query_vec = embed_query(query)
        vec_str = embedding_to_pgvector(query_vec)

        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, file_path, heading_path, chunk_index, content,
                       1 - (embedding <=> %s::vector) AS score
                FROM puremind_chunks
                WHERE embedding IS NOT NULL{where_extra}
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                [vec_str] + params_extra + [vec_str, overfetch],
            )
            sem_rows = [
                {"id": r[0], "file_path": r[1], "heading_path": r[2],
                 "chunk_index": r[3], "content": r[4], "score": float(r[5])}
                for r in cur.fetchall()
            ]

        # 3. RRF fusion
        return _rrf_fuse(bm25_rows, sem_rows, limit)

    finally:
        conn.close()


def _rrf_fuse(bm25_results: list[dict], sem_results: list[dict], limit: int) -> list[dict]:
    """Fuse BM25 and semantic results via Reciprocal Rank Fusion."""
    scores: dict[int, float] = {}
    items: dict[int, dict] = {}

    for rank, item in enumerate(bm25_results):
        fid = item["id"]
        scores[fid] = scores.get(fid, 0) + 1.0 / (RRF_K + rank)
        if fid not in items:
            item["sources"] = ["bm25"]
            items[fid] = item
        else:
            items[fid]["sources"].append("bm25")

    for rank, item in enumerate(sem_results):
        fid = item["id"]
        scores[fid] = scores.get(fid, 0) + 1.0 / (RRF_K + rank)
        if fid not in items:
            item["sources"] = ["semantic"]
            items[fid] = item
        else:
            items[fid]["sources"].append("semantic")

    ranked = sorted(scores.items(), key=lambda x: -x[1])
    results = []
    for fid, rrf_score in ranked[:limit]:
        item = items[fid]
        results.append({
            "id": item["id"],
            "file_path": item["file_path"],
            "heading_path": item["heading_path"],
            "content": item["content"],
            "rrf_score": round(rrf_score, 6),
            "sources": item["sources"],
        })

    return results


def extract_query_entities(conn, query: str) -> list[int]:
    """Find entity IDs whose names appear in the query text (case-insensitive).

    Lightweight -- no LLM call. Matches entity names as substrings of the query.
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, name FROM pm_entities
            WHERE lower(%s) LIKE '%%' || lower(name) || '%%'
            ORDER BY length(name) DESC
        """, (query,))
        return [row[0] for row in cur.fetchall()]


def traverse_graph(conn, entity_ids: list[int], max_depth: int = 2) -> list[dict]:
    """Traverse the entity graph via recursive CTE.

    Returns connected entities with depth, plus their source chunk IDs.
    """
    if not entity_ids:
        return []

    with conn.cursor() as cur:
        cur.execute("""
            WITH RECURSIVE graph AS (
                SELECT id, name, entity_type, source_chunk_ids, 0 AS depth
                FROM pm_entities WHERE id = ANY(%s)
                UNION
                SELECT DISTINCT e.id, e.name, e.entity_type, e.source_chunk_ids, g.depth + 1
                FROM graph g
                JOIN pm_relationships r ON (r.source_id = g.id OR r.target_id = g.id)
                JOIN pm_entities e ON (
                    e.id = CASE WHEN r.source_id = g.id THEN r.target_id ELSE r.source_id END
                )
                WHERE g.depth < %s
            )
            SELECT id, name, entity_type, source_chunk_ids, MIN(depth) as depth
            FROM graph
            GROUP BY id, name, entity_type, source_chunk_ids
            ORDER BY depth, name
        """, (entity_ids, max_depth))
        return [
            {"id": row[0], "name": row[1], "entity_type": row[2],
             "source_chunk_ids": row[3] or [], "depth": row[4]}
            for row in cur.fetchall()
        ]


def graph_search(query: str, limit: int = 5, file_filter: str | None = None) -> list[dict]:
    """Graph-augmented search: find entities in query, traverse graph, retrieve chunks.

    Fuses graph-sourced chunks with standard hybrid search results via RRF.
    """
    conn = get_conn()
    if conn is None:
        return search(query, limit=limit, file_filter=file_filter)

    try:
        # Find entities mentioned in the query
        entity_ids = extract_query_entities(conn, query)

        if not entity_ids:
            # No entity matches -- fall back to standard hybrid search
            conn.close()
            return search(query, limit=limit, file_filter=file_filter)

        # Traverse graph to find connected entities
        graph_entities = traverse_graph(conn, entity_ids, max_depth=2)

        # Collect all chunk IDs from graph traversal
        chunk_ids = set()
        for entity in graph_entities:
            for cid in entity["source_chunk_ids"]:
                chunk_ids.add(cid)

        # Retrieve graph-sourced chunks
        graph_rows = []
        if chunk_ids:
            where_extra = ""
            params_extra = []
            if file_filter:
                where_extra = " AND file_path LIKE %s"
                params_extra = [f"{file_filter}%"]

            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT id, file_path, heading_path, chunk_index, content
                    FROM puremind_chunks
                    WHERE id = ANY(%s){where_extra}
                """, [list(chunk_ids)] + params_extra)
                for rank, r in enumerate(cur.fetchall()):
                    graph_rows.append({
                        "id": r[0], "file_path": r[1], "heading_path": r[2],
                        "chunk_index": r[3], "content": r[4],
                        "score": 1.0 / (1 + rank),  # decreasing score by fetch order
                    })

    finally:
        conn.close()

    # Get standard hybrid results
    hybrid_results = search(query, limit=limit * 2, file_filter=file_filter)

    # Fuse: hybrid results + graph results via RRF
    # Treat graph as a third signal alongside BM25 and semantic
    scores: dict[int, float] = {}
    items: dict[int, dict] = {}

    for rank, item in enumerate(hybrid_results):
        fid = item["id"]
        scores[fid] = scores.get(fid, 0) + 1.0 / (RRF_K + rank)
        items[fid] = item

    for rank, item in enumerate(graph_rows):
        fid = item["id"]
        scores[fid] = scores.get(fid, 0) + 1.0 / (RRF_K + rank)
        if fid not in items:
            item["sources"] = ["graph"]
            item["rrf_score"] = 0
            items[fid] = item
        else:
            if "graph" not in items[fid].get("sources", []):
                items[fid]["sources"].append("graph")

    ranked = sorted(scores.items(), key=lambda x: -x[1])
    results = []
    for fid, rrf_score in ranked[:limit]:
        item = items[fid]
        item["rrf_score"] = round(rrf_score, 6)
        results.append(item)

    # Attach graph context to results
    if graph_entities:
        entity_names = [e["name"] for e in graph_entities[:10]]
        for r in results:
            r["graph_entities"] = entity_names

    return results


def hyde_search(query: str, limit: int = 5, file_filter: str | None = None) -> list[dict]:
    """HyDE search: generate hypothetical answer, embed it, search with that embedding.

    Uses Claude CLI to generate a hypothetical document that would answer the query,
    then embeds that document and uses it for vector search. Fuses with BM25 via RRF.
    """
    # Generate hypothetical answer via Claude CLI
    hyde_prompt = (
        f"Write a short paragraph (80-120 words) that would be a perfect answer "
        f"to this question, as if it existed in a personal knowledge base. "
        f"Output ONLY the paragraph, no preamble.\n\nQuestion: {query}"
    )

    hypothetical_doc = None
    try:
        result = subprocess.run(
            ["claude", "-p", "--output-format", "json", "--max-turns", "1"],
            input=hyde_prompt,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            outer = json.loads(result.stdout)
            hypothetical_doc = outer.get("result", "").strip()
    except (subprocess.TimeoutExpired, json.JSONDecodeError):
        pass

    if not hypothetical_doc:
        # HyDE generation failed -- fall back to standard search
        return search(query, limit=limit, file_filter=file_filter)

    # Embed the hypothetical document
    hyde_vec = embed_query(hypothetical_doc)
    vec_str = embedding_to_pgvector(hyde_vec)

    conn = get_conn()
    if conn is None:
        return search(query, limit=limit, file_filter=file_filter)

    overfetch = limit * 3
    try:
        # BM25 on original query
        where_extra = ""
        params_extra = []
        if file_filter:
            where_extra = " AND file_path LIKE %s"
            params_extra = [f"{file_filter}%"]

        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, file_path, heading_path, chunk_index, content,
                       ts_rank_cd(content_tsv, plainto_tsquery('english', %s)) AS score
                FROM puremind_chunks
                WHERE content_tsv @@ plainto_tsquery('english', %s){where_extra}
                ORDER BY score DESC
                LIMIT %s
                """,
                [query, query] + params_extra + [overfetch],
            )
            bm25_rows = [
                {"id": r[0], "file_path": r[1], "heading_path": r[2],
                 "chunk_index": r[3], "content": r[4], "score": float(r[5])}
                for r in cur.fetchall()
            ]

        # Vector search with HyDE embedding (instead of query embedding)
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, file_path, heading_path, chunk_index, content,
                       1 - (embedding <=> %s::vector) AS score
                FROM puremind_chunks
                WHERE embedding IS NOT NULL{where_extra}
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                [vec_str] + params_extra + [vec_str, overfetch],
            )
            hyde_rows = [
                {"id": r[0], "file_path": r[1], "heading_path": r[2],
                 "chunk_index": r[3], "content": r[4], "score": float(r[5])}
                for r in cur.fetchall()
            ]

        return _rrf_fuse(bm25_rows, hyde_rows, limit)

    finally:
        conn.close()


def format_results(results: list[dict]) -> str:
    """Format results as readable markdown."""
    if not results:
        return "No results found."

    lines = []

    # Show graph entities if present
    if results and "graph_entities" in results[0]:
        entities = results[0]["graph_entities"]
        lines.append(f"**Graph entities:** {', '.join(entities)}")
        lines.append("")

    for i, r in enumerate(results, 1):
        sources = "+".join(r.get("sources", []))
        lines.append(f"### {i}. {r['file_path']}")
        if r.get("heading_path"):
            lines.append(f"**Path:** {r['heading_path']}")
        lines.append(f"**Score:** {r['rrf_score']:.4f} ({sources})")
        lines.append("")
        # Truncate long content for display
        content = r["content"]
        if len(content) > 500:
            content = content[:500] + "..."
        lines.append(content)
        lines.append("")

    return "\n".join(lines)


def main():
    args = sys.argv[1:]
    if not args or args[0].startswith("-"):
        print("Usage: search.py <query> [--limit N] [--json] [--file-filter prefix] [--graph] [--hyde]", file=sys.stderr)
        sys.exit(1)

    query = args[0]
    limit = 5
    json_output = False
    file_filter = None
    use_graph = False
    use_hyde = False
    lang = "english"

    i = 1
    while i < len(args):
        if args[i] == "--limit" and i + 1 < len(args):
            limit = int(args[i + 1])
            i += 2
        elif args[i] == "--json":
            json_output = True
            i += 1
        elif args[i] == "--file-filter" and i + 1 < len(args):
            file_filter = args[i + 1]
            i += 2
        elif args[i] == "--graph":
            use_graph = True
            i += 1
        elif args[i] == "--hyde":
            use_hyde = True
            i += 1
        elif args[i] == "--lang" and i + 1 < len(args):
            lang = args[i + 1]
            i += 2
        else:
            i += 1

    if use_graph:
        results = graph_search(query, limit=limit, file_filter=file_filter)
    elif use_hyde:
        results = hyde_search(query, limit=limit, file_filter=file_filter)
    else:
        results = search(query, limit=limit, file_filter=file_filter, lang=lang)

    if json_output:
        print(json.dumps(results, indent=2))
    else:
        print(format_results(results))


if __name__ == "__main__":
    main()
```

### tools/summarize.py (NEW -- ~310 lines, hierarchical summaries)
```python
#!/usr/bin/env python3
"""pureMind hierarchical summaries -- RAPTOR-style tree-structured summaries.

Builds summaries at multiple abstraction levels:
  leaf = chunk -> mid = file -> high = project -> top = vault

Summaries are embedded and stored in pm_summaries for abstraction-level retrieval.

Usage:
    python3 summarize.py --file knowledge/puretensor/lessons.md
    python3 summarize.py --project puremind
    python3 summarize.py --period 2026-04-01 2026-04-05
    python3 summarize.py --build-all          # Full summary tree
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

_PARENT = str(Path(__file__).resolve().parent.parent)
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

from tools.db import get_conn
from tools.embed import embed_query, embedding_to_pgvector

VAULT_ROOT = Path(__file__).resolve().parent.parent


def _call_claude_summarize(text: str, scope_hint: str) -> str | None:
    """Call Claude CLI to generate a summary."""
    prompt = (
        f"Summarize this {scope_hint} in 2-4 concise sentences. "
        f"Focus on key decisions, technologies, and relationships. "
        f"Output ONLY the summary paragraph, no preamble.\n\n{text[:20000]}"
    )

    try:
        result = subprocess.run(
            ["claude", "-p", "--output-format", "json", "--max-turns", "1"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=90,
        )
        if result.returncode != 0:
            return None

        outer = json.loads(result.stdout)
        summary = outer.get("result", "").strip()
        return summary if summary else None

    except (subprocess.TimeoutExpired, json.JSONDecodeError):
        return None


def upsert_summary(conn, scope: str, scope_key: str, summary: str,
                   chunk_ids: list[int] | None = None) -> int | None:
    """Insert or update a summary with embedding."""
    embedding = embed_query(summary)
    vec_str = embedding_to_pgvector(embedding)

    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO pm_summaries (scope, scope_key, summary, embedding, source_chunk_ids)
            VALUES (%s, %s, %s, %s::vector, %s)
            ON CONFLICT (scope, scope_key) DO UPDATE SET
                summary = EXCLUDED.summary,
                embedding = EXCLUDED.embedding,
                source_chunk_ids = EXCLUDED.source_chunk_ids,
                updated_at = now()
            RETURNING id
        """, (scope, scope_key, summary, vec_str, chunk_ids or []))
        return cur.fetchone()[0]


def summarize_file(conn, file_path: str, verbose: bool = False) -> str | None:
    """Generate a file-level summary from its chunks."""
    abs_path = VAULT_ROOT / file_path
    if not abs_path.exists():
        if verbose:
            print(f"  File not found: {file_path}", file=sys.stderr)
        return None

    content = abs_path.read_text(encoding="utf-8", errors="replace")
    if len(content.strip()) < 100:
        return None

    if verbose:
        print(f"  Summarizing {file_path}...")

    summary = _call_claude_summarize(content, f"document ({file_path})")
    if not summary:
        return None

    # Find chunk IDs for this file
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM puremind_chunks WHERE file_path = %s", (file_path,))
        chunk_ids = [row[0] for row in cur.fetchall()]

    upsert_summary(conn, "file", file_path, summary, chunk_ids)

    if verbose:
        print(f"    -> {len(summary)} chars")

    return summary


def summarize_project(conn, project_name: str, verbose: bool = False) -> str | None:
    """Generate a project-level summary by aggregating file summaries."""
    project_dir = VAULT_ROOT / "projects" / project_name
    if not project_dir.exists():
        if verbose:
            print(f"  Project directory not found: {project_name}", file=sys.stderr)
        return None

    # Collect file summaries for this project
    file_summaries = []
    with conn.cursor() as cur:
        cur.execute("""
            SELECT scope_key, summary FROM pm_summaries
            WHERE scope = 'file' AND scope_key LIKE %s
        """, (f"projects/{project_name}/%",))
        for row in cur.fetchall():
            file_summaries.append(f"[{row[0]}]: {row[1]}")

    # Also include knowledge files related to the project
    with conn.cursor() as cur:
        cur.execute("""
            SELECT scope_key, summary FROM pm_summaries
            WHERE scope = 'file' AND scope_key LIKE %s
        """, (f"knowledge/{project_name}/%",))
        for row in cur.fetchall():
            file_summaries.append(f"[{row[0]}]: {row[1]}")

    if not file_summaries:
        # No file summaries yet -- generate from raw files
        if verbose:
            print(f"  No file summaries for {project_name}, generating from raw files...")
        for md_file in sorted(project_dir.glob("**/*.md")):
            rel = str(md_file.relative_to(VAULT_ROOT))
            s = summarize_file(conn, rel, verbose)
            if s:
                file_summaries.append(f"[{rel}]: {s}")

    if not file_summaries:
        return None

    combined = "\n".join(file_summaries)
    if verbose:
        print(f"  Aggregating {len(file_summaries)} file summaries for project {project_name}...")

    summary = _call_claude_summarize(combined, f"project ({project_name})")
    if not summary:
        return None

    upsert_summary(conn, "project", project_name, summary)

    if verbose:
        print(f"    -> {len(summary)} chars")

    return summary


def summarize_period(conn, start_date: str, end_date: str, verbose: bool = False) -> str | None:
    """Summarize daily logs for a date range."""
    logs_dir = VAULT_ROOT / "daily-logs"
    combined_content = []

    # Iterate date range
    from datetime import timedelta
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    current = start

    while current <= end:
        log_file = logs_dir / f"{current.strftime('%Y-%m-%d')}.md"
        if log_file.exists():
            content = log_file.read_text(encoding="utf-8", errors="replace")
            if content.strip():
                combined_content.append(f"[{current.strftime('%Y-%m-%d')}]:\n{content[:5000]}")
        current += timedelta(days=1)

    if not combined_content:
        if verbose:
            print(f"  No daily logs found for {start_date} to {end_date}")
        return None

    combined = "\n\n".join(combined_content)
    scope_key = f"{start_date}:{end_date}"

    if verbose:
        print(f"  Summarizing {len(combined_content)} days ({start_date} to {end_date})...")

    summary = _call_claude_summarize(combined, f"daily logs ({start_date} to {end_date})")
    if not summary:
        return None

    upsert_summary(conn, "period", scope_key, summary)

    if verbose:
        print(f"    -> {len(summary)} chars")

    return summary


def build_summary_tree(verbose: bool = True) -> dict:
    """Build the full summary hierarchy: files -> projects -> vault."""
    conn = get_conn()
    if conn is None:
        return {"files": 0, "projects": 0, "vault": False}

    stats = {"files": 0, "projects": 0, "vault": False}

    # Level 1: File summaries
    if verbose:
        print("Level 1: File summaries")

    from tools.index import collect_files, VAULT_ROOT as IDX_ROOT
    for f in collect_files():
        rel = str(f.relative_to(IDX_ROOT))
        s = summarize_file(conn, rel, verbose)
        if s:
            stats["files"] += 1

    # Level 2: Project summaries
    if verbose:
        print(f"\nLevel 2: Project summaries")

    projects_dir = VAULT_ROOT / "projects"
    if projects_dir.exists():
        for pdir in sorted(projects_dir.iterdir()):
            if pdir.is_dir():
                s = summarize_project(conn, pdir.name, verbose)
                if s:
                    stats["projects"] += 1

    # Level 3: Vault summary (aggregate all project summaries)
    if verbose:
        print(f"\nLevel 3: Vault summary")

    with conn.cursor() as cur:
        cur.execute("SELECT scope_key, summary FROM pm_summaries WHERE scope = 'project'")
        project_summaries = [f"[{row[0]}]: {row[1]}" for row in cur.fetchall()]

    if project_summaries:
        combined = "\n".join(project_summaries)
        vault_summary = _call_claude_summarize(combined, "entire knowledge vault")
        if vault_summary:
            upsert_summary(conn, "vault", "vault", vault_summary)
            stats["vault"] = True
            if verbose:
                print(f"  Vault summary: {len(vault_summary)} chars")

    conn.close()

    if verbose:
        print(f"\nSummary tree: {stats['files']} files, {stats['projects']} projects, "
              f"vault={'yes' if stats['vault'] else 'no'}")

    return stats


def main():
    parser = argparse.ArgumentParser(description="pureMind hierarchical summaries")
    parser.add_argument("--file", type=str, help="Summarize a single file (vault-relative path)")
    parser.add_argument("--project", type=str, help="Summarize a project")
    parser.add_argument("--period", nargs=2, metavar=("START", "END"),
                        help="Summarize daily logs for date range (YYYY-MM-DD)")
    parser.add_argument("--build-all", action="store_true", help="Build full summary tree")
    parser.add_argument("--verbose", "-v", action="store_true", default=True)
    parser.add_argument("--quiet", "-q", action="store_true")

    args = parser.parse_args()
    verbose = not args.quiet

    conn = get_conn()
    if conn is None:
        sys.exit(1)

    if args.file:
        s = summarize_file(conn, args.file, verbose)
        if verbose and s:
            print(f"\n{s}")
        conn.close()
    elif args.project:
        s = summarize_project(conn, args.project, verbose)
        if verbose and s:
            print(f"\n{s}")
        conn.close()
    elif args.period:
        s = summarize_period(conn, args.period[0], args.period[1], verbose)
        if verbose and s:
            print(f"\n{s}")
        conn.close()
    elif args.build_all:
        conn.close()
        build_summary_tree(verbose)
    else:
        parser.print_help()
        conn.close()


if __name__ == "__main__":
    main()
```

### tools/db.py (NEW -- shared DB connection, Phase 7 Step 0)
```python
"""Shared database connection for pureMind tools.

Single source of truth for DB_DSN and connection helpers.
Used by search.py, index.py, extract.py, summarize.py.
"""

import sys

import psycopg2

DB_DSN = "postgresql://raguser:REDACTED_DB_PASSWORD@100.103.248.9:30433/vantage"


def get_conn():
    """Get a database connection to the vantage DB on fox-n1."""
    try:
        conn = psycopg2.connect(DB_DSN)
        conn.autocommit = True
        return conn
    except psycopg2.OperationalError as e:
        print(f"ERROR: Cannot connect to vantage DB (fox-n1:30433): {e}", file=sys.stderr)
        return None
```

### migrations/003_knowledge_graph.sql (NEW -- schema)
```sql
-- Phase 7: Knowledge Graph schema
-- Entity-relationship storage for GraphRAG retrieval.
-- PostgreSQL JSONB adjacency lists -- no Neo4j needed at this scale.

CREATE TABLE IF NOT EXISTS pm_entities (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    entity_type TEXT NOT NULL,  -- person|project|technology|concept|decision|event
    description TEXT,
    source_chunk_ids BIGINT[],  -- references puremind_chunks.id
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(name, entity_type)
);

CREATE TABLE IF NOT EXISTS pm_relationships (
    id BIGSERIAL PRIMARY KEY,
    source_id BIGINT NOT NULL REFERENCES pm_entities(id) ON DELETE CASCADE,
    target_id BIGINT NOT NULL REFERENCES pm_entities(id) ON DELETE CASCADE,
    rel_type TEXT NOT NULL,  -- mentions|depends_on|part_of|works_on|uses|decided|created_by
    weight FLOAT DEFAULT 1.0,
    evidence_chunk_ids BIGINT[],
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(source_id, target_id, rel_type)
);

CREATE TABLE IF NOT EXISTS pm_summaries (
    id BIGSERIAL PRIMARY KEY,
    scope TEXT NOT NULL,        -- file|project|period|vault
    scope_key TEXT NOT NULL,    -- file path, project name, date range, "vault"
    summary TEXT NOT NULL,
    embedding vector(768),
    source_chunk_ids BIGINT[],
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(scope, scope_key)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_pm_entities_name ON pm_entities(name);
CREATE INDEX IF NOT EXISTS idx_pm_entities_type ON pm_entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_pm_rel_source ON pm_relationships(source_id, rel_type);
CREATE INDEX IF NOT EXISTS idx_pm_rel_target ON pm_relationships(target_id, rel_type);
CREATE INDEX IF NOT EXISTS idx_pm_summaries_scope ON pm_summaries(scope, scope_key);
CREATE INDEX IF NOT EXISTS idx_pm_summaries_embedding ON pm_summaries USING hnsw (embedding vector_cosine_ops);
```

### .claude/hooks/daily_reflect.py (MODIFIED -- +15 lines, entity extraction hook)
Only the modified section (lines 566-582, added after the re-index step):
```python
    # Extract entities from today's log for the knowledge graph (Phase 7)
    entity_count = 0
    try:
        sys.path.insert(0, str(PUREMIND_ROOT))
        from tools.extract import extract_from_file
        from tools.db import get_conn
        import hashlib

        conn = get_conn()
        if conn and log_path.exists():
            fhash = hashlib.sha256(log_path.read_bytes()).hexdigest()
            e, r = extract_from_file(conn, log_path, fhash, verbose=False)
            entity_count = e
            conn.close()
    except Exception as ex:
        print(f"  Entity extraction skipped: {ex}", file=sys.stderr)
```
