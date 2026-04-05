#!/usr/bin/env python3
"""pureMind evaluation harness -- weekly quality assessment across 6 metrics.

Measures retrieval quality, generation faithfulness, personalisation,
latency, security, and cost. Results written to pm_eval_runs and posted
to Telegram.

Usage:
    python3 eval_harness.py                # Full eval
    python3 eval_harness.py --dry-run      # Preview without writing
    python3 eval_harness.py --retrieval-only
    python3 eval_harness.py --json
"""

import argparse
import json
import random
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

_PARENT = str(Path(__file__).resolve().parent.parent)
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

from tools.db import get_conn, get_write_conn
from tools.embed import embed_query

VAULT_ROOT = Path.home() / "pureMind"


# ---------------------------------------------------------------------------
# Retrieval metrics (sklearn-compatible, pure math)
# ---------------------------------------------------------------------------

def _reciprocal_rank(relevant: set, retrieved: list) -> float:
    """Compute reciprocal rank: 1/position of first relevant result."""
    for i, chunk_id in enumerate(retrieved, 1):
        if chunk_id in relevant:
            return 1.0 / i
    return 0.0


def _recall_at_k(relevant: set, retrieved: list, k: int) -> float:
    """Fraction of relevant docs found in top-k results."""
    if not relevant:
        return 0.0
    found = sum(1 for cid in retrieved[:k] if cid in relevant)
    return found / len(relevant)


def _dcg_at_k(relevant: set, retrieved: list, k: int) -> float:
    """Discounted cumulative gain at k."""
    dcg = 0.0
    for i, chunk_id in enumerate(retrieved[:k]):
        rel = 1.0 if chunk_id in relevant else 0.0
        dcg += rel / np.log2(i + 2)  # i+2 because log2(1) = 0
    return dcg


def _ndcg_at_k(relevant: set, retrieved: list, k: int) -> float:
    """Normalized DCG at k."""
    dcg = _dcg_at_k(relevant, retrieved, k)
    # Ideal DCG: all relevant docs at the top
    ideal = sum(1.0 / np.log2(i + 2) for i in range(min(len(relevant), k)))
    return dcg / ideal if ideal > 0 else 0.0


def eval_retrieval(limit: int = 5) -> dict:
    """Run golden queries through search, compute Recall@k, MRR, nDCG.

    Uses the search module directly (BM25 + vector hybrid).
    """
    conn = get_conn()
    if conn is None:
        return {"error": "DB unavailable"}

    # Load golden pairs with ground truth
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, query, relevant_chunk_ids FROM pm_eval_golden
               WHERE active = true AND relevant_chunk_ids IS NOT NULL
               AND array_length(relevant_chunk_ids, 1) > 0"""
        )
        golden = cur.fetchall()

    if not golden:
        return {"error": "No golden pairs with chunk IDs", "count": 0}

    # Import search function
    from tools.search import search

    mrr_scores = []
    recall_5_scores = []
    recall_10_scores = []
    ndcg_5_scores = []
    per_query = []

    for gid, query, relevant_ids in golden:
        relevant = set(relevant_ids)

        # Run hybrid search
        try:
            results = search(query, limit=10)
        except Exception as e:
            per_query.append({"id": gid, "query": query, "error": str(e)})
            continue

        # Extract chunk IDs from results
        retrieved_ids = []
        for r in results:
            if "chunk_id" in r:
                retrieved_ids.append(r["chunk_id"])
            elif "id" in r:
                retrieved_ids.append(r["id"])

        rr = _reciprocal_rank(relevant, retrieved_ids)
        r5 = _recall_at_k(relevant, retrieved_ids, 5)
        r10 = _recall_at_k(relevant, retrieved_ids, 10)
        n5 = _ndcg_at_k(relevant, retrieved_ids, 5)

        mrr_scores.append(rr)
        recall_5_scores.append(r5)
        recall_10_scores.append(r10)
        ndcg_5_scores.append(n5)

        per_query.append({
            "id": gid, "query": query[:60],
            "rr": round(rr, 3), "recall@5": round(r5, 3),
            "ndcg@5": round(n5, 3),
            "retrieved": len(retrieved_ids), "relevant": len(relevant),
        })

    conn.close()
    return {
        "recall_at_5": round(np.mean(recall_5_scores), 4) if recall_5_scores else 0,
        "recall_at_10": round(np.mean(recall_10_scores), 4) if recall_10_scores else 0,
        "mrr": round(np.mean(mrr_scores), 4) if mrr_scores else 0,
        "ndcg_at_5": round(np.mean(ndcg_5_scores), 4) if ndcg_5_scores else 0,
        "golden_count": len(golden),
        "evaluated": len(mrr_scores),
        "per_query": per_query,
    }


# ---------------------------------------------------------------------------
# Generation quality (Claude CLI as judge)
# ---------------------------------------------------------------------------

def eval_generation(sample_size: int = 10) -> dict:
    """Sample golden pairs, generate answers, judge faithfulness."""
    conn = get_conn()
    if conn is None:
        return {"error": "DB unavailable"}

    with conn.cursor() as cur:
        cur.execute(
            """SELECT query, answer FROM pm_eval_golden
               WHERE active = true ORDER BY random() LIMIT %s""",
            (sample_size,)
        )
        samples = cur.fetchall()
    conn.close()

    if not samples:
        return {"error": "No golden pairs", "faithfulness_score": 0}

    faithful_count = 0
    total_judged = 0

    for query, gold_answer in samples:
        # Generate answer via search + Claude
        prompt = (
            f"Answer this question about PureTensor/pureMind based on your knowledge:\n"
            f"Question: {query}\n\n"
            f"Be concise (1-3 sentences)."
        )
        try:
            gen_result = subprocess.run(
                ["claude", "-p", "--max-turns", "1", "--output-format", "text"],
                input=prompt, capture_output=True, text=True, timeout=60,
            )
            generated = gen_result.stdout.strip() if gen_result.returncode == 0 else ""
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue

        if not generated:
            continue

        # Judge faithfulness
        judge_prompt = (
            f"Judge if the GENERATED answer is faithful to the REFERENCE answer. "
            f"They don't need to be identical, but the generated answer should not "
            f"contradict or hallucinate beyond the reference.\n\n"
            f"REFERENCE: {gold_answer}\n"
            f"GENERATED: {generated}\n\n"
            f"Reply with exactly one word: FAITHFUL or UNFAITHFUL"
        )
        try:
            judge_result = subprocess.run(
                ["claude", "-p", "--max-turns", "1", "--output-format", "text"],
                input=judge_prompt, capture_output=True, text=True, timeout=60,
            )
            verdict = judge_result.stdout.strip().upper() if judge_result.returncode == 0 else ""
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue

        total_judged += 1
        if "FAITHFUL" in verdict and "UNFAITHFUL" not in verdict:
            faithful_count += 1

    score = faithful_count / total_judged if total_judged > 0 else 0
    return {
        "faithfulness_score": round(score, 4),
        "judged": total_judged,
        "faithful": faithful_count,
        "sampled": len(samples),
    }


# ---------------------------------------------------------------------------
# Personalisation (embedding similarity)
# ---------------------------------------------------------------------------

def eval_personalisation() -> dict:
    """Compare Claude-generated content against style templates."""
    template_path = VAULT_ROOT / "templates" / "email-style.md"
    if not template_path.exists():
        return {"personalisation_score": 0, "error": "No email-style.md template"}

    template_text = template_path.read_text(encoding="utf-8")[:2000]
    template_emb = np.array(embed_query(template_text))

    # Generate a sample email in operator's style
    prompt = (
        "Draft a brief professional email from HAL (hal@puretensor.ai) to a "
        "business partner about scheduling a meeting next week. Use PureTensor's "
        "direct, concise communication style. 3-4 sentences max."
    )
    try:
        result = subprocess.run(
            ["claude", "-p", "--max-turns", "1", "--output-format", "text"],
            input=prompt, capture_output=True, text=True, timeout=60,
        )
        generated = result.stdout.strip() if result.returncode == 0 else ""
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return {"personalisation_score": 0, "error": "Claude CLI unavailable"}

    if not generated:
        return {"personalisation_score": 0, "error": "Empty generation"}

    gen_emb = np.array(embed_query(generated))

    # Cosine similarity (embeddings are already normalized)
    similarity = float(np.dot(template_emb, gen_emb))

    return {
        "personalisation_score": round(max(0, similarity), 4),
        "template_chars": len(template_text),
        "generated_chars": len(generated),
    }


# ---------------------------------------------------------------------------
# Latency (from pm_audit)
# ---------------------------------------------------------------------------

def eval_latency() -> dict:
    """Compute P50/P95 search latency from audit log."""
    conn = get_conn()
    if conn is None:
        return {"error": "DB unavailable"}

    with conn.cursor() as cur:
        cur.execute(
            """SELECT latency_ms FROM pm_audit
               WHERE latency_ms IS NOT NULL
               AND ts > now() - interval '7 days'
               ORDER BY ts DESC"""
        )
        latencies = [row[0] for row in cur.fetchall()]

    conn.close()

    if not latencies:
        return {"latency_p50_ms": 0, "latency_p95_ms": 0, "samples": 0}

    arr = np.array(latencies)
    return {
        "latency_p50_ms": int(np.percentile(arr, 50)),
        "latency_p95_ms": int(np.percentile(arr, 95)),
        "latency_mean_ms": int(np.mean(arr)),
        "samples": len(latencies),
    }


# ---------------------------------------------------------------------------
# Security (run test suite)
# ---------------------------------------------------------------------------

def eval_security() -> dict:
    """Run test_sanitize.py and check audit completeness."""
    # Run pytest programmatically
    try:
        result = subprocess.run(
            ["python3", "-m", "pytest", "tests/test_sanitize.py", "-v", "--tb=short"],
            capture_output=True, text=True, timeout=30,
            cwd=str(VAULT_ROOT),
        )
        output = result.stdout + result.stderr

        # Parse results
        import re
        match = re.search(r"(\d+) passed", output)
        passed = int(match.group(1)) if match else 0
        match_f = re.search(r"(\d+) failed", output)
        failed = int(match_f.group(1)) if match_f else 0
        total = passed + failed
        all_pass = failed == 0 and passed > 0
    except Exception as e:
        return {"security_pass": False, "error": str(e)}

    # Audit completeness: fraction of integration calls that were logged
    conn = get_conn()
    audit_completeness = 1.0
    if conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT count(*) FROM pm_audit
                   WHERE ts > now() - interval '7 days'"""
            )
            total_audited = cur.fetchone()[0]
            # If any fallback entries exist, completeness < 1.0
            fallback = Path.home() / ".cache" / "puremind" / "audit_fallback.jsonl"
            fallback_count = 0
            if fallback.exists():
                fallback_count = sum(1 for _ in fallback.open())
            if total_audited + fallback_count > 0:
                audit_completeness = total_audited / (total_audited + fallback_count)
        conn.close()

    return {
        "security_pass": all_pass,
        "tests_passed": passed,
        "tests_total": total,
        "audit_completeness": round(audit_completeness, 4),
    }


# ---------------------------------------------------------------------------
# Cost (Claude CLI usage estimation)
# ---------------------------------------------------------------------------

def eval_cost() -> dict:
    """Estimate Claude CLI usage from audit log."""
    conn = get_conn()
    if conn is None:
        return {"error": "DB unavailable"}

    with conn.cursor() as cur:
        # Count all calls in last 7 days (proxy for CLI usage)
        cur.execute(
            """SELECT count(*) FROM pm_audit
               WHERE ts > now() - interval '7 days'"""
        )
        calls_7d = cur.fetchone()[0]

        # Count by integration
        cur.execute(
            """SELECT integration, count(*) FROM pm_audit
               WHERE ts > now() - interval '7 days'
               GROUP BY integration ORDER BY count(*) DESC"""
        )
        by_integration = dict(cur.fetchall())

    conn.close()
    return {
        "cost_calls_7d": calls_7d,
        "by_integration": by_integration,
    }


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def run_full_eval(dry_run: bool = False, retrieval_only: bool = False) -> dict:
    """Run all 6 evaluations, write results, notify."""
    start = time.time()
    results = {}

    print("Eval: retrieval quality...", file=sys.stderr)
    results["retrieval"] = eval_retrieval()

    if not retrieval_only:
        print("Eval: generation quality...", file=sys.stderr)
        results["generation"] = eval_generation(sample_size=10)

        print("Eval: personalisation...", file=sys.stderr)
        results["personalisation"] = eval_personalisation()

        print("Eval: latency...", file=sys.stderr)
        results["latency"] = eval_latency()

        print("Eval: security...", file=sys.stderr)
        results["security"] = eval_security()

        print("Eval: cost...", file=sys.stderr)
        results["cost"] = eval_cost()

    elapsed = int(time.time() - start)
    results["elapsed_seconds"] = elapsed

    # Build summary
    r = results.get("retrieval", {})
    g = results.get("generation", {})
    p = results.get("personalisation", {})
    l = results.get("latency", {})
    s = results.get("security", {})
    c = results.get("cost", {})

    summary = (
        f"pureMind Weekly Eval\n"
        f"Retrieval: Recall@5={r.get('recall_at_5', '?')}, "
        f"MRR={r.get('mrr', '?')}, nDCG@5={r.get('ndcg_at_5', '?')} "
        f"({r.get('evaluated', 0)}/{r.get('golden_count', 0)} queries)\n"
    )
    if not retrieval_only:
        summary += (
            f"Generation: faithfulness={g.get('faithfulness_score', '?')} "
            f"({g.get('faithful', 0)}/{g.get('judged', 0)})\n"
            f"Personalisation: {p.get('personalisation_score', '?')}\n"
            f"Latency: P50={l.get('latency_p50_ms', '?')}ms, "
            f"P95={l.get('latency_p95_ms', '?')}ms\n"
            f"Security: {'PASS' if s.get('security_pass') else 'FAIL'} "
            f"({s.get('tests_passed', 0)}/{s.get('tests_total', 0)}), "
            f"audit={s.get('audit_completeness', '?')}\n"
            f"Cost: {c.get('cost_calls_7d', '?')} calls/7d\n"
        )
    summary += f"Elapsed: {elapsed}s"

    results["summary"] = summary
    print(f"\n{summary}", file=sys.stderr)

    if dry_run:
        return results

    # Helper: convert numpy types to native Python for psycopg2
    def _py(val):
        if val is None:
            return None
        if hasattr(val, 'item'):  # numpy scalar
            return val.item()
        return val

    # Write to pm_eval_runs
    conn = get_write_conn()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO pm_eval_runs
                       (recall_at_5, recall_at_10, mrr, ndcg_at_5,
                        faithfulness_score, personalisation_score,
                        latency_p50_ms, latency_p95_ms,
                        security_pass, security_tests_passed, security_tests_total,
                        audit_completeness, cost_calls_7d, golden_count,
                        detail, summary)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        _py(r.get("recall_at_5")), _py(r.get("recall_at_10")),
                        _py(r.get("mrr")), _py(r.get("ndcg_at_5")),
                        _py(g.get("faithfulness_score")), _py(p.get("personalisation_score")),
                        _py(l.get("latency_p50_ms")), _py(l.get("latency_p95_ms")),
                        _py(s.get("security_pass")), _py(s.get("tests_passed")),
                        _py(s.get("tests_total")), _py(s.get("audit_completeness")),
                        _py(c.get("cost_calls_7d")), _py(r.get("golden_count")),
                        json.dumps({k: v for k, v in results.items()
                                    if k not in ("summary",)}),
                        summary,
                    )
                )
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"WARNING: Failed to write eval results: {e}", file=sys.stderr)
        finally:
            conn.close()

    # Notify via Telegram
    try:
        subprocess.run(
            ["python3", str(VAULT_ROOT / ".claude/integrations/telegram_integration.py"),
             "post_alert", summary],
            capture_output=True, timeout=30,
        )
    except Exception:
        pass

    return results


def main():
    parser = argparse.ArgumentParser(description="pureMind evaluation harness")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run evals but don't write results")
    parser.add_argument("--retrieval-only", action="store_true",
                        help="Only run retrieval eval")
    parser.add_argument("--json", action="store_true",
                        help="Output results as JSON")

    args = parser.parse_args()
    results = run_full_eval(dry_run=args.dry_run, retrieval_only=args.retrieval_only)

    if args.json:
        # Remove per_query detail for clean JSON (too verbose)
        clean = {k: v for k, v in results.items()}
        if "retrieval" in clean and "per_query" in clean["retrieval"]:
            clean["retrieval"] = {k: v for k, v in clean["retrieval"].items()
                                  if k != "per_query"}
        print(json.dumps(clean, indent=2, default=str))


if __name__ == "__main__":
    main()
