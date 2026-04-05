#!/usr/bin/env python3
"""pureMind vault indexer -- chunk, embed, and store in pgvector.

Indexes markdown files from the pureMind vault into the puremind_chunks
table in the vantage database. Supports full re-index and incremental
mode (SHA-256 change detection).

Usage:
    python3 index.py                    # Incremental (changed files only)
    python3 index.py --full             # Full re-index (all files)
    python3 index.py --full --verbose   # Full with per-file output
    python3 index.py --quiet            # Suppress output (for hooks)
"""

import hashlib
import sys
import time
from pathlib import Path

import psycopg2

# Add tools dir to path for local imports
TOOLS_DIR = Path(__file__).parent
sys.path.insert(0, str(TOOLS_DIR))

from chunker import chunk_markdown
from embed import embed_documents, embedding_to_pgvector

# Database connection
DB_DSN = "postgresql://raguser:REDACTED_DB_PASSWORD@100.103.248.9:30433/vantage"

# Vault root
VAULT_ROOT = Path.home() / "pureMind"

# Files to index (relative glob patterns)
INDEX_PATTERNS = [
    "knowledge/**/*.md",
    "projects/**/*.md",
    "daily-logs/*.md",
    "templates/*.md",
    "memory/memory.md",
    "memory/pending.md",
    "CLAUDE.md",
    "README.md",
]

# Files to exclude from indexing (loaded at session start, don't need RAG)
EXCLUDE_FILES = {
    "memory/soul.md",
    "memory/user.md",
}


def collect_files() -> list[Path]:
    """Collect all indexable markdown files from the vault."""
    files = set()
    for pattern in INDEX_PATTERNS:
        for path in VAULT_ROOT.glob(pattern):
            rel = path.relative_to(VAULT_ROOT)
            if str(rel) not in EXCLUDE_FILES and path.is_file():
                files.add(path)
    return sorted(files)


def file_hash(path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def get_stored_hashes(conn) -> dict[str, str]:
    """Get file_path -> file_hash mapping from the database."""
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT file_path, file_hash FROM puremind_chunks")
        return {row[0]: row[1] for row in cur.fetchall()}


def delete_file_chunks(conn, file_path: str):
    """Delete all chunks for a given file."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM puremind_chunks WHERE file_path = %s", (file_path,))


def insert_chunks(conn, file_path: str, chunks: list[dict], embeddings: list[list[float]], fhash: str):
    """Insert chunks with embeddings into the database."""
    with conn.cursor() as cur:
        for chunk, embedding in zip(chunks, embeddings):
            vec_str = embedding_to_pgvector(embedding)
            cur.execute(
                """
                INSERT INTO puremind_chunks (file_path, heading_path, chunk_index, content, embedding, file_hash)
                VALUES (%s, %s, %s, %s, %s::vector, %s)
                ON CONFLICT (file_path, chunk_index) DO UPDATE SET
                    heading_path = EXCLUDED.heading_path,
                    content = EXCLUDED.content,
                    embedding = EXCLUDED.embedding,
                    file_hash = EXCLUDED.file_hash,
                    updated_at = now()
                """,
                (file_path, chunk["heading_path"], chunk["chunk_index"],
                 chunk["content"], vec_str, fhash),
            )


def main():
    full_mode = "--full" in sys.argv
    verbose = "--verbose" in sys.argv
    quiet = "--quiet" in sys.argv

    start = time.time()
    files = collect_files()

    if verbose:
        print(f"Found {len(files)} indexable files in vault")

    conn = psycopg2.connect(DB_DSN)
    conn.autocommit = False

    try:
        stored_hashes = get_stored_hashes(conn)
        stored_files = set(stored_hashes.keys())

        indexed = 0
        skipped = 0
        deleted = 0
        total_chunks = 0

        for path in files:
            rel_path = str(path.relative_to(VAULT_ROOT))
            fhash = file_hash(path)

            # Incremental: skip unchanged files
            if not full_mode and rel_path in stored_hashes and stored_hashes[rel_path] == fhash:
                skipped += 1
                continue

            # Read and chunk
            content = path.read_text(encoding="utf-8")
            chunks = chunk_markdown(content, rel_path)

            if not chunks:
                if verbose:
                    print(f"  SKIP (empty): {rel_path}")
                continue

            # Embed all chunks in batch
            texts = [c["content"] for c in chunks]
            embeddings = embed_documents(texts)

            # Delete old chunks for this file, insert new
            delete_file_chunks(conn, rel_path)
            insert_chunks(conn, rel_path, chunks, embeddings, fhash)
            conn.commit()

            indexed += 1
            total_chunks += len(chunks)
            if verbose:
                print(f"  INDEX: {rel_path} -> {len(chunks)} chunks")

        # Clean up chunks for files that no longer exist
        current_files = {str(p.relative_to(VAULT_ROOT)) for p in files}
        orphan_files = stored_files - current_files
        for orphan in orphan_files:
            delete_file_chunks(conn, orphan)
            conn.commit()
            deleted += 1
            if verbose:
                print(f"  DELETE: {orphan} (file removed)")

        elapsed = time.time() - start

        if not quiet:
            print(f"Index complete: {indexed} indexed, {skipped} unchanged, {deleted} removed, {total_chunks} chunks total ({elapsed:.1f}s)")

    except Exception as e:
        conn.rollback()
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
