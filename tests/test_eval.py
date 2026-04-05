"""Unit tests for pureMind evaluation harness metric computations.

No Claude CLI required -- tests pure math helpers and ops utility functions.
Run: python3 -m pytest tests/test_eval.py -v
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from tools.eval_harness import (
    _extract_verdict, _reciprocal_rank, _recall_at_k, _dcg_at_k, _ndcg_at_k,
)


class TestReciprocalRank:
    def test_first_position(self):
        assert _reciprocal_rank({1, 2}, [1, 3, 4]) == 1.0

    def test_second_position(self):
        assert _reciprocal_rank({2}, [1, 2, 3]) == 0.5

    def test_third_position(self):
        assert abs(_reciprocal_rank({3}, [1, 2, 3]) - 1/3) < 0.001

    def test_no_match(self):
        assert _reciprocal_rank({10}, [1, 2, 3]) == 0.0

    def test_empty_retrieved(self):
        assert _reciprocal_rank({1}, []) == 0.0

    def test_empty_relevant(self):
        assert _reciprocal_rank(set(), [1, 2, 3]) == 0.0


class TestRecallAtK:
    def test_perfect_recall(self):
        assert _recall_at_k({1, 2}, [1, 2, 3], k=5) == 1.0

    def test_partial_recall(self):
        assert _recall_at_k({1, 2, 3}, [1, 4, 5], k=5) == 1/3

    def test_zero_recall(self):
        assert _recall_at_k({1, 2}, [3, 4, 5], k=5) == 0.0

    def test_k_limit(self):
        # Only first 2 results checked
        assert _recall_at_k({3}, [1, 2, 3], k=2) == 0.0

    def test_empty_relevant(self):
        assert _recall_at_k(set(), [1, 2, 3], k=5) == 0.0


class TestNDCG:
    def test_perfect_ranking(self):
        # All relevant docs at top
        relevant = {1, 2}
        retrieved = [1, 2, 3, 4, 5]
        ndcg = _ndcg_at_k(relevant, retrieved, k=5)
        assert ndcg == 1.0

    def test_imperfect_ranking(self):
        relevant = {3}
        retrieved = [1, 2, 3, 4, 5]
        ndcg = _ndcg_at_k(relevant, retrieved, k=5)
        assert 0 < ndcg < 1.0

    def test_no_relevant_found(self):
        assert _ndcg_at_k({10}, [1, 2, 3], k=3) == 0.0

    def test_empty_relevant(self):
        assert _ndcg_at_k(set(), [1, 2], k=2) == 0.0

    def test_dcg_values(self):
        # DCG with relevant at position 1: 1/log2(2) = 1.0
        relevant = {1}
        retrieved = [1, 2, 3]
        dcg = _dcg_at_k(relevant, retrieved, k=3)
        assert abs(dcg - 1.0) < 0.001


class TestMetricsCollector:
    def test_thresholds_defined(self):
        from tools.metrics_collector import THRESHOLDS
        assert "chunk_count" in THRESHOLDS
        assert "heartbeat_ok_24h" in THRESHOLDS
        assert "embedding_freshness_hours" in THRESHOLDS

    def test_threshold_operators(self):
        from tools.metrics_collector import THRESHOLDS
        for name, (op, value, desc) in THRESHOLDS.items():
            assert op in ("gt", "lt"), f"Invalid operator for {name}: {op}"
            assert isinstance(value, (int, float))
            assert isinstance(desc, str)

    def test_check_thresholds_returns_list(self):
        from tools.metrics_collector import check_thresholds
        alerts = check_thresholds({"chunk_count": 200, "heartbeat_ok_24h": 5})
        assert isinstance(alerts, list)

    def test_threshold_breach_detected(self):
        from tools.metrics_collector import check_thresholds, ALERT_DEDUP_FILE
        # Clear dedup state so test isn't suppressed by prior runs
        if ALERT_DEDUP_FILE.exists():
            ALERT_DEDUP_FILE.unlink()
        alerts = check_thresholds({"chunk_count": 10})
        assert any("chunk" in a.lower() for a in alerts)

    def test_state_root_uses_puremind_subdir(self):
        from tools.metrics_collector import _state_root
        root = _state_root()
        assert root.name == "puremind"

    def test_heartbeat_counter_parses_recent_entries(self, tmp_path):
        from tools.metrics_collector import _count_recent_heartbeat_entries

        now = datetime.now(timezone.utc)
        log = tmp_path / "heartbeat-log.jsonl"
        log.write_text(
            "\n".join([
                json.dumps({"timestamp": now.isoformat(), "dry_run": False}),
                json.dumps({"timestamp": (now - timedelta(hours=23)).isoformat(), "dry_run": False}),
                json.dumps({"timestamp": (now - timedelta(hours=25)).isoformat(), "dry_run": False}),
                json.dumps({"timestamp": now.isoformat(), "dry_run": True}),
            ]) + "\n",
            encoding="utf-8",
        )
        assert _count_recent_heartbeat_entries(log) == 2.0


class TestEvalGolden:
    def test_normalize_query(self):
        from tools.eval_golden import _normalize_query
        assert _normalize_query("  What   Is  PGVECTOR? ") == "what is pgvector?"

    def test_query_hash_is_stable(self):
        from tools.eval_golden import _query_hash
        assert _query_hash("What is pgvector?") == _query_hash("  what is   pgvector?  ")


class TestFaithfulnessVerdict:
    def test_extract_verdict_faithful(self):
        assert _extract_verdict("FAITHFUL") is True

    def test_extract_verdict_unfaithful(self):
        assert _extract_verdict("The answer is UNFAITHFUL") is False

    def test_extract_verdict_unknown(self):
        assert _extract_verdict("Cannot determine") is None
