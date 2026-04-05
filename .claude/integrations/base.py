"""pureMind integration base -- audit logging, rate limiting, param sanitisation.

All integration wrappers use the @audited decorator and deny() for permission
enforcement. Permissions survive both CLI and library (import) usage.

Fixes applied from Codex Phase 4 review:
- A-01: deny() raises PermissionError (works in library mode, not just CLI)
- B-01: sanitise_params strips content keys (body, message, text, etc.)
- B-02: Write ops fail closed when audit DB is unavailable
- C-01: File-based rate limiter persists across process invocations
- I-01: @audited captures positional args via inspect.signature
"""

import fcntl
import inspect
import json
import os
import sys
import time
from functools import wraps
from pathlib import Path

import psycopg2

# Credentials resolved via tools.credentials (env > secrets.env > fallback)
_VAULT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _VAULT_ROOT not in sys.path:
    sys.path.insert(0, _VAULT_ROOT)

from tools.credentials import get_db_dsn

# Per-integration rate limits (calls per minute)
RATE_LIMITS = {
    "gmail": 30,
    "github": 60,
    "calendar": 30,
    "telegram": 20,
    "cluster": 60,
}

# Write operations that must fail closed (block if audit DB unavailable)
WRITE_OPS = {
    "gmail": {"create_draft"},
    "github": {"comment_pr", "comment_issue", "create_issue"},
    "telegram": {"post_alert"},
}

# Keys to strip entirely from audit log parameters
_SENSITIVE_KEYS = {"token", "password", "secret", "key", "authorization", "cookie"}

# Content keys to truncate aggressively (bodies, messages, etc.)
_CONTENT_KEYS = {"body", "message", "text", "content", "subject", "description", "raw"}

# File-based rate limiter state (per-user, mode 0700)
# Prefer XDG_RUNTIME_DIR (tmpfs, per-user), fall back to ~/.cache/
_RATE_DIR = Path(os.environ.get("XDG_RUNTIME_DIR", "")) / "puremind_rate" \
    if os.environ.get("XDG_RUNTIME_DIR") \
    else Path.home() / ".cache" / "puremind_rate"

# JSONL fallback for audit logging when DB is unavailable
_AUDIT_FALLBACK = Path.home() / ".cache" / "puremind" / "audit_fallback.jsonl"


def _get_db():
    """Get a database connection for audit logging."""
    try:
        conn = psycopg2.connect(get_db_dsn(), connect_timeout=5)
        conn.autocommit = True
        return conn
    except psycopg2.OperationalError as e:
        print(f"WARNING: Audit DB unavailable (fox-n1:30433/vantage): {e}", file=sys.stderr)
        return None


def sanitise_params(params: dict) -> dict:
    """Remove sensitive values and truncate content fields for audit logging.

    B-01 fix: content keys (body, message, text, etc.) truncated to 80 chars
    to prevent the audit table becoming a secondary sensitive-data store.
    """
    clean = {}
    for k, v in params.items():
        kl = k.lower()
        if any(s in kl for s in _SENSITIVE_KEYS):
            clean[k] = "***"
        elif any(s in kl for s in _CONTENT_KEYS):
            clean[k] = (str(v)[:80] + "...") if isinstance(v, str) and len(v) > 80 else v
        elif isinstance(v, str) and len(v) > 200:
            clean[k] = v[:200] + "..."
        else:
            clean[k] = v
    return clean


def rate_check(integration: str) -> bool:
    """File-based rate limiter with flock for atomicity.

    E-01: Uses exclusive flock around the full read-prune-write cycle to prevent
    concurrent processes from bypassing the limit. The lock file is the rate file
    itself, held for the duration of the check.
    """
    limit = RATE_LIMITS.get(integration, 60)
    _RATE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    rate_file = _RATE_DIR / f"{integration}.log"
    now = time.time()

    # Open (or create) the rate file and hold an exclusive lock for the full cycle
    fd = os.open(str(rate_file), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        with os.fdopen(os.dup(fd), "r") as rf:
            content = rf.read().strip()

        timestamps = []
        if content:
            try:
                timestamps = [float(t) for t in content.split("\n") if t]
            except ValueError:
                timestamps = []

        # Prune entries older than 60s
        timestamps = [t for t in timestamps if now - t < 60]

        if len(timestamps) >= limit:
            # Over limit -- rewrite pruned state and deny
            os.lseek(fd, 0, os.SEEK_SET)
            os.ftruncate(fd, 0)
            os.write(fd, ("\n".join(str(t) for t in timestamps) + "\n").encode())
            return False

        timestamps.append(now)
        os.lseek(fd, 0, os.SEEK_SET)
        os.ftruncate(fd, 0)
        os.write(fd, ("\n".join(str(t) for t in timestamps) + "\n").encode())
        return True
    finally:
        os.close(fd)  # releases flock


def _audit_fallback_write(integration: str, function: str, params: dict,
                          result: str, detail: str, latency_ms: int):
    """Write audit entry to JSONL fallback when DB is unavailable.

    D-01: Uses flock for concurrent writers, sets file mode 0600.
    """
    try:
        _AUDIT_FALLBACK.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "integration": integration,
            "function": function,
            "params": sanitise_params(params),
            "result": result,
            "detail": detail[:200] if detail else "",
            "latency_ms": latency_ms,
        }
        line = json.dumps(entry) + "\n"
        fd = os.open(str(_AUDIT_FALLBACK), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            os.write(fd, line.encode())
        finally:
            os.close(fd)
    except Exception as e:
        print(f"WARNING: Audit fallback write also failed: {e}", file=sys.stderr)


def audit_log(integration: str, function: str, params: dict,
              result: str, detail: str = "", latency_ms: int = 0) -> bool:
    """Write an audit entry to pm_audit. Falls back to JSONL if DB unavailable.

    B-01 fix: detail field truncated to 200 chars (no raw result content).
    Phase 8: JSONL fallback ensures no call goes unlogged.
    """
    conn = _get_db()
    if conn is None:
        _audit_fallback_write(integration, function, params, result, detail, latency_ms)
        return False
    try:
        safe_detail = detail[:200] if detail else ""
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO pm_audit (integration, function, parameters, result, detail, latency_ms)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (integration, function, json.dumps(sanitise_params(params)),
                 result, safe_detail, latency_ms),
            )
        return True
    except Exception as e:
        print(f"WARNING: Audit log write failed: {e}", file=sys.stderr)
        _audit_fallback_write(integration, function, params, result, detail, latency_ms)
        return False
    finally:
        conn.close()


def deny(integration: str, function: str, params: dict):
    """Log a denied operation and raise PermissionError.

    A-01 fix: raises PermissionError instead of sys.exit(1) so permission
    enforcement works in both CLI and library (import) usage.
    """
    audit_log(integration, function, params, "denied",
              f"Operation '{function}' is not permitted on {integration}")
    raise PermissionError(
        f"DENIED: {integration}.{function}() is not permitted by pureMind permission model.")


def audited(integration: str):
    """Decorator: rate check + audit logging + write-op fail-closed.

    I-01 fix: captures positional args via inspect.signature.
    B-02 fix: write operations blocked if audit DB is unavailable.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            fname = func.__name__

            # I-01: capture both positional and keyword args
            try:
                sig = inspect.signature(func)
                bound = sig.bind(*args, **kwargs)
                bound.apply_defaults()
                params = dict(bound.arguments)
            except (TypeError, ValueError):
                params = kwargs.copy()

            if not rate_check(integration):
                audit_log(integration, fname, params, "denied", "Rate limit exceeded")
                raise RuntimeError(
                    f"RATE LIMITED: {integration} exceeded "
                    f"{RATE_LIMITS.get(integration, 60)} calls/min")

            is_write = fname in WRITE_OPS.get(integration, set())

            # B-02: pre-check audit DB for write operations
            # D-01: log blocked write ops to fallback so they're never unlogged
            if is_write:
                test_conn = _get_db()
                if test_conn is None:
                    _audit_fallback_write(
                        integration, fname, params, "blocked",
                        "Write blocked: audit DB unavailable", 0)
                    raise RuntimeError(
                        f"Write operation {integration}.{fname}() blocked: "
                        f"audit DB unavailable. Writes require audit logging.")
                test_conn.close()

            start = time.time()
            try:
                result = func(*args, **kwargs)
                latency = int((time.time() - start) * 1000)
                # B-01: log char count, not raw content
                audit_log(integration, fname, params, "ok",
                          f"({len(str(result))} chars)" if result else "", latency)
                return result
            except (SystemExit, PermissionError):
                raise
            except Exception as e:
                latency = int((time.time() - start) * 1000)
                audit_log(integration, fname, params, "error", str(e)[:200], latency)
                raise
        return wrapper
    return decorator
