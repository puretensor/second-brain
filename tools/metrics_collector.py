#!/usr/bin/env python3
"""pureMind metrics collector -- lightweight 15-minute health check.

Collects system metrics from PostgreSQL and writes to pm_metrics for
Grafana dashboards. Alerts via Telegram when thresholds are breached.

No Claude CLI required -- pure SQL queries.

Usage:
    python3 metrics_collector.py            # Collect and store
    python3 metrics_collector.py --dry-run  # Print without storing
    python3 metrics_collector.py --json     # JSON output
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

_PARENT = str(Path(__file__).resolve().parent.parent)
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

from tools.db import get_conn, get_write_conn

VAULT_ROOT = Path.home() / "pureMind"
AUDIT_FALLBACK = Path.home() / ".cache" / "puremind" / "audit_fallback.jsonl"
HEARTBEAT_LOG = VAULT_ROOT / "daily-logs" / "heartbeat-log.jsonl"
SEARCH_BENCHMARK_QUERIES = ("pgvector", "PureTensor", "heartbeat")

# Alert deduplication: don't re-alert on the same metric within this window
def _state_root() -> Path:
    """Per-machine state root for pureMind ops files."""
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if runtime_dir:
        return Path(runtime_dir) / "puremind"
    return Path.home() / ".cache" / "puremind"


ALERT_DEDUP_FILE = _state_root() / "alert_dedup.json"
ALERT_DEDUP_SECONDS = 3600  # 1 hour

# Thresholds: metric_name -> (operator, value, description)
THRESHOLDS = {
    "chunk_count": ("lt", 50, "Index appears broken (fewer than 50 chunks)"),
    "audit_errors_1h": ("gt", 5, "More than 5 audit errors in the last hour"),
    "search_latency_p95": ("gt", 10000, "Search P95 latency exceeds 10s"),
    "heartbeat_ok_24h": ("lt", 1, "No successful heartbeat in 24 hours"),
    "embedding_freshness_hours": ("gt", 48, "Embeddings not updated in 48 hours"),
    "summary_freshness_hours": ("gt", 168, "Summaries not updated in 7 days"),
    "fallback_lines": ("gt", 0, "Audit fallback has entries (DB was unavailable)"),
}


def _collect_metric(conn, name: str, query: str) -> float | None:
    """Execute a single metric query, return float or None."""
    try:
        with conn.cursor() as cur:
            cur.execute(query)
            row = cur.fetchone()
            if row and row[0] is not None:
                return float(row[0])
    except Exception as e:
        print(f"WARNING: Metric '{name}' failed: {e}", file=sys.stderr)
    return None


def _percentile(values: list[float], percentile: float) -> float | None:
    """Simple percentile helper without an extra dependency."""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    idx = (len(ordered) - 1) * percentile
    low = int(idx)
    high = min(low + 1, len(ordered) - 1)
    frac = idx - low
    return ordered[low] + (ordered[high] - ordered[low]) * frac


def _count_recent_heartbeat_entries(log_path: Path = HEARTBEAT_LOG,
                                    hours: int = 24) -> float:
    """Count non-dry-run heartbeat runs in the recent JSONL log window."""
    if not log_path.exists():
        return 0.0
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    count = 0
    try:
        with log_path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    ts = datetime.fromisoformat(entry["timestamp"])
                except (KeyError, ValueError, json.JSONDecodeError):
                    continue
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if ts >= cutoff and not entry.get("dry_run", False):
                    count += 1
    except OSError:
        return 0.0
    return float(count)


def _benchmark_search_latency() -> tuple[float | None, float | None]:
    """Measure real search latency from a few deterministic benchmark queries."""
    from tools.search import search

    durations = []
    for query in SEARCH_BENCHMARK_QUERIES:
        started = time.perf_counter()
        try:
            search(query, limit=5)
        except Exception as e:
            print(f"WARNING: Search benchmark failed for {query!r}: {e}", file=sys.stderr)
            continue
        durations.append((time.perf_counter() - started) * 1000)
    return _percentile(durations, 0.5), _percentile(durations, 0.95)


def collect_all() -> dict:
    """Collect all metrics. Returns {metric_name: value}."""
    conn = get_conn()
    if conn is None:
        return {"error": "DB unavailable"}

    metrics = {}

    # Chunk and entity counts
    metrics["chunk_count"] = _collect_metric(
        conn, "chunk_count",
        "SELECT count(*) FROM puremind_chunks"
    )
    metrics["entity_count"] = _collect_metric(
        conn, "entity_count",
        "SELECT count(*) FROM pm_entities"
    )
    metrics["relationship_count"] = _collect_metric(
        conn, "relationship_count",
        "SELECT count(*) FROM pm_relationships"
    )

    # Audit stats (last hour)
    metrics["audit_calls_1h"] = _collect_metric(
        conn, "audit_calls_1h",
        "SELECT count(*) FROM pm_audit WHERE ts > now() - interval '1 hour'"
    )
    metrics["audit_errors_1h"] = _collect_metric(
        conn, "audit_errors_1h",
        "SELECT count(*) FROM pm_audit WHERE result='error' AND ts > now() - interval '1 hour'"
    )

    # Freshness
    metrics["embedding_freshness_hours"] = _collect_metric(
        conn, "embedding_freshness_hours",
        """SELECT EXTRACT(EPOCH FROM now() - max(updated_at))/3600
           FROM puremind_chunks"""
    )
    metrics["summary_freshness_hours"] = _collect_metric(
        conn, "summary_freshness_hours",
        """SELECT EXTRACT(EPOCH FROM now() - max(updated_at))/3600
           FROM pm_summaries"""
    )

    # Golden dataset size
    metrics["golden_count"] = _collect_metric(
        conn, "golden_count",
        "SELECT count(*) FROM pm_eval_golden WHERE active = true"
    )

    # Latest eval scores (most recent run)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT recall_at_5, mrr, ndcg_at_5, faithfulness_score,
                          personalisation_score, security_pass
                   FROM pm_eval_runs ORDER BY ts DESC LIMIT 1"""
            )
            row = cur.fetchone()
            if row:
                metrics["last_recall_at_5"] = float(row[0]) if row[0] else None
                metrics["last_mrr"] = float(row[1]) if row[1] else None
                metrics["last_ndcg_at_5"] = float(row[2]) if row[2] else None
                metrics["last_faithfulness"] = float(row[3]) if row[3] else None
                metrics["last_personalisation"] = float(row[4]) if row[4] else None
                metrics["last_security_pass"] = 1.0 if row[5] else 0.0
    except Exception:
        pass

    conn.close()

    # Fallback file check (outside DB)
    try:
        if AUDIT_FALLBACK.exists():
            metrics["fallback_lines"] = float(sum(1 for _ in AUDIT_FALLBACK.open()))
        else:
            metrics["fallback_lines"] = 0.0
    except Exception:
        metrics["fallback_lines"] = 0.0

    # Heartbeat health and search latency are derived from the actual runtime paths
    metrics["heartbeat_ok_24h"] = _count_recent_heartbeat_entries()
    bench_p50, bench_p95 = _benchmark_search_latency()
    metrics["search_latency_p50"] = bench_p50
    metrics["search_latency_p95"] = bench_p95

    # Round floats
    for k, v in metrics.items():
        if isinstance(v, float):
            metrics[k] = round(v, 2)

    return metrics


def store_metrics(metrics: dict):
    """Write metrics to pm_metrics table."""
    conn = get_write_conn()
    if conn is None:
        print("WARNING: Cannot store metrics (DB unavailable)", file=sys.stderr)
        return

    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM pm_metrics WHERE ts < now() - interval '90 days'"
            )
            for name, value in metrics.items():
                if value is None or name == "error":
                    continue
                cur.execute(
                    "INSERT INTO pm_metrics (metric, value) VALUES (%s, %s)",
                    (name, float(value))
                )
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"WARNING: Failed to store metrics: {e}", file=sys.stderr)
    finally:
        conn.close()


def _load_dedup() -> dict:
    """Load alert deduplication state."""
    try:
        if ALERT_DEDUP_FILE.exists():
            return json.loads(ALERT_DEDUP_FILE.read_text())
    except Exception:
        pass
    return {}


def _save_dedup(state: dict):
    """Save alert deduplication state."""
    try:
        ALERT_DEDUP_FILE.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", dir=str(ALERT_DEDUP_FILE.parent), delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(json.dumps(state))
            tmp.flush()
            os.fchmod(tmp.fileno(), 0o600)
            temp_name = tmp.name
        os.replace(temp_name, ALERT_DEDUP_FILE)
    except Exception:
        pass


def check_thresholds(metrics: dict) -> list[str]:
    """Check metrics against thresholds, return list of alert messages."""
    alerts = []
    now = time.time()
    dedup = _load_dedup()

    for metric_name, (op, threshold, desc) in THRESHOLDS.items():
        value = metrics.get(metric_name)
        if value is None:
            continue

        breached = False
        if op == "gt" and value > threshold:
            breached = True
        elif op == "lt" and value < threshold:
            breached = True

        if breached:
            # Check dedup
            last_alert = dedup.get(metric_name, 0)
            if now - last_alert < ALERT_DEDUP_SECONDS:
                continue

            dedup[metric_name] = now
            alerts.append(f"[pureMind] {desc} ({metric_name}={value})")

    _save_dedup(dedup)
    return alerts


def send_alerts(alerts: list[str]):
    """Send alert messages via Telegram."""
    if not alerts:
        return

    message = "\n".join(alerts)
    try:
        subprocess.run(
            ["python3",
             str(VAULT_ROOT / ".claude/integrations/telegram_integration.py"),
             "post_alert", message],
            capture_output=True, timeout=30,
        )
    except Exception as e:
        print(f"WARNING: Failed to send alerts: {e}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="pureMind metrics collector")
    parser.add_argument("--dry-run", action="store_true",
                        help="Collect and print without storing")
    parser.add_argument("--json", action="store_true",
                        help="JSON output")

    args = parser.parse_args()

    metrics = collect_all()

    if args.json:
        print(json.dumps(metrics, indent=2))
        return

    if not args.dry_run:
        store_metrics(metrics)

    # Check thresholds and alert
    alerts = check_thresholds(metrics)
    if alerts:
        if args.dry_run:
            print("Would alert:", file=sys.stderr)
            for a in alerts:
                print(f"  {a}", file=sys.stderr)
        else:
            send_alerts(alerts)

    # Print summary
    print(f"Metrics collected: {len([v for v in metrics.values() if v is not None])}")
    for name, value in sorted(metrics.items()):
        if value is not None and name != "error":
            flag = ""
            if name in THRESHOLDS:
                op, thresh, _ = THRESHOLDS[name]
                if (op == "gt" and value > thresh) or (op == "lt" and value < thresh):
                    flag = " *** THRESHOLD BREACHED ***"
            print(f"  {name}: {value}{flag}")

    if alerts:
        print(f"\nAlerts fired: {len(alerts)}")


if __name__ == "__main__":
    main()
