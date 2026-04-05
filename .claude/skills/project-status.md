---
name: project-status
description: Generate a project status report from vault, daily logs, and GitHub
---

# Project Status

Produce a status summary for a named project by combining vault knowledge, recent daily log activity, GitHub PRs/issues, and pending items.

## Steps

1. **Read project context:**
```bash
cat ~/pureMind/projects/<project-name>/README.md
```

2. **Search vault for project knowledge:**
```bash
python3 ~/pureMind/tools/search.py "<project-name>" --file-filter projects/<project-name>/ --limit 5
```

3. **Search daily logs for recent activity:**
```bash
python3 ~/pureMind/tools/search.py "<project-name>" --file-filter daily-logs/ --limit 5
```

4. **Check GitHub PRs and issues** (map project to repo name):
```bash
python3 ~/pureMind/.claude/integrations/github_integration.py list_prs <repo> --state open
python3 ~/pureMind/.claude/integrations/github_integration.py list_issues <repo> --state open
```

5. **Check pending items:**
```bash
cat ~/pureMind/memory/pending.md
```
Filter for items related to the project.

## Output Format

```markdown
# Project Status: <Name>

## Current Phase
<phase and status from project README>

## Recent Activity (last 7 days)
- <key actions from daily logs>

## Open PRs
- <PR list or "None">

## Open Issues
- <issue list or "None">

## Pending Items
- <filtered pending items>

## Blockers
- <any blockers identified>
```

## Project-to-Repo Mapping

| Project | GitHub Repo | Notes |
|---|---|---|
| puremind | second-brain | This vault |
| pureclaw | PureClaw | Agentic AI platform |
| immune-system | macrophage | Self-healing fleet agent |

## Constraints

- Read-only. This skill does not modify any files.
- All GitHub and search operations are logged to pm_audit.
