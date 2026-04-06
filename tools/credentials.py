"""Credential resolution for pureMind tools.

Resolution order:
  1. Environment variable (set by systemd EnvironmentFile or shell)
  2. ~/.config/puremind/secrets.env file (mode 0600, outside vault)
  3. Hardcoded fallback (deprecated -- prints warning)

Never import credentials into Git-tracked files. Always use this module.
"""

import os
import sys
from pathlib import Path

_SECRETS_FILE = Path.home() / ".config" / "puremind" / "secrets.env"

_env_cache: dict[str, str] | None = None


def _load_env_file() -> dict[str, str]:
    """Parse key=value lines from secrets.env (ignoring comments and blanks).

    A-02: Strips BOM, validates file permissions (warns if not 0600),
    handles quoted values and values containing '='.
    """
    global _env_cache
    if _env_cache is not None:
        return _env_cache
    _env_cache = {}
    if not _SECRETS_FILE.exists():
        return _env_cache

    # A-02: warn if secrets.env is world/group readable
    mode = _SECRETS_FILE.stat().st_mode & 0o777
    if mode & 0o077:
        print(f"WARNING: {_SECRETS_FILE} has mode {oct(mode)} -- "
              f"should be 0600. Run: chmod 600 {_SECRETS_FILE}", file=sys.stderr)

    raw = _SECRETS_FILE.read_text(encoding="utf-8-sig")  # strips BOM
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip()
            # Strip surrounding quotes if present
            if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
                v = v[1:-1]
            _env_cache[k] = v
    return _env_cache


def _resolve(env_key: str) -> str | None:
    """Resolve a secret: env var > secrets.env. Returns None if not found."""
    val = os.environ.get(env_key)
    if val:
        return val
    val = _load_env_file().get(env_key)
    if val:
        return val
    return None


def get_db_dsn() -> str:
    """Get PostgreSQL DSN for the vantage database.

    A-01: Fails closed if neither env var nor secrets.env provides the DSN.
    No hardcoded fallback -- credentials must not live in Git-tracked files.
    """
    dsn = _resolve("PUREMIND_DB_DSN")
    if not dsn:
        raise RuntimeError(
            f"PUREMIND_DB_DSN not set. Configure via environment variable "
            f"or {_SECRETS_FILE}")
    return dsn


def get_telegram_config() -> dict:
    """Get Telegram bot token and chat ID."""
    return {
        "bot_token": _resolve("PUREMIND_TELEGRAM_TOKEN") or "",
        "chat_id": _resolve("PUREMIND_TELEGRAM_CHAT_ID") or "",
    }
