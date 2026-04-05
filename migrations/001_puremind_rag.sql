-- pureMind Phase 3: Hybrid RAG Schema
-- Creates puremind_chunks table in the existing vantage database.
-- Uses pgvector for dense vectors and native tsvector for BM25 search.
-- Hybrid retrieval via Reciprocal Rank Fusion (matches Nexus + Alexandria pattern).
--
-- Prerequisites: vantage database with pgvector extension (already loaded).
--
-- Usage:
--   PGPASSWORD="REDACTED_DB_PASSWORD" psql -h 100.103.248.9 -p 30433 -U raguser -d vantage -f 001_puremind_rag.sql

CREATE TABLE IF NOT EXISTS puremind_chunks (
    id              bigserial PRIMARY KEY,
    file_path       text NOT NULL,              -- relative to ~/pureMind/ (e.g., "knowledge/puretensor/lessons.md")
    heading_path    text NOT NULL DEFAULT '',    -- breadcrumb: "## Section > ### Subsection"
    chunk_index     smallint NOT NULL DEFAULT 0,
    content         text NOT NULL,
    embedding       vector(768),                -- nomic-embed-text-v1.5

    -- Full-text search (generated column for BM25)
    content_tsv     tsvector GENERATED ALWAYS AS (
        to_tsvector('english', coalesce(content, ''))
    ) STORED,

    -- Change detection
    file_hash       text NOT NULL,              -- SHA-256 of source file at index time

    -- Timestamps
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),

    -- One chunk per (file, index) -- enables clean incremental updates
    UNIQUE (file_path, chunk_index)
);

-- HNSW index for vector similarity search (cosine distance)
CREATE INDEX IF NOT EXISTS idx_pm_chunks_embedding
    ON puremind_chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 200);

-- GIN index for full-text search
CREATE INDEX IF NOT EXISTS idx_pm_chunks_tsv
    ON puremind_chunks USING gin (content_tsv);

-- File path lookup (for incremental re-indexing)
CREATE INDEX IF NOT EXISTS idx_pm_chunks_file
    ON puremind_chunks (file_path);

-- File hash lookup (for change detection)
CREATE INDEX IF NOT EXISTS idx_pm_chunks_hash
    ON puremind_chunks (file_hash);
