# Codex Review: pureMind Phase 4 -- Direct Integrations

## Your Role

You are a senior systems architect reviewing Phase 4 of **pureMind**, a sovereign second brain project. Your review is constructive and actionable. You do NOT make any changes -- you read, analyze, and produce structured suggestions.

## Context

pureMind is a cognitive augmentation system built on:
- **Claude Code CLI** (Max 20x subscription) as the sole LLM
- **Obsidian-compatible vault** (Markdown-native, Git-versioned) at `~/pureMind/`
- **pgvector + PostgreSQL FTS** for hybrid retrieval (Phase 3)
- **sentence-transformers on CPU** for embeddings (nomic-embed-text-v1.5, 768-dim)
- **Ray cluster** (160 CPUs, 2 GPUs, 200 GbE) as compute backbone

Phase 1 (Memory Foundation) created the vault. Phase 2 (Context Persistence & Hooks) wired lifecycle hooks. Phase 3 (Memory Search & Hybrid RAG) added hybrid search. All three were Codex-reviewed with fixes applied.

Phase 4 (Direct Integrations) connects pureMind to external services with a permission-enforced wrapper model. Each integration is a thin Python wrapper that enforces hardcoded read/write permissions, logs every call to an audit table, and rate-limits per integration.

### Phase 4 Deliverables

1. **Audit log schema** (`~/pureMind/migrations/002_audit_log.sql`) -- `pm_audit` table in the existing `vantage` database. Columns: id (bigserial), ts (timestamptz), integration (text), function (text), parameters (jsonb), result (text), detail (text), latency_ms (int). Indexes on ts DESC and (integration, ts DESC).

2. **Base integration module** (`~/pureMind/.claude/integrations/base.py`) -- Shared infrastructure for all wrappers:
   - `audit_log(integration, function, params, result, detail, latency_ms)` -- writes to pm_audit
   - `rate_check(integration)` -- in-memory token bucket (gmail:30/min, github:60/min, calendar:30/min, telegram:20/min)
   - `sanitise_params(params)` -- strips tokens, passwords, large bodies from audit params
   - `deny(integration, function, params)` -- logs denied op and exits
   - `@audited(integration)` -- decorator wrapping functions with rate check + audit logging

3. **Gmail integration** (`~/pureMind/.claude/integrations/gmail_integration.py`) -- Wraps `~/.config/puretensor/gmail.py` via subprocess for reads (search, get, list_inbox, list_unread). Uses Google API directly (google-api-python-client) for create_draft with existing OAuth tokens from `~/.config/puretensor/gdrive_tokens/`. Blocks: send, reply, trash, delete, spam, filter operations.

4. **GitHub integration** (`~/pureMind/.claude/integrations/github_integration.py`) -- Wraps `gh` CLI. All repos scoped to `puretensor` org. Allowed: list_repos, list_prs, get_pr, list_issues, get_issue, comment_pr, comment_issue, create_issue. Blocks: merge, push, close, delete.

5. **Calendar integration** (`~/pureMind/.claude/integrations/calendar_integration.py`) -- Wraps `~/nexus/tools/gcalendar.py` via subprocess. Read-only. Maps `list_events(days)` to gcalendar.py commands (days<=1 -> today, days<=7 -> week, days>7 -> upcoming). Blocks: create, update, delete.

6. **Telegram alerts** (`~/pureMind/.claude/integrations/telegram_integration.py`) -- Direct Bot API calls (urllib) to `@puretensor_alert_bot`. Allowed: post_alert (prefixes "[pureMind]"), read_channel. Blocks: DMs, other channels. Config from `telegram_config.json` or env vars.

7. **Claude Code skills** (`~/pureMind/.claude/skills/`) -- 5 skill files: `gmail.md`, `github.md`, `calendar.md`, `alerts.md`, `briefing.md`. Each documents allowed operations and CLI invocations for its integration.

8. **PRD recovery** (`~/pureMind/projects/puremind/prd-v2.md`, `PT-2026-SB-v2.pdf`) -- Full PRD transcribed to markdown and PDF copy saved to vault. Also uploaded to Google Drive. Closes Phase 1 issue I-01.

9. **Documentation updates** -- CLAUDE.md (integration section with permission model table, usage examples, skills list, components), README.md (Phase 4 status, expanded "What is live now"), project README (Phase 4 complete), daily log entry.

### Database Environment

- **Host:** fox-n1 (K3s), accessible at 100.103.248.9:30433 (NodePort)
- **Database:** `vantage` (shared with Alexandria/Nexus + pureMind Phase 3)
- **User:** `raguser` / `REDACTED_DB_PASSWORD`
- **Existing tables:** `puremind_chunks` (Phase 3), `facts`, `rag_documents`, `rag_chunks` (Nexus/Alexandria)
- **New table:** `pm_audit` (this phase)

### Permission Model (from PRD p8)

| Integration | Read | Write | Blocked |
|---|---|---|---|
| Gmail | search, get, list_inbox, list_unread | create_draft only | send, reply, trash, delete, spam, filters |
| GitHub | list_repos, list_prs, list_issues, get_pr, get_issue | comment_pr, comment_issue, create_issue | merge, push, close, delete |
| Calendar | list_events, get_event, search_events | None | create, update, delete |
| Telegram | read_channel | post_alert (alerts channel only) | DMs, other channels |

### Existing Tools Wrapped

- `~/.config/puretensor/gmail.py` -- full multi-account Gmail CLI (OAuth2, SMTP fallback, labels, filters). Tokens in `~/.config/puretensor/gdrive_tokens/`.
- `~/nexus/tools/gcalendar.py` -- Google Calendar CLI (list, create, search, get). Positional args: `{personal,ops,all} {today,week,upcoming,search,get,...}`.
- `gh` CLI -- GitHub CLI, already installed and authenticated for `puretensor` org.
- Telegram Bot API -- `@puretensor_alert_bot` (token `8546123559:...`), direct HTTPS calls.

## What to Review

### 1. Read the full integration codebase

Read every file in `~/pureMind/.claude/integrations/` and `~/pureMind/.claude/skills/`. Also read `~/pureMind/migrations/002_audit_log.sql` and the integration section in `~/pureMind/CLAUDE.md`. Understand the data flow: CLI invocation -> permission check -> subprocess/API call -> audit log -> formatted output.

### 2. Evaluate against these criteria

**A. Permission Model Enforcement**
- Are all blocked operations actually unreachable? Could a caller bypass the `BLOCKED_OPS` check by calling the underlying function directly (e.g., importing `_call_gmail` and passing "send")?
- Is the `deny()` function's `sys.exit(1)` appropriate? What if the integration is called as a library (imported) rather than CLI? Does the exit propagate correctly?
- Are there any operations that should be blocked but aren't in the current lists? Compare against the PRD permission table.
- Could command injection occur through any of the subprocess calls? (e.g., crafted message body in `comment_pr`, crafted query in `gmail search`)
- Is the hardcoded permission model (Python constants) the right pattern vs. a config file? What are the trade-offs for Phase 8 (Security Hardening)?

**B. Audit Logging (base.py + 002_audit_log.sql)**
- Is the `@audited` decorator correctly capturing function arguments? Does it handle *args and **kwargs properly?
- What happens if the audit DB is unreachable? Does the wrapper fail open (proceed without logging) or fail closed (block the operation)?
- Is the `sanitise_params()` function stripping all sensitive values? What about OAuth tokens that might appear in error messages or tracebacks?
- Is `bigserial` appropriate for the audit table? At the current call volume (~50/day), will it hit limits?
- Is `latency_ms` as `int` correct? Should it be `float` for sub-millisecond precision, or is integer millisecond sufficient?
- Should the audit table have a retention/rotation policy? It will grow indefinitely.
- Is the `parameters jsonb` column indexed? Should it be, for searching audit entries?
- Does the `detail` column truncation (if any) lose important diagnostic information?

**C. Rate Limiting (base.py)**
- The token bucket is in-memory and resets on process exit. Since each CLI invocation is a new process, does the rate limiter actually work? Or does it only limit within a single long-running import?
- If the rate limiter doesn't persist across process invocations, is it effectively useless for CLI usage?
- Are the rate limits (gmail:30/min, github:60/min, calendar:30/min, telegram:20/min) aligned with the upstream API limits?
- What happens when a rate limit is hit? Is the error message clear? Does it audit the denial?

**D. Gmail Integration (gmail_integration.py)**
- The wrapper calls gmail.py via subprocess for reads but uses Google API directly for create_draft. Is this mixed approach clean, or should it be consistent?
- Does the `create_draft` function correctly load OAuth tokens from the filesystem? What if the token is expired and needs refresh?
- Is the account mapping correct? Does `hal` map to the right token file?
- Could the `--query` argument to gmail.py be exploited for command injection? (subprocess with list args should be safe, but verify)
- Is the subprocess timeout (30s) appropriate for gmail operations (search can be slow on large mailboxes)?
- Error handling: if gmail.py returns a non-zero exit code, is the error message from stderr useful?

**E. GitHub Integration (github_integration.py)**
- The wrapper calls `gh` CLI with `--json` for structured output and `json.loads()` for parsing. What if `gh` returns non-JSON output (e.g., authentication errors, rate limit messages)?
- Is the `puretensor` org prefix hardcoded correctly everywhere? What if a repo name contains special characters?
- For `comment_pr` and `comment_issue`, is the `--body` argument shell-safe? (`subprocess.run` with list args should handle this, but verify)
- Is `create_issue` correctly creating issues in the right repo? Is there validation on the repo name?
- What happens if `gh` is not installed or not authenticated? Is the error message clear?
- The `--json` field list for `list_prs` and `list_issues` -- are all requested fields available in the current `gh` version?

**F. Calendar Integration (calendar_integration.py)**
- The `list_events(days)` function maps days to gcalendar.py commands: days<=1 -> today, days<=7 -> week, days>7 -> upcoming. Is this mapping correct? What about days=2 or days=3 (falls into "week" which shows the full week, not just 2-3 days)?
- Does the `search` command pass the query correctly via `-q`? Could special characters in the query break the subprocess call?
- The gcalendar.py `get` command uses `--id` flag. Is the event_id format validated or sanitised?
- What if gcalendar.py's OAuth token expires? Does it auto-refresh (it does, but verify the wrapper handles the refresh output)?

**G. Telegram Integration (telegram_integration.py)**
- The bot token is stored in a JSON config file in the repo. Is this acceptable for a Git-tracked vault? (telegram_config.json is in the integrations directory which is committed)
- The `post_alert` function uses `parse_mode: "Markdown"`. Does this create issues if the message contains Markdown special characters (*, _, `, [)?
- `read_channel` uses `getUpdates` which only returns messages sent TO the bot, not channel history. Is this limitation documented? Does the skill/briefing account for this?
- Is the `urlopen` timeout (10s) appropriate? What about network interruptions?
- The config loading tries env vars, then config file. Is the precedence correct? What if both are set with different values?

**H. Skills (*.md files)**
- Do the skill files accurately document only the allowed operations? Is there any mismatch between what the skill says and what the wrapper permits?
- Is the `/briefing` skill's sequence of calls (calendar, email, pending, GitHub, memory search) the right order? Could any call block or timeout and prevent later calls?
- Are the CLI examples in skills syntactically correct and tested? Would copy-pasting them work?
- Is there a skill for checking audit logs? (e.g., "show me recent integration activity")

**I. Code Quality & Security**
- Are all subprocess calls using list args (not `shell=True`)? This is critical for command injection prevention.
- Is the error handling consistent across all 4 integrations? Do they all raise RuntimeError, or is there a mix of exceptions?
- Are there any imports that could fail at runtime (google-api-python-client, psycopg2) without clear error messages?
- Is the `sys.path.insert(0, ...)` pattern for importing base.py clean? Could it shadow system modules?
- Are there any hardcoded paths that should be relative or configurable?
- Is there dead code in any of the integration files?
- Are the CLI argument parsers robust? What about missing required args, unknown args?

**J. Phase 5 Readiness**
- Phase 5 is "Skills Framework" -- extending the skill library with more complex multi-step skills. Do the Phase 4 integrations provide the right building blocks?
- Is the `@audited` decorator reusable for new integrations added in later phases?
- Is the base module extensible for the cluster monitoring integration (deferred from Phase 4)?
- Could the briefing skill evolve into an autonomous heartbeat agent (Phase 6) without major refactoring?
- Are there structural decisions in Phase 4 that create friction for Phase 8 (Security Hardening)?

### 3. Produce structured output

Format your review as follows. This exact format is required -- the operator will copy-paste it into Claude Code for triage and execution.

```
## PHASE 4 REVIEW: pureMind Direct Integrations

### Overall Assessment
[2-3 sentences: overall quality, biggest strength, biggest concern]

### Critical Issues (fix now)
- [ ] **[ISSUE-ID]:** [description] | File: [path] | Why: [reason]
- [ ] ...

### Important Improvements (should do)
- [ ] **[ISSUE-ID]:** [description] | File: [path] | Why: [reason]
- [ ] ...

### Nice-to-Haves (consider for later)
- [ ] **[ISSUE-ID]:** [description] | File: [path] | Why: [reason]
- [ ] ...

### Structural Observations
[bullet list of architectural observations -- things that aren't wrong but worth noting for future phases]

### Phase 5 Readiness Score
[X/10] -- [one sentence justification]

### Missing from Phase 4
[list anything the PRD specified for Phase 4 that was not delivered]
```

## Constraints

- **DO NOT modify any files.** This is a read-only review.
- **DO NOT create branches, PRs, or issues.** Output is text only.
- Be specific. "Improve error handling" is not actionable. "The `@audited` decorator at base.py:98 catches `Exception` broadly -- catch `psycopg2.OperationalError` specifically for DB failures and let unexpected exceptions propagate" is.
- Reference specific files and line numbers where relevant.
- Assume the reviewer (the operator) is deeply technical. No need to explain basic concepts.
- The project is for a real company (PureTensor, Inc.), not a hobby. Treat it accordingly.
- The Ray cluster (160 CPUs, 2 GPUs, 200 GbE) is the compute backbone for later phases. Note any Phase 4 decisions that help or hinder distributed processing.
- Credentials are hardcoded in tool scripts (DB_DSN, bot tokens in config). This matches the sovereign infrastructure pattern. Do not flag it as a security issue unless you have a specific bypass/exfiltration scenario.
- The permission model is intentionally hardcoded in Python (not config files). This is a design decision: permissions are code, not configuration. Flag only if there's a specific vulnerability.
- The integration wrappers are thin by design. They should NOT replicate the functionality of the tools they wrap. Flag any scope creep.
