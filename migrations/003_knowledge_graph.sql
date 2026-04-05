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
