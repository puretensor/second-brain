# pureMind Vault

This is the pureMind second brain vault. When working in this directory:

1. Always load memory/soul.md, memory/user.md, memory/memory.md at session start.
2. Every file change is auto-committed to Git via PostToolUse hook.
3. Never store credentials, passwords, API keys, or tokens in this vault. They live in ~/.claude/ memory only.
4. memory.md must stay under 8K tokens (~5KB text). Curate aggressively.
5. Daily logs go in daily-logs/YYYY-MM-DD.md.
6. Knowledge files go in knowledge/ with clean markdown and no credential data.
7. Project context goes in projects/{name}/README.md.
8. Templates in templates/ are style guides, not executable code.

## Credential Safety
This vault is a Git repository. Everything committed becomes permanent history. The .gitignore blocks common patterns, but the primary defence is discipline: never write credentials here. Reference them by pointer ("see ~/.claude/ memory") instead.

## Memory Hierarchy (MemGPT-inspired)
- **Register:** Live conversation context (ephemeral)
- **RAM:** memory/memory.md (always loaded, <8K tokens)
- **Disk:** daily-logs/, knowledge/, projects/ (searchable, not always loaded)
