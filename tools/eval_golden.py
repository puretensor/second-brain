#!/usr/bin/env python3
"""pureMind golden dataset builder for retrieval evaluation.

Builds and manages query-answer pairs with ground-truth chunk IDs
for computing Recall@k, MRR, and nDCG in the eval harness.

Usage:
    python3 eval_golden.py seed --count 50      # Generate QA pairs from vault
    python3 eval_golden.py --add "query" "answer"
    python3 eval_golden.py --harvest             # Extract from daily logs
    python3 eval_golden.py --list [--json]
    python3 eval_golden.py --stats
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

_PARENT = str(Path(__file__).resolve().parent.parent)
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

from tools.db import get_conn, get_write_conn

VAULT_ROOT = Path.home() / "pureMind"
KNOWLEDGE_DIR = VAULT_ROOT / "knowledge"


def _claude_generate(prompt: str, max_turns: int = 1) -> str | None:
    """Call Claude CLI and return raw text output."""
    try:
        result = subprocess.run(
            ["claude", "-p", "--max-turns", str(max_turns),
             "--output-format", "text"],
            input=prompt, capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def _get_chunk_ids_for_file(conn, file_path: str) -> list[int]:
    """Get all chunk IDs for a given file path."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM puremind_chunks WHERE file_path = %s ORDER BY chunk_index",
            (file_path,)
        )
        return [row[0] for row in cur.fetchall()]


def _find_relevant_chunks(conn, query: str, limit: int = 10) -> list[int]:
    """Find chunk IDs relevant to a query via hybrid search."""
    # Use BM25 search to find relevant chunks
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id FROM puremind_chunks
               WHERE content_tsv @@ plainto_tsquery('english', %s)
               ORDER BY ts_rank(content_tsv, plainto_tsquery('english', %s)) DESC
               LIMIT %s""",
            (query, query, limit)
        )
        return [row[0] for row in cur.fetchall()]


def seed_from_vault(count: int = 50, batch_size: int = 5) -> int:
    """Generate QA pairs from vault knowledge files using Claude CLI.

    For each file, asks Claude to generate natural questions that the
    file's content answers. Records the file's chunk IDs as relevant.
    """
    conn = get_write_conn()
    if conn is None:
        print("ERROR: Cannot connect to DB", file=sys.stderr)
        return 0

    # Gather knowledge files
    knowledge_files = []
    for ext in ("*.md", "*.txt"):
        knowledge_files.extend(KNOWLEDGE_DIR.rglob(ext))

    # Also include memory files and project READMEs
    for md in (VAULT_ROOT / "memory").glob("*.md"):
        knowledge_files.append(md)
    for md in (VAULT_ROOT / "projects").rglob("README.md"):
        knowledge_files.append(md)

    if not knowledge_files:
        print("No knowledge files found", file=sys.stderr)
        return 0

    generated = 0
    for filepath in knowledge_files:
        if generated >= count:
            break

        rel_path = str(filepath.relative_to(VAULT_ROOT))
        try:
            content = filepath.read_text(encoding="utf-8")[:5000]
        except Exception:
            continue

        if len(content.strip()) < 100:
            continue

        # Get chunk IDs for this file
        chunk_ids = _get_chunk_ids_for_file(conn, rel_path)
        if not chunk_ids:
            continue

        questions_needed = min(batch_size, count - generated)
        prompt = (
            f"Given this document content, generate exactly {questions_needed} "
            f"natural questions that this document answers. Return ONLY a JSON "
            f"array of objects with 'query' and 'answer' keys. The answer should "
            f"be a brief 1-2 sentence summary from the document.\n\n"
            f"Document ({rel_path}):\n{content}\n\n"
            f"Return JSON array only, no markdown fencing:"
        )

        response = _claude_generate(prompt)
        if not response:
            continue

        # Parse JSON response
        try:
            # Strip markdown fencing if present
            clean = response.strip()
            if clean.startswith("```"):
                clean = re.sub(r"^```\w*\n?", "", clean)
                clean = re.sub(r"\n?```$", "", clean)
            pairs = json.loads(clean)
        except (json.JSONDecodeError, ValueError):
            continue

        if not isinstance(pairs, list):
            continue

        for pair in pairs:
            if generated >= count:
                break
            query = pair.get("query", "").strip()
            answer = pair.get("answer", "").strip()
            if not query or not answer:
                continue

            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """INSERT INTO pm_eval_golden (query, answer, relevant_chunk_ids, source, tags)
                           VALUES (%s, %s, %s, 'seeded', %s)
                           ON CONFLICT DO NOTHING""",
                        (query, answer, chunk_ids, [rel_path])
                    )
                conn.commit()
                generated += 1
            except Exception as e:
                conn.rollback()
                print(f"WARNING: Insert failed: {e}", file=sys.stderr)

    conn.close()
    return generated


def harvest_from_logs(days: int = 30) -> int:
    """Extract QA pairs from daily logs by finding search patterns."""
    conn = get_write_conn()
    if conn is None:
        return 0

    log_dir = VAULT_ROOT / "daily-logs"
    harvested = 0

    for log_file in sorted(log_dir.glob("*.md"), reverse=True):
        content = log_file.read_text(encoding="utf-8")

        # Find search queries in logs (pattern: searched for "X", found Y)
        patterns = [
            re.compile(r'search.*?["\']([^"\']{5,80})["\']', re.IGNORECASE),
            re.compile(r'query.*?["\']([^"\']{5,80})["\']', re.IGNORECASE),
            re.compile(r'search\.py\s+"([^"]{5,80})"', re.IGNORECASE),
        ]

        for pattern in patterns:
            for match in pattern.finditer(content):
                query = match.group(1).strip()
                if not query or len(query) < 5:
                    continue

                # Find relevant chunks via BM25
                chunk_ids = _find_relevant_chunks(conn, query)
                if not chunk_ids:
                    continue

                # Get a snippet from the top chunk as the answer
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT content FROM puremind_chunks WHERE id = %s",
                        (chunk_ids[0],)
                    )
                    row = cur.fetchone()
                    if not row:
                        continue
                    answer = row[0][:200]

                try:
                    with conn.cursor() as cur:
                        cur.execute(
                            """INSERT INTO pm_eval_golden (query, answer, relevant_chunk_ids, source, tags)
                               VALUES (%s, %s, %s, 'harvested', %s)
                               ON CONFLICT DO NOTHING""",
                            (query, answer, chunk_ids[:5],
                             [str(log_file.relative_to(VAULT_ROOT))])
                        )
                    conn.commit()
                    harvested += 1
                except Exception:
                    conn.rollback()

    conn.close()
    return harvested


def add_manual(query: str, answer: str, chunk_ids: list[int] = None):
    """Add a manually curated QA pair."""
    conn = get_write_conn()
    if conn is None:
        print("ERROR: Cannot connect to DB", file=sys.stderr)
        return

    if chunk_ids is None:
        chunk_ids = _find_relevant_chunks(conn, query)

    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO pm_eval_golden (query, answer, relevant_chunk_ids, source)
                   VALUES (%s, %s, %s, 'manual')""",
                (query, answer, chunk_ids)
            )
        conn.commit()
        print(f"Added: {query[:60]}... ({len(chunk_ids)} chunks)")
    except Exception as e:
        conn.rollback()
        print(f"ERROR: {e}", file=sys.stderr)
    finally:
        conn.close()


def list_golden(as_json: bool = False) -> list[dict]:
    """List all active golden QA pairs."""
    conn = get_conn()
    if conn is None:
        return []

    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, query, answer, relevant_chunk_ids, source, tags, created_at
               FROM pm_eval_golden WHERE active = true ORDER BY id"""
        )
        rows = cur.fetchall()

    conn.close()
    results = []
    for row in rows:
        entry = {
            "id": row[0], "query": row[1], "answer": row[2],
            "chunk_ids": row[3] or [], "source": row[4],
            "tags": row[5] or [], "created_at": str(row[6]),
        }
        results.append(entry)

    if as_json:
        print(json.dumps(results, indent=2))
    else:
        for r in results:
            print(f"  [{r['id']}] ({r['source']}) {r['query'][:70]}")
        print(f"\nTotal: {len(results)} active pairs")

    return results


def get_stats():
    """Print golden dataset statistics."""
    conn = get_conn()
    if conn is None:
        return

    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM pm_eval_golden WHERE active = true")
        total = cur.fetchone()[0]
        cur.execute(
            "SELECT source, count(*) FROM pm_eval_golden WHERE active = true GROUP BY source"
        )
        by_source = dict(cur.fetchall())
        cur.execute(
            """SELECT count(*) FROM pm_eval_golden
               WHERE active = true AND relevant_chunk_ids IS NOT NULL
               AND array_length(relevant_chunk_ids, 1) > 0"""
        )
        with_chunks = cur.fetchone()[0]

    conn.close()
    print(f"Golden dataset: {total} active pairs")
    for src, cnt in by_source.items():
        print(f"  {src}: {cnt}")
    print(f"  With ground-truth chunks: {with_chunks}")


def main():
    parser = argparse.ArgumentParser(description="pureMind golden dataset builder")
    parser.add_argument("command", nargs="?", choices=["seed", "harvest", "stats"],
                        help="Command to run")
    parser.add_argument("--add", nargs=2, metavar=("QUERY", "ANSWER"),
                        help="Add a manual QA pair")
    parser.add_argument("--list", action="store_true", help="List all golden pairs")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--count", type=int, default=50,
                        help="Number of pairs to generate (seed)")
    parser.add_argument("--days", type=int, default=30,
                        help="Days to scan (harvest)")

    args = parser.parse_args()

    if args.add:
        add_manual(args.add[0], args.add[1])
    elif args.list:
        list_golden(as_json=args.json)
    elif args.command == "seed":
        n = seed_from_vault(count=args.count)
        print(f"Seeded {n} QA pairs from vault content")
    elif args.command == "harvest":
        n = harvest_from_logs(days=args.days)
        print(f"Harvested {n} QA pairs from daily logs")
    elif args.command == "stats":
        get_stats()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
