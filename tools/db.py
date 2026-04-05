"""Shared database connection for pureMind tools.

Single source of truth for connection helpers.
Used by search.py, index.py, extract.py, summarize.py.
Credentials resolved via tools.credentials (env > secrets.env > fallback).
"""

import sys
from pathlib import Path

import psycopg2

# Ensure parent is on path for direct script invocation
_PARENT = str(Path(__file__).resolve().parent.parent)
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

from tools.credentials import get_db_dsn


def get_conn():
    """Get a read-oriented database connection (autocommit=True).

    Use for search queries and read-only operations.
    """
    try:
        conn = psycopg2.connect(get_db_dsn(), connect_timeout=5)
        conn.autocommit = True
        return conn
    except psycopg2.OperationalError as e:
        print(f"ERROR: Cannot connect to vantage DB (fox-n1:30433): {e}", file=sys.stderr)
        return None


def get_write_conn():
    """Get a transactional database connection (autocommit=False).

    Use for extraction, summarization, and any multi-statement writes.
    Caller must conn.commit() or conn.rollback() explicitly.
    """
    try:
        conn = psycopg2.connect(get_db_dsn(), connect_timeout=5)
        conn.autocommit = False
        return conn
    except psycopg2.OperationalError as e:
        print(f"ERROR: Cannot connect to vantage DB (fox-n1:30433): {e}", file=sys.stderr)
        return None
