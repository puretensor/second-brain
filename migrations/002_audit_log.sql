-- pureMind Phase 4: Integration Audit Log
-- Logs every integration call for observability and security review.
-- Same database as Phase 3 (vantage on fox-n1:30433).
--
-- Usage:
--   PGPASSWORD="<set-via-secrets-env>" psql -h 100.103.248.9 -p 30433 -U raguser -d vantage -f 002_audit_log.sql

CREATE TABLE IF NOT EXISTS pm_audit (
    id          bigserial PRIMARY KEY,
    ts          timestamptz NOT NULL DEFAULT now(),
    integration text NOT NULL,        -- 'gmail', 'github', 'calendar', 'telegram', 'cluster'
    function    text NOT NULL,        -- 'search', 'get', 'list', 'create_draft', 'comment', 'post_alert'
    parameters  jsonb DEFAULT '{}',   -- sanitised params (no tokens/secrets)
    result      text NOT NULL,        -- 'ok', 'error', 'denied'
    detail      text DEFAULT '',      -- error message or result summary
    latency_ms  int                   -- execution time in milliseconds
);

CREATE INDEX IF NOT EXISTS idx_pm_audit_ts ON pm_audit (ts DESC);
CREATE INDEX IF NOT EXISTS idx_pm_audit_integration ON pm_audit (integration, ts DESC);
