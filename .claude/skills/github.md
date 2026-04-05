---
name: github
description: List repos, PRs, issues and post comments via the pureMind GitHub integration
---

# GitHub Integration

Read repos, PRs, and issues. Comment on PRs/issues. Create issues. No merge, push, or close.

## Available Operations

```bash
# List repos
python3 ~/pureMind/.claude/integrations/github_integration.py list_repos

# List open PRs
python3 ~/pureMind/.claude/integrations/github_integration.py list_prs nexus --state open

# Get PR details
python3 ~/pureMind/.claude/integrations/github_integration.py get_pr nexus 42

# List issues
python3 ~/pureMind/.claude/integrations/github_integration.py list_issues nexus

# Get issue details
python3 ~/pureMind/.claude/integrations/github_integration.py get_issue nexus 10

# Comment on a PR
python3 ~/pureMind/.claude/integrations/github_integration.py comment_pr nexus 42 --body "Looks good, approved"

# Comment on an issue
python3 ~/pureMind/.claude/integrations/github_integration.py comment_issue nexus 10 --body "Investigating"

# Create a new issue
python3 ~/pureMind/.claude/integrations/github_integration.py create_issue nexus --title "Bug: X fails" --body "Steps to reproduce..."
```

## Constraints

- **No merge, push, close, or delete.** Read + comment + create issues only.
- All repos are under the `puretensor` org.
- All operations are logged to the pm_audit table.
