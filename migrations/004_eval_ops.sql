-- Phase 9: Evaluation & Ops Maturity schema
-- Golden QA pairs, eval run results, time-series metrics for Grafana.
-- Same database as Phases 3-8 (vantage on fox-n1:30433).
--
-- Usage:
--   psql -h 100.103.248.9 -p 30433 -U raguser -d vantage -f 004_eval_ops.sql

-- Golden QA pairs for retrieval evaluation
CREATE TABLE IF NOT EXISTS pm_eval_golden (
    id                  bigserial PRIMARY KEY,
    query               text NOT NULL,
    query_hash          text,
    answer              text NOT NULL,
    relevant_chunk_ids  bigint[],
    source              text DEFAULT 'manual',   -- manual | seeded | harvested
    tags                text[] DEFAULT '{}',
    created_at          timestamptz DEFAULT now(),
    active              boolean DEFAULT true
);

-- Backfill + dedupe for legacy installs where pm_eval_golden already exists.
ALTER TABLE pm_eval_golden ADD COLUMN IF NOT EXISTS query_hash text;
UPDATE pm_eval_golden
SET query_hash = md5(regexp_replace(lower(trim(query)), '\s+', ' ', 'g'))
WHERE query_hash IS NULL;
DELETE FROM pm_eval_golden a
USING pm_eval_golden b
WHERE a.id > b.id
  AND a.query_hash = b.query_hash;
CREATE UNIQUE INDEX IF NOT EXISTS idx_pm_eval_golden_query_hash
    ON pm_eval_golden (query_hash);

-- Weekly eval run results (one row per run)
CREATE TABLE IF NOT EXISTS pm_eval_runs (
    id                      bigserial PRIMARY KEY,
    ts                      timestamptz DEFAULT now(),
    recall_at_5             float,
    recall_at_10            float,
    mrr                     float,
    ndcg_at_5               float,
    faithfulness_score      float,
    personalisation_score   float,
    latency_p50_ms          int,
    latency_p95_ms          int,
    security_pass           boolean,
    security_tests_passed   int,
    security_tests_total    int,
    audit_completeness      float,
    cost_calls_7d           int,
    golden_count            int,
    detail                  jsonb DEFAULT '{}',
    summary                 text
);

CREATE INDEX IF NOT EXISTS idx_pm_eval_runs_ts ON pm_eval_runs (ts DESC);

-- Time-series metrics for Grafana (collected every 15 min)
CREATE TABLE IF NOT EXISTS pm_metrics (
    ts      timestamptz DEFAULT now(),
    metric  text NOT NULL,
    value   float NOT NULL,
    tags    jsonb DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_pm_metrics_ts ON pm_metrics (ts DESC);
CREATE INDEX IF NOT EXISTS idx_pm_metrics_metric ON pm_metrics (metric, ts DESC);

-- Retention is enforced by tools/metrics_collector.py on every write:
-- DELETE FROM pm_metrics WHERE ts < now() - interval '90 days';
