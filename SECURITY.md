# pureMind Security Model

## Threat Model

| Surface | Threats | Mitigations |
|---|---|---|
| **Data** | Credential leakage, unauthorized vault access | Credentials externalized to `~/.config/puremind/secrets.env` (0600). Vault is Git-tracked; `.gitignore` blocks `*credentials*`, `*secrets*`, `*.env`. Tailscale segmentation on DB. |
| **Model** | Prompt injection via ingested content, instruction override | Content sanitization pipeline (`tools/sanitize.py`). `<document>` fencing with UNTRUSTED DATA markers. Pattern stripping for role injection, instruction override, token markers. |
| **Tool** | Unauthorized integration calls, scope escalation | Python wrapper allowlists per integration. `@audited` decorator on all calls. Rate limiting (per-user, 0700). Write ops fail closed if audit DB unavailable. Heartbeat 3-layer action validation. |
| **Governance** | Unlogged operations, stale credentials, dependency vulns | JSONL audit fallback (no call unlogged). Dependency pinning in `requirements.txt`. Quarterly review checklist below. |

## Credential Management

Secrets are resolved in order: environment variable > `~/.config/puremind/secrets.env` > hardcoded fallback (deprecated, prints warning).

| Secret | Env Var | Used By |
|---|---|---|
| PostgreSQL DSN | `PUREMIND_DB_DSN` | `tools/db.py`, `.claude/integrations/base.py` |
| Telegram bot token | `PUREMIND_TELEGRAM_TOKEN` | `.claude/integrations/telegram_integration.py` |
| Telegram chat ID | `PUREMIND_TELEGRAM_CHAT_ID` | `.claude/integrations/telegram_integration.py` |

**Rotation schedule:** Quarterly. Update `~/.config/puremind/secrets.env` and restart systemd timers.

**The secrets.env file must be mode 0600 and live outside the vault.** Never commit credentials to this repository.

## Content Sanitization

All external content passes through `tools/sanitize.py` before entering Claude prompts. Four layers:

1. **Control char removal** -- null bytes, ASCII control chars (except `\n`, `\r`, `\t`)
2. **Injection pattern stripping** -- instruction overrides, role injection, token markers, prompt leaking
3. **Fence escaping** -- `<document>`, `<system>`, `<instructions>` tags neutralized; `javascript:` and `data:` URIs blocked
4. **Size enforcement** -- hard truncation with marker

### Where sanitization is applied

| Tool | What's sanitized |
|---|---|
| `tools/extract.py` | Document content before entity extraction prompt |
| `tools/summarize.py` | Document content before summary prompt |
| `tools/heartbeat.py` | All gathered integration state before reasoning prompt |
| `tools/ingest.py` | Ingested content before writing to vault |

### What clean content looks like

Normal markdown, code, and prose passes through unchanged. The sanitizer is tuned to catch injection patterns while preserving legitimate document content.

## Permission Model

Four integrations with explicit allowlists (defined in each `*_integration.py`):

- **Gmail:** read + draft only. No send, reply, delete.
- **GitHub:** read + comment only. No merge, push, close.
- **Calendar:** read-only. No create, update, delete.
- **Telegram:** alerts chat only. No DMs, no other chats.

All calls logged to `pm_audit` table via `@audited` decorator. Write ops blocked if audit DB unavailable (fail-closed).

## Audit Logging

Every integration call is logged to `pm_audit` (PostgreSQL). If the DB is unavailable, entries fall back to `~/.cache/puremind/audit_fallback.jsonl`.

Rate limiter state is stored in `$XDG_RUNTIME_DIR/puremind_rate/` (mode 0700, per-user).

## Red Team Testing

### Fast tests (no Claude CLI, <1s)
```bash
cd ~/pureMind && python3 -m pytest tests/test_sanitize.py -v
```

Tests 8 attack categories from `tests/payloads.json`:
- Direct instruction override
- Role injection
- Fence escape
- JSON injection
- Unicode smuggling
- Social engineering
- Markdown injection
- Context flooding

### Integration tests (Claude CLI, ~5 min)
```bash
cd ~/pureMind && python3 -m pytest tests/test_injection.py -v --timeout=300
```

Feeds sanitized attack payloads through the actual entity extraction pipeline and verifies Claude does not follow injected instructions.

**Success metric:** 0% attacker success (all extraction outputs contain only valid entity types and names).

## Resource Limits

| Resource | Limit | Where |
|---|---|---|
| PDF extraction | 120s timeout, 200 pages max | `tools/ingest.py` |
| Entity extraction content | 30,000 chars | `tools/extract.py` via `sanitize_content()` |
| Summary content | 20,000 chars | `tools/summarize.py` via `sanitize_content()` |
| Heartbeat state per source | 5,000 chars | `tools/heartbeat.py` via `sanitize_content()` |
| Ingested content | 1MB | `tools/ingest.py` MAX_TEXT_BYTES |
| Claude CLI timeout | 120s | extract.py, summarize.py, heartbeat.py |

## Quarterly Review Checklist

- [ ] Rotate DB password (update `~/.config/puremind/secrets.env`, restart services)
- [ ] Rotate Telegram bot token if compromised
- [ ] Run `pip install --upgrade` for pinned dependencies, update `requirements.txt`
- [ ] Run full test suite: `python3 -m pytest tests/ -v`
- [ ] Review `pm_audit` table for anomalies
- [ ] Check `~/.cache/puremind/audit_fallback.jsonl` for DB outage entries
- [ ] Verify `.gitignore` patterns still cover all sensitive files
- [ ] Review and prune entity graph for stale/incorrect entries
