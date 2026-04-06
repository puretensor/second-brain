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

from tools.db import get_conn, get_write_conn
from tools.embed import embed_query, embedding_to_pgvector
RRF_K = 60  # RRF constant (matches Nexus)
WIKI_BOOST = 1.15  # knowledge/ results boosted 15% (wiki-first, CLAUDE.md rule 4)

# F-01: whitelist of allowed PostgreSQL FTS configs -- no f-string interpolation
ALLOWED_FTS_LANGS = {"english", "simple", "spanish", "danish", "german", "french", "italian", "portuguese"}


def search(query: str, limit: int = 5, file_filter: str | None = None,
           lang: str = "english", wiki_boost: bool = True,
           include_sources: bool = False) -> list[dict]:
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
        # F-01: whitelist lang to prevent SQL injection -- no f-string interpolation
        if lang not in ALLOWED_FTS_LANGS:
            lang = "english"
        if lang == "simple":
            tsquery_expr = "plainto_tsquery('simple', unaccent(%s))"
        else:
            # Safe: lang is validated against ALLOWED_FTS_LANGS whitelist above
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

        # E-01: Also search pm_summaries for abstraction-level matches
        summary_rows = []
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, scope_key, scope, summary,
                       1 - (embedding <=> %s::vector) AS score
                FROM pm_summaries
                WHERE embedding IS NOT NULL
                ORDER BY embedding <=> %s::vector
                LIMIT %s
            """, (vec_str, vec_str, limit))
            for r in cur.fetchall():
                if float(r[4]) > 0.3:  # only include reasonably relevant summaries
                    summary_rows.append({
                        "id": -r[0],  # negative ID to distinguish from chunks
                        "file_path": r[1],  # scope_key as file_path
                        "heading_path": f"[{r[2]} summary]",
                        "content": r[3],
                        "score": float(r[4]),
                    })

        # 3. RRF fusion on overfetched candidates (truncation in _post_process)
        if summary_rows:
            results = _rrf_fuse_3way(bm25_rows, sem_rows, summary_rows, overfetch)
        else:
            results = _rrf_fuse(bm25_rows, sem_rows, overfetch)
        return _post_process(results, limit, wiki_boost, include_sources)

    finally:
        conn.close()


def _rrf_fuse(bm25_results: list[dict], sem_results: list[dict], limit: int) -> list[dict]:
    """Fuse BM25 and semantic results via Reciprocal Rank Fusion."""
    scores: dict[int, float] = {}
    items: dict[int, dict] = {}

    for rank, item in enumerate(bm25_results, start=1):
        fid = item["id"]
        scores[fid] = scores.get(fid, 0) + 1.0 / (RRF_K + rank)
        if fid not in items:
            item["sources"] = ["bm25"]
            items[fid] = item
        else:
            items[fid]["sources"].append("bm25")

    for rank, item in enumerate(sem_results, start=1):
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


# Meta pages excluded from wiki boost (navigation/changelog, not content)
_WIKI_BOOST_EXCLUDE = {"knowledge/index.md", "knowledge/log.md"}


def _apply_wiki_boost(results: list[dict]) -> list[dict]:
    """Boost knowledge/ content pages to implement wiki-first ranking (CLAUDE.md rule 4)."""
    for r in results:
        fp = r["file_path"]
        if fp.startswith("knowledge/") and fp not in _WIKI_BOOST_EXCLUDE:
            r["rrf_score"] *= WIKI_BOOST
    results.sort(key=lambda r: r["rrf_score"], reverse=True)
    return results


def _post_process(results: list[dict], limit: int,
                  wiki_boost: bool, include_sources: bool) -> list[dict]:
    """Apply wiki boost, filter sources, and truncate to final limit."""
    if wiki_boost:
        results = _apply_wiki_boost(results)
    if not include_sources:
        results = [r for r in results if not r["file_path"].startswith("sources/")]
    return results[:limit]


def extract_query_entities(conn, query: str) -> list[int]:
    """Find entity IDs whose names appear in the query text.

    C-02: Uses trigram similarity (gin_trgm_ops index) for indexed matching.
    Falls back to substring match for short names that trigram misses.
    """
    with conn.cursor() as cur:
        # Trigram similarity match (uses gin index)
        cur.execute("""
            SELECT id, name, similarity(lower(name), lower(%s)) AS sim
            FROM pm_entities
            WHERE lower(name) %% lower(%s) OR lower(%s) LIKE '%%' || lower(name) || '%%'
            ORDER BY sim DESC, length(name) DESC
            LIMIT 20
        """, (query, query, query))
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


def _rrf_fuse_3way(bm25_results: list[dict], sem_results: list[dict],
                   graph_results: list[dict], limit: int) -> list[dict]:
    """C-01: True 3-way RRF fusion keeping BM25, semantic, and graph as independent signals."""
    scores: dict[int, float] = {}
    items: dict[int, dict] = {}

    for rank, item in enumerate(bm25_results, start=1):
        fid = item["id"]
        scores[fid] = scores.get(fid, 0) + 1.0 / (RRF_K + rank)
        if fid not in items:
            item["sources"] = ["bm25"]
            items[fid] = item
        else:
            items[fid]["sources"].append("bm25")

    for rank, item in enumerate(sem_results, start=1):
        fid = item["id"]
        scores[fid] = scores.get(fid, 0) + 1.0 / (RRF_K + rank)
        if fid not in items:
            item["sources"] = ["semantic"]
            items[fid] = item
        else:
            items[fid]["sources"].append("semantic")

    for rank, item in enumerate(graph_results, start=1):
        fid = item["id"]
        scores[fid] = scores.get(fid, 0) + 1.0 / (RRF_K + rank)
        if fid not in items:
            item["sources"] = ["graph"]
            items[fid] = item
        else:
            if "graph" not in items[fid]["sources"]:
                items[fid]["sources"].append("graph")

    ranked = sorted(scores.items(), key=lambda x: -x[1])
    results = []
    for fid, rrf_score in ranked[:limit]:
        item = items[fid]
        results.append({
            "id": item["id"],
            "file_path": item["file_path"],
            "heading_path": item.get("heading_path", ""),
            "content": item["content"],
            "rrf_score": round(rrf_score, 6),
            "sources": item["sources"],
        })

    return results


def graph_search(query: str, limit: int = 5, file_filter: str | None = None,
                 lang: str = "english", wiki_boost: bool = True,
                 include_sources: bool = False) -> list[dict]:
    """C-01: Graph-augmented search with true 3-way RRF fusion.

    Runs BM25, semantic, and graph retrieval as independent signals,
    then fuses all three via RRF. C-03: respects --lang parameter.
    """
    conn = get_conn()
    if conn is None:
        return search(query, limit=limit, file_filter=file_filter, lang=lang,
                      wiki_boost=wiki_boost, include_sources=include_sources)

    overfetch = limit * 3

    try:
        # Find entities mentioned in the query
        entity_ids = extract_query_entities(conn, query)
        graph_entities = []
        graph_rows = []

        if entity_ids:
            graph_entities = traverse_graph(conn, entity_ids, max_depth=2)

            # Collect chunk IDs from graph traversal
            chunk_ids = set()
            for entity in graph_entities:
                for cid in entity["source_chunk_ids"]:
                    chunk_ids.add(cid)

            # Retrieve graph-sourced chunks
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
                            "score": 1.0 / (1 + rank),
                        })

        # C-01: Run BM25 and semantic independently (not via search() which pre-fuses them)
        where_extra = ""
        params_extra = []
        if file_filter:
            where_extra = " AND file_path LIKE %s"
            params_extra = [f"{file_filter}%"]

        # C-03: respect --lang
        if lang not in ALLOWED_FTS_LANGS:
            lang = "english"
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

    finally:
        conn.close()

    # C-01: true 3-way fusion on overfetched candidates
    results = _rrf_fuse_3way(bm25_rows, sem_rows, graph_rows, overfetch)

    # Attach graph context
    if graph_entities:
        entity_names = [e["name"] for e in graph_entities[:10]]
        for r in results:
            r["graph_entities"] = entity_names

    return _post_process(results, limit, wiki_boost, include_sources)


def hyde_search(query: str, limit: int = 5, file_filter: str | None = None,
                lang: str = "english", wiki_boost: bool = True,
                include_sources: bool = False) -> list[dict]:
    """HyDE search: generate hypothetical answer, embed it, search with that embedding.

    D-02: Respects --lang parameter for BM25 component.
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
        return search(query, limit=limit, file_filter=file_filter, lang=lang,
                      wiki_boost=wiki_boost, include_sources=include_sources)

    hyde_vec = embed_query(hypothetical_doc)
    vec_str = embedding_to_pgvector(hyde_vec)

    conn = get_conn()
    if conn is None:
        return search(query, limit=limit, file_filter=file_filter, lang=lang,
                      wiki_boost=wiki_boost, include_sources=include_sources)

    overfetch = limit * 3
    try:
        where_extra = ""
        params_extra = []
        if file_filter:
            where_extra = " AND file_path LIKE %s"
            params_extra = [f"{file_filter}%"]

        # D-02: respect --lang for BM25 component
        if lang not in ALLOWED_FTS_LANGS:
            lang = "english"
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

        results = _rrf_fuse(bm25_rows, hyde_rows, overfetch)
        return _post_process(results, limit, wiki_boost, include_sources)

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
        print("Usage: search.py <query> [--limit N] [--json] [--file-filter prefix] [--graph] [--hyde] [--no-wiki-boost] [--include-sources]", file=sys.stderr)
        sys.exit(1)

    query = args[0]
    limit = 5
    json_output = False
    file_filter = None
    use_graph = False
    use_hyde = False
    wiki_boost = True
    include_sources = False
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
        elif args[i] == "--no-wiki-boost":
            wiki_boost = False
            i += 1
        elif args[i] == "--include-sources":
            include_sources = True
            i += 1
        elif args[i] == "--lang" and i + 1 < len(args):
            lang = args[i + 1]
            i += 2
        else:
            i += 1

    if use_graph:
        results = graph_search(query, limit=limit, file_filter=file_filter, lang=lang,
                               wiki_boost=wiki_boost, include_sources=include_sources)
    elif use_hyde:
        results = hyde_search(query, limit=limit, file_filter=file_filter, lang=lang,
                              wiki_boost=wiki_boost, include_sources=include_sources)
    else:
        results = search(query, limit=limit, file_filter=file_filter, lang=lang,
                         wiki_boost=wiki_boost, include_sources=include_sources)

    if json_output:
        print(json.dumps(results, indent=2))
    else:
        print(format_results(results))


if __name__ == "__main__":
    main()
