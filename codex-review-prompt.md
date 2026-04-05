# Codex Review: pureMind Phase 2 -- Context Persistence & Hooks

## Your Role

You are a senior systems architect reviewing Phase 2 of **pureMind**, a sovereign second brain project. Your review is constructive and actionable. You do NOT make any changes -- you read, analyze, and produce structured suggestions.

## Context

pureMind is a cognitive augmentation system built on:
- **Claude Code CLI** (Max 20x subscription) as the sole LLM
- **Obsidian-compatible vault** (Markdown-native, Git-versioned) at `~/pureMind/`
- **pgvector + PostgreSQL FTS** for hybrid retrieval (Phase 3)
- **sentence-transformers on CPU** for embeddings, distributed via a Ray cluster (160 CPUs, 2 GPUs, 200 GbE)

Phase 1 (Memory Foundation) created the vault skeleton with soul.md, user.md, memory.md, knowledge files, project READMEs, and templates. Phase 1 was Codex-reviewed and 12 fixes applied (credential trimming, auto-commit scoping, daily-log schema, etc.).

Phase 2 (Context Persistence & Hooks) rewires three Claude Code lifecycle hooks to use the pureMind vault as the primary source and creates a daily reflection cron for MemGPT-inspired disk-to-RAM knowledge promotion. The PRD defines 9 phases over 56 days. Phases 1-2 are complete. Phases 3-9 are planned.

### Phase 2 Deliverables

1. **cc_session_start.py** (`~/tensor-scripts/hooks/cc_session_start.py`) -- Updated to resolve identity files (soul.md, user.md, memory.md) from pureMind first, falling back to legacy `~/.claude/` path. Handles case differences (pureMind lowercase vs legacy uppercase). Loads pending.md (20-line cap).

2. **cc_pre_compact.py** (`~/tensor-scripts/hooks/cc_pre_compact.py`) -- Updated to write compaction extracts to `~/pureMind/daily-logs/`, read soul.md from pureMind for recovery context, and git commit after daily log writes.

3. **cc_session_end.py** (`~/tensor-scripts/hooks/cc_session_end.py`) -- Enhanced to append session boundary markers (`---`) to the pureMind daily log and git commit. Runs in background, best-effort.

4. **daily_reflect.py** (`~/pureMind/.claude/hooks/daily_reflect.py`) -- New script. Nightly cron that reads today's daily log + current memory.md, calls Claude CLI (`claude -p --output-format json --max-turns 1`) to extract high-signal items, promotes them to memory.md, updates pending.md, archives logs >30 days, and git commits. Supports `--dry-run` and `--date` flags.

5. **Systemd timer** (`/etc/systemd/system/puremind-reflect.service` + `.timer`) -- Runs daily_reflect.py at 23:00 UTC daily with `Persistent=true`.

6. **Documentation updates** -- CLAUDE.md (hook docs), README.md (Phase 2 status), daily log (Phase 2 session entry), project README.

### Hook Registration

Hooks are registered in `~/.claude/settings.json` (not in the pureMind vault). The registration was NOT changed in Phase 2 -- same script paths, same events:
- `SessionStart` -> `cc_session_start.py`
- `PreCompact` -> `cc_pre_compact.py`
- `SessionEnd` -> `cc_session_end.py &` (background)
- `PreToolUse[Bash]` -> `bash_safety_guard.sh`
- `PostToolUse[Edit|Write]` -> py_compile, yaml_json_lint, ts_typecheck, cc_auto_report
- `Stop` -> auto-report check

### Memory Architecture

MemGPT-inspired three-tier hierarchy:
- **Register:** Live conversation context (ephemeral, in Claude Code context window)
- **RAM:** `memory/memory.md` (always loaded at session start, capped at ~5KB / 8K tokens)
- **Disk:** `daily-logs/`, `knowledge/`, `projects/` (searchable, not always loaded)

The daily reflection cron is the promotion mechanism: daily logs (Disk) -> memory.md (RAM). The cap is enforced at 5120 bytes.

## What to Review

### 1. Read the full GitHub repo
Clone or read every file in `puretensor/second-brain`. Also read the three hook scripts in `tensor-scripts/hooks/` (cc_session_start.py, cc_pre_compact.py, cc_session_end.py). Understand the data flow between them.

### 2. Evaluate against these criteria

**A. Source Resolution Logic (cc_session_start.py)**
- Is the pureMind-first / legacy-fallback pattern robust? What happens if pureMind dir exists but files are empty or corrupt?
- Is the PUREMIND_MAP (uppercase to lowercase mapping) the right approach vs alternatives (e.g., case-insensitive glob)?
- Is the 8000-char output budget appropriate? Could it be exceeded with large daily logs + memory.md?
- Is pending.md (20-line cap) the right addition? Should it be loaded with higher or lower priority?
- Are there files that should be loaded but aren't (e.g., CLAUDE.md, specific knowledge files)?

**B. Compaction Handling (cc_pre_compact.py)**
- Is the daily log write path resilient? What if the daily-logs/ directory doesn't exist?
- Is the git commit after compaction extract correct? Could it race with the auto-commit PostToolUse hook?
- Is the Nemotron extraction fallback chain sound (try vLLM -> fail silently -> proceed without)?
- Is the recovery context (soul.md[:500] + facts + TOOLS.md) the right content for post-compaction continuity?
- Could the recovery output exceed MAX_RECOVERY_OUTPUT (4000 chars) in practice? What gets truncated first?

**C. Session End (cc_session_end.py)**
- Is the background execution safe? Could it race with a rapid session restart?
- Is the `---` boundary marker the right format? Will it interfere with Obsidian rendering or daily log parsing?
- Is the git commit reliable when running in background with `&`? Could it conflict with concurrent git operations?
- SESSION_ID is always "unknown" (confirmed from 70+ entries). Should the script still reference it, or should it be cleaned up?

**D. Daily Reflection (daily_reflect.py)**
- Is the Claude CLI invocation robust? What happens when Claude CLI is not installed, not authenticated, or the subscription has lapsed?
- Is the JSON parsing resilient? Claude sometimes wraps JSON in markdown fences despite instructions. Is the fence-stripping logic sufficient?
- Is the promotion scoring prompt well-designed? Will Claude produce consistent, high-quality JSON output?
- Is the memory cap enforcement algorithm correct? Does trimming "Recent Promotions" first make sense, or should it be more sophisticated?
- Is the pending.md update logic correct? String replacement (`- [ ] {item}`) is fragile -- what if the text has slight differences?
- Is the 30-day archive threshold appropriate? Should it be configurable?
- Is the --dry-run mode truly side-effect-free? (No writes, no git, no Claude calls that mutate state)
- Is the JSONL reflection log useful for debugging and evaluation?
- Error handling: what happens if Claude returns valid JSON but with unexpected keys or empty lists?

**E. Systemd Timer**
- Is 23:00 UTC the right time? (Midnight BST in summer, 23:00 GMT in winter)
- Is `Persistent=true` correctly configured for a machine that may not be on 24/7?
- Is `TimeoutStartSec=180` sufficient for Claude CLI invocation?
- Should the service have restart/failure handling?
- Is system-level (`/etc/systemd/system/`) correct vs user-level (`~/.config/systemd/user/`)?

**F. Git Safety**
- Are there race conditions between the three git-committing hooks (PreCompact, SessionEnd, auto-commit PostToolUse)?
- Should any of them use git locking or atomic operations?
- Is `git -C ~/pureMind add -A` in daily_reflect.py safe, or should it scope to specific paths like the auto-commit hook does?
- Could rapid compaction + session end + new session start create a dirty git state?

**G. Documentation (CLAUDE.md)**
- Is the hook documentation section accurate and complete?
- Does it explain the data flow clearly enough for a new Claude Code session to understand the system?
- Are there any contradictions between CLAUDE.md and the actual hook behavior?

**H. Failure Modes & Edge Cases**
- What happens on the first run after Phase 2 deploy (no previous daily logs, empty memory.md)?
- What happens if the pureMind git repo is in a dirty state when hooks fire?
- What happens if two Claude Code sessions are active simultaneously?
- What happens if the daily reflection cron runs but today's daily log is empty or malformed?
- What happens if memory.md hits the cap and the reflection tries to add more items?

**I. Phase 3 Readiness**
- Does Phase 2's output create the right foundation for Phase 3 (Hybrid RAG with pgvector)?
- Are daily logs structured well enough for future embedding and chunking?
- Is the reflection JSONL log useful for evaluation (Phase 9)?
- Are there structural decisions in Phase 2 that will create friction in later phases?

### 3. Produce structured output

Format your review as follows. This exact format is required -- the operator will copy-paste it into Claude Code for evaluation.

```
## PHASE 2 REVIEW: pureMind Context Persistence & Hooks

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

### Phase 3 Readiness Score
[X/10] -- [one sentence justification]

### Missing from Phase 2
[list anything the PRD specified for Phase 2 that was not delivered]
```

## Constraints

- **DO NOT modify any files.** This is a read-only review.
- **DO NOT create branches, PRs, or issues.** Output is text only.
- Be specific. "Improve error handling" is not actionable. "Add a try/except around the subprocess.run at line 47 of daily_reflect.py that catches FileNotFoundError when claude CLI is missing and logs to stderr" is.
- Reference specific files and line numbers where relevant.
- Assume the reviewer (the operator) is deeply technical. No need to explain basic concepts.
- The project is for a real company (PureTensor, Inc.), not a hobby. Treat it accordingly.
- The Ray cluster (160 CPUs, 2 GPUs, 200 GbE) is the compute backbone for Phases 3, 7, and 9. Note any Phase 2 decisions that help or hinder distributed processing later.
- The hook scripts live in TWO repos: `tensor-scripts` (hooks) and `second-brain` (vault + daily_reflect.py). Review both.
