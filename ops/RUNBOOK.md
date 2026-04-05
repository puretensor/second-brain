# pureMind Operations Runbook

## Service Map

| Component | Host | Schedule | Timer |
|---|---|---|---|
| Heartbeat agent | TC (systemd) | Every 30 min (07:00-23:00 UTC) | `puremind-heartbeat.timer` |
| Daily reflection | TC (systemd) | 23:00 UTC daily | `puremind-reflect.timer` |
| Eval harness | TC (systemd) | Saturday 04:00 UTC | `puremind-eval.timer` |
| Metrics collector | TC (systemd) | Every 15 min | `puremind-metrics.timer` |
| PostgreSQL (vantage) | fox-n1:30433 | Always-on | K3s pod |
| Grafana | fox-n1:30302 | Always-on | K3s pod |
| Telegram alerts | @puretensor_alert_bot | On threshold breach | N/A |

### Credentials

| Service | Location |
|---|---|
| DB DSN | `$PUREMIND_DB_DSN` or `~/.config/puremind/secrets.env` |
| Telegram token | `$PUREMIND_TELEGRAM_TOKEN` or `~/.config/puremind/secrets.env` |
| Grafana admin | `admin` / `consort-crazy-curl` (K3s NodePort 30302) |

### Key Paths

| Path | Purpose |
|---|---|
| `~/pureMind/` | Vault root (Git-backed) |
| `~/pureMind/tools/` | Core tools (search, index, extract, eval, metrics) |
| `~/pureMind/daily-logs/` | Session logs, heartbeat/reflection JSONL |
| `~/.config/puremind/secrets.env` | Credentials (0600, outside vault) |
| `~/.cache/puremind/audit_fallback.jsonl` | Audit JSONL fallback |

---

## Daily Operations

**Automatic (no action required):**
- Heartbeat runs every 30 min, posts Telegram summary
- Metrics collected every 15 min, stored in pm_metrics
- Daily reflection at 23:00 UTC promotes knowledge

**Check (if desired):**
```bash
# Latest heartbeat result
tail -1 ~/pureMind/daily-logs/heartbeat-log.jsonl | python3 -m json.tool

# Today's metrics
python3 ~/pureMind/tools/metrics_collector.py --json

# Timer status
systemctl --user list-timers | grep puremind
```

---

## Weekly Operations

### Eval Review (after Saturday 04:00 UTC run)

```bash
# Latest eval results
PGPASSWORD='REDACTED_DB_PASSWORD' psql -h 100.103.248.9 -p 30433 -U raguser -d vantage \
  -c "SELECT ts, recall_at_5, mrr, ndcg_at_5, faithfulness_score, security_pass, cost_calls_7d FROM pm_eval_runs ORDER BY ts DESC LIMIT 5"

# Or run manually
python3 ~/pureMind/tools/eval_harness.py --json
```

**Healthy baselines (initial):**
- Recall@5: 0.33 (expected to improve with more golden pairs)
- MRR: 0.80 (strong -- most relevant results appear first)
- nDCG@5: 0.46
- Security: all 30 tests passing
- Latency P50: <500ms, P95: <2000ms

### Audit Log Review

```bash
# Errors in last 7 days
PGPASSWORD='REDACTED_DB_PASSWORD' psql -h 100.103.248.9 -p 30433 -U raguser -d vantage \
  -c "SELECT ts, integration, function, detail FROM pm_audit WHERE result='error' AND ts > now() - interval '7 days' ORDER BY ts DESC LIMIT 20"

# Check fallback file
wc -l ~/.cache/puremind/audit_fallback.jsonl 2>/dev/null || echo "No fallback entries"
```

---

## Quarterly Operations

### Credential Rotation
1. Generate new DB password
2. Update PostgreSQL: `ALTER USER raguser WITH PASSWORD 'new-password';`
3. Update `~/.config/puremind/secrets.env`
4. Restart timers: `systemctl --user restart puremind-heartbeat puremind-reflect puremind-eval puremind-metrics`
5. Verify: `python3 ~/pureMind/tools/search.py "test" --limit 1`

### Dependency Update
```bash
cd ~/pureMind
pip3 install --upgrade -r requirements.txt
pip3 freeze | grep -E "psycopg2|sentence-transform|pdfplumber|scikit-learn" > /tmp/versions.txt
# Update requirements.txt with new versions
python3 -m pytest tests/ -v  # Verify nothing broke
```

### Embedding Model Evaluation
1. Check MTEB leaderboard for nomic-embed-text updates
2. If new model available: test on golden dataset, compare nDCG/MRR
3. Update `tools/embed.py` MODEL_NAME and MODEL_REVISION
4. Full re-index: `python3 tools/index.py --full`

---

## Troubleshooting

### Heartbeat Not Firing
```bash
# Check timer
systemctl --user status puremind-heartbeat.timer
systemctl --user status puremind-heartbeat.service

# Check waking hours (07:00-23:00 UTC)
date -u

# Manual test
python3 ~/pureMind/tools/heartbeat.py --dry-run

# Check DB connectivity
python3 -c "from tools.db import get_conn; c = get_conn(); print('OK' if c else 'FAIL')"
```

### Retrieval Degradation (Recall/MRR drop)
```bash
# Check index freshness
python3 -c "
from tools.db import get_conn
c = get_conn()
cur = c.cursor()
cur.execute('SELECT count(*), max(updated_at) FROM puremind_chunks')
print(cur.fetchone())
"

# Re-index
python3 ~/pureMind/tools/index.py --full

# Check embedding model loads
python3 ~/pureMind/tools/embed.py "test query"

# Expand golden dataset
python3 ~/pureMind/tools/eval_golden.py seed --count 20
```

### Audit Errors
```bash
# Check DB connectivity
python3 -c "from tools.db import get_conn; print(get_conn())"

# Review recent errors
PGPASSWORD='REDACTED_DB_PASSWORD' psql -h 100.103.248.9 -p 30433 -U raguser -d vantage \
  -c "SELECT ts, integration, function, detail FROM pm_audit WHERE result='error' ORDER BY ts DESC LIMIT 10"

# Check fallback file
cat ~/.cache/puremind/audit_fallback.jsonl | python3 -m json.tool | head -50
```

### High Latency (P95 > 5s)
```bash
# Check DB connections
PGPASSWORD='REDACTED_DB_PASSWORD' psql -h 100.103.248.9 -p 30433 -U raguser -d vantage \
  -c "SELECT count(*) FROM pg_stat_activity WHERE datname='vantage'"

# Check slow queries
PGPASSWORD='REDACTED_DB_PASSWORD' psql -h 100.103.248.9 -p 30433 -U raguser -d vantage \
  -c "SELECT function, avg(latency_ms), max(latency_ms) FROM pm_audit WHERE ts > now() - interval '1 hour' GROUP BY function ORDER BY avg DESC"

# VACUUM/ANALYZE
PGPASSWORD='REDACTED_DB_PASSWORD' psql -h 100.103.248.9 -p 30433 -U raguser -d vantage \
  -c "VACUUM ANALYZE puremind_chunks; VACUUM ANALYZE pm_entities;"
```

### Security Test Failure
```bash
# Run tests verbosely
python3 -m pytest tests/test_sanitize.py -v --tb=long

# Check what changed
cd ~/pureMind && git diff tools/sanitize.py

# Check payload coverage
python3 -c "import json; d=json.load(open('tests/payloads.json')); print({k: len(v) for k,v in d.items()})"
```

### Grafana Dashboard Not Loading
```bash
# Check Grafana is running
curl -s -u admin:consort-crazy-curl http://100.103.248.9:30302/api/health

# Re-deploy dashboard
bash ~/pureMind/ops/deploy_dashboard.sh

# Check PostgreSQL datasource
curl -s -u admin:consort-crazy-curl http://100.103.248.9:30302/api/datasources | python3 -m json.tool
```

---

## Alerting Matrix

| Metric | Threshold | Channel | Escalation |
|---|---|---|---|
| `chunk_count` | < 50 | Telegram | Index likely broken; re-index |
| `audit_errors_1h` | > 5 | Telegram | Check DB, review errors |
| `search_latency_p95` | > 10,000ms | Telegram | Check DB, VACUUM ANALYZE |
| `heartbeat_ok_24h` | < 1 | Telegram | Check timer, check waking hours |
| `embedding_freshness_hours` | > 48 | Telegram | Check indexer, re-index |
| `summary_freshness_hours` | > 168 | Telegram | Run summarize.py --build-all |
| `fallback_lines` | > 0 | Telegram | DB was unavailable; check connectivity |

Alert deduplication: 1 hour per metric. State in `$XDG_RUNTIME_DIR/puremind_alert_dedup.json`.

---

## Recovery Procedures

### Vault Recovery (from Git)
```bash
cd ~/pureMind
git log --oneline -20  # Find good state
git stash               # Save current changes
git checkout <commit>   # Restore
```

### Database Recovery
```bash
# PostgreSQL is on K3s with Ceph-backed PVCs
# Check pod status
kubectl get pods -n default | grep postgres

# If data loss: restore from Ceph snapshot
# Then re-index and re-extract
python3 ~/pureMind/tools/index.py --full
python3 ~/pureMind/tools/extract.py --full
```

### Full Re-Index
```bash
python3 ~/pureMind/tools/index.py --full    # Chunks + embeddings
python3 ~/pureMind/tools/extract.py --full  # Entity extraction
python3 ~/pureMind/tools/summarize.py --build-all  # Hierarchical summaries
```
