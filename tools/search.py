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
import sys
from pathlib import Path

import psycopg2

# Add tools dir to path for local imports
TOOLS_DIR = Path(__file__).parent
sys.path.insert(0, str(TOOLS_DIR))

from embed import embed_query, embedding_to_pgvector

DB_DSN = "postgresql://raguser:REDACTED_DB_PASSWORD@100.103.248.9:30433/vantage"
RRF_K = 60  # RRF constant (matches Nexus)


def search(query: str, limit: int = 5, file_filter: str | None = None) -> list[dict]:
    """Hybrid search: BM25 + vector similarity fused via RRF."""
    overfetch = limit * 3
    try:
        conn = psycopg2.connect(DB_DSN)
    except psycopg2.OperationalError as e:
        print(f"ERROR: Cannot connect to database (fox-n1:30433/vantage): {e}", file=sys.stderr)
        return []

    try:
        # Build optional WHERE clause for file filter
        where_extra = ""
        params_extra = []
        if file_filter:
            where_extra = " AND file_path LIKE %s"
            params_extra = [f"{file_filter}%"]

        # 1. BM25 search via tsvector
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


def format_results(results: list[dict]) -> str:
    """Format results as readable markdown."""
    if not results:
        return "No results found."

    lines = []
    for i, r in enumerate(results, 1):
        sources = "+".join(r["sources"])
        lines.append(f"### {i}. {r['file_path']}")
        if r["heading_path"]:
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
        print("Usage: search.py <query> [--limit N] [--json] [--file-filter prefix]", file=sys.stderr)
        sys.exit(1)

    query = args[0]
    limit = 5
    json_output = False
    file_filter = None

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
        else:
            i += 1

    results = search(query, limit=limit, file_filter=file_filter)

    if json_output:
        print(json.dumps(results, indent=2))
    else:
        print(format_results(results))


if __name__ == "__main__":
    main()
