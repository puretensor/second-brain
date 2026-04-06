#!/usr/bin/env python3
"""pureMind migration test runner -- discovers and runs bash test_* functions.

Runs acceptance tests defined as bash functions prefixed with test_.
Implements 3-consecutive-failure stop logic for step-by-step migration validation.

Usage:
    python3 migrate_test_runner.py /tmp/migrate_tests.sh                # Run all tests
    python3 migrate_test_runner.py /tmp/migrate_tests.sh --json         # JSON output
    python3 migrate_test_runner.py /tmp/migrate_tests.sh --test test_dns # Run single test
    python3 migrate_test_runner.py /tmp/migrate_tests.sh --max-retries 5 # Custom retry limit

Test script convention:
    #!/bin/bash
    # Each function prefixed with test_ is a test case.
    # Exit 0 = pass, nonzero = fail. Stdout captured as detail.

    test_service_reachable() {
        curl -sf http://example.com/healthz
    }

    test_dns_resolves() {
        dig +short example.com | grep -q .
    }
"""

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_VAULT_ROOT = str(Path(__file__).resolve().parent.parent)
if _VAULT_ROOT not in sys.path:
    sys.path.insert(0, _VAULT_ROOT)

from tools.db import get_conn

INTEGRATION = "cluster"

# Test execution limits
DEFAULT_TIMEOUT = 30  # seconds per test
MAX_CONSECUTIVE_FAILURES = 3  # stop after this many consecutive failures on same test


def _discover_tests(script_path: str) -> list[str]:
    """Discover test_* functions in a bash script by parsing function definitions."""
    content = Path(script_path).read_text()
    # Match both "test_foo()" and "function test_foo" patterns
    pattern = re.compile(r'(?:^|\n)\s*(?:function\s+)?(test_\w+)\s*\(\s*\)')
    return pattern.findall(content)


def _run_test(script_path: str, test_name: str, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """Run a single test function from the script. Returns result dict."""
    start = time.monotonic()
    try:
        result = subprocess.run(
            ["bash", "-c", f"source {script_path}; {test_name}"],
            capture_output=True, text=True, timeout=timeout,
        )
        elapsed = round(time.monotonic() - start, 2)
        return {
            "test": test_name,
            "passed": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout.strip()[:500],
            "stderr": result.stderr.strip()[:200],
            "elapsed_s": elapsed,
        }
    except subprocess.TimeoutExpired:
        elapsed = round(time.monotonic() - start, 2)
        return {
            "test": test_name,
            "passed": False,
            "returncode": -1,
            "stdout": "",
            "stderr": f"TIMEOUT after {timeout}s",
            "elapsed_s": elapsed,
        }
    except Exception as e:
        elapsed = round(time.monotonic() - start, 2)
        return {
            "test": test_name,
            "passed": False,
            "returncode": -2,
            "stdout": "",
            "stderr": str(e)[:200],
            "elapsed_s": elapsed,
        }


def _log_audit(function: str, params: dict, result: str, detail: str, latency_ms: int):
    """Log test execution to pm_audit table."""
    conn = get_conn()
    if conn is None:
        return
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO pm_audit (integration, function, params, result, detail, latency_ms)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (INTEGRATION, function, json.dumps(params), result, detail[:500], latency_ms),
            )
        conn.commit()
    except Exception:
        pass


def run_tests(
    script_path: str,
    test_filter: str | None = None,
    max_retries: int = MAX_CONSECUTIVE_FAILURES,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    """Run all tests, tracking consecutive failures.

    Returns:
        {
            "script": str,
            "timestamp": str,
            "tests_discovered": int,
            "tests_run": int,
            "passed": int,
            "failed": int,
            "stopped_at": str | None,
            "stop_reason": str | None,
            "elapsed_s": float,
            "results": [...]
        }
    """
    if not Path(script_path).exists():
        return {"error": f"Script not found: {script_path}"}

    tests = _discover_tests(script_path)
    if not tests:
        return {"error": "No test_* functions found in script"}

    if test_filter:
        tests = [t for t in tests if t == test_filter]
        if not tests:
            return {"error": f"Test '{test_filter}' not found. Available: {_discover_tests(script_path)}"}

    start = time.monotonic()
    results = []
    passed = 0
    failed = 0
    stopped_at = None
    stop_reason = None
    consecutive_failures = {}  # test_name -> failure count

    for test_name in tests:
        result = _run_test(script_path, test_name, timeout)
        results.append(result)

        # Audit log
        _log_audit(
            f"migrate_test:{test_name}",
            {"script": str(script_path), "test": test_name},
            "ok" if result["passed"] else "error",
            result["stdout"][:200] if result["passed"] else result["stderr"][:200],
            int(result["elapsed_s"] * 1000),
        )

        if result["passed"]:
            passed += 1
            consecutive_failures[test_name] = 0
        else:
            failed += 1
            consecutive_failures[test_name] = consecutive_failures.get(test_name, 0) + 1

            if consecutive_failures[test_name] >= max_retries:
                stopped_at = test_name
                stop_reason = f"{test_name} failed {max_retries} consecutive times"
                break

    elapsed = round(time.monotonic() - start, 2)

    return {
        "script": str(script_path),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tests_discovered": len(_discover_tests(script_path)),
        "tests_run": len(results),
        "passed": passed,
        "failed": failed,
        "stopped_at": stopped_at,
        "stop_reason": stop_reason,
        "elapsed_s": elapsed,
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description="pureMind migration test runner")
    parser.add_argument("script", help="Path to bash test script")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--test", help="Run single test function")
    parser.add_argument("--max-retries", type=int, default=MAX_CONSECUTIVE_FAILURES,
                        help=f"Stop after N consecutive failures (default: {MAX_CONSECUTIVE_FAILURES})")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT,
                        help=f"Per-test timeout in seconds (default: {DEFAULT_TIMEOUT})")

    args = parser.parse_args()

    output = run_tests(
        script_path=args.script,
        test_filter=args.test,
        max_retries=args.max_retries,
        timeout=args.timeout,
    )

    if args.json:
        print(json.dumps(output, indent=2))
    else:
        if "error" in output:
            print(f"ERROR: {output['error']}", file=sys.stderr)
            sys.exit(1)

        print(f"Migration Tests: {output['script']}")
        print(f"  Discovered: {output['tests_discovered']} | Run: {output['tests_run']} | "
              f"Passed: {output['passed']} | Failed: {output['failed']} | "
              f"Elapsed: {output['elapsed_s']}s")

        if output["stopped_at"]:
            print(f"  STOPPED: {output['stop_reason']}")

        print()
        for r in output["results"]:
            status = "PASS" if r["passed"] else "FAIL"
            print(f"  [{status}] {r['test']} ({r['elapsed_s']}s)")
            if not r["passed"]:
                detail = r["stderr"] or r["stdout"]
                if detail:
                    print(f"         {detail[:120]}")

        sys.exit(0 if output["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
