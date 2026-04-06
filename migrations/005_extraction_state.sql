-- Phase 7 addendum: Extraction state tracking for incremental entity extraction.
-- Tracks per-file hashes and entity/relationship IDs for change detection and cleanup.
-- Omitted from 003_knowledge_graph.sql, required by tools/extract.py.
--
-- Usage:
--   PGPASSWORD="<set-via-secrets-env>" psql -h 100.103.248.9 -p 30433 -U raguser -d vantage -f 005_extraction_state.sql

CREATE TABLE IF NOT EXISTS pm_extraction_state (
    file_path           text PRIMARY KEY,
    file_hash           text NOT NULL,
    entity_ids          bigint[],
    relationship_ids    bigint[],
    extracted_at        timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pm_extraction_state_hash
    ON pm_extraction_state (file_hash);
