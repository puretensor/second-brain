"""pureMind integration base -- audit logging, rate limiting, param sanitisation.

All integration wrappers inherit from IntegrationBase to get consistent
audit logging to the pm_audit table and per-integration rate limiting.
"""

import json
import sys
import time
from functools import wraps

import psycopg2

DB_DSN = "postgresql://raguser:REDACTED_DB_PASSWORD@100.103.248.9:30433/vantage"

# Per-integration rate limits (calls per minute)
RATE_LIMITS = {
    "gmail": 30,
    "github": 60,
    "calendar": 30,
    "telegram": 20,
    "cluster": 60,
}

# In-memory token bucket (resets on process exit -- acceptable for CLI tools)
_rate_buckets: dict[str, list[float]] = {}

# Keys to strip from audit log parameters
_SENSITIVE_KEYS = {"token", "password", "secret", "key", "authorization", "cookie"}


def _get_db():
    """Get a database connection for audit logging."""
    try:
        conn = psycopg2.connect(DB_DSN)
        conn.autocommit = True
        return conn
    except psycopg2.OperationalError as e:
        print(f"WARNING: Audit DB unavailable (fox-n1:30433/vantage): {e}", file=sys.stderr)
        return None


def sanitise_params(params: dict) -> dict:
    """Remove sensitive values and truncate large fields for audit logging."""
    clean = {}
    for k, v in params.items():
        if any(s in k.lower() for s in _SENSITIVE_KEYS):
            clean[k] = "***"
        elif isinstance(v, str) and len(v) > 200:
            clean[k] = v[:200] + "..."
        else:
            clean[k] = v
    return clean


def rate_check(integration: str) -> bool:
    """Check if the integration is within its rate limit. Returns True if OK."""
    limit = RATE_LIMITS.get(integration, 60)
    now = time.time()
    bucket = _rate_buckets.setdefault(integration, [])
    # Prune entries older than 60s
    bucket[:] = [t for t in bucket if now - t < 60]
    if len(bucket) >= limit:
        return False
    bucket.append(now)
    return True


def audit_log(integration: str, function: str, params: dict,
              result: str, detail: str = "", latency_ms: int = 0):
    """Write an audit entry to pm_audit."""
    conn = _get_db()
    if conn is None:
        return
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO pm_audit (integration, function, parameters, result, detail, latency_ms)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (integration, function, json.dumps(sanitise_params(params)),
                 result, detail[:500], latency_ms),
            )
    except Exception as e:
        print(f"WARNING: Audit log write failed: {e}", file=sys.stderr)
    finally:
        conn.close()


def deny(integration: str, function: str, params: dict):
    """Log a denied operation and print error."""
    audit_log(integration, function, params, "denied",
              f"Operation '{function}' is not permitted on {integration}")
    print(f"DENIED: {integration}.{function}() is not permitted by pureMind permission model.",
          file=sys.stderr)
    sys.exit(1)


def audited(integration: str):
    """Decorator that wraps a function with rate checking and audit logging."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            fname = func.__name__
            params = kwargs.copy()

            if not rate_check(integration):
                audit_log(integration, fname, params, "denied", "Rate limit exceeded")
                print(f"RATE LIMITED: {integration} exceeded {RATE_LIMITS.get(integration, 60)} calls/min",
                      file=sys.stderr)
                sys.exit(1)

            start = time.time()
            try:
                result = func(*args, **kwargs)
                latency = int((time.time() - start) * 1000)
                audit_log(integration, fname, params, "ok",
                          str(result)[:200] if result else "", latency)
                return result
            except SystemExit:
                raise
            except Exception as e:
                latency = int((time.time() - start) * 1000)
                audit_log(integration, fname, params, "error", str(e)[:500], latency)
                raise
        return wrapper
    return decorator
