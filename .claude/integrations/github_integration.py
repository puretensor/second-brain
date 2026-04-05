#!/usr/bin/env python3
"""pureMind GitHub integration -- permission-enforced wrapper over gh CLI.

Read: repos, PRs, issues. Write: comments on PRs/issues, create issues.
Blocked: merge, push, close, delete.

Usage:
    python3 github_integration.py list_repos
    python3 github_integration.py list_prs nexus [--state open]
    python3 github_integration.py get_pr nexus 42
    python3 github_integration.py list_issues nexus
    python3 github_integration.py get_issue nexus 10
    python3 github_integration.py comment_pr nexus 42 --body "Looks good"
    python3 github_integration.py comment_issue nexus 10 --body "Investigating"
    python3 github_integration.py create_issue nexus --title "Bug" --body "Description"
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from base import audited, deny

INTEGRATION = "github"
ORG = "puretensor"

BLOCKED_OPS = {"merge", "push", "close", "delete"}

# A-01 fix: gh subcommands that are never allowed through the wrapper
_GH_BLOCKED_SUBCOMMANDS = {"merge", "close", "delete", "push"}


def _gh(args: list[str]) -> str:
    """Run a gh CLI command and return stdout.

    A-01 fix: validates that no blocked subcommands appear in args.
    """
    for blocked in _GH_BLOCKED_SUBCOMMANDS:
        if blocked in args:
            deny(INTEGRATION, blocked, {"args": " ".join(args[:5])})
    result = subprocess.run(["gh"] + args, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"gh error: {result.stderr[:300]}")
    return result.stdout


@audited(INTEGRATION)
def list_repos() -> str:
    """List all repos in the puretensor org."""
    # E-01 fix: raised limit from 50 to 100 (org has 57+ repos)
    return _gh(["repo", "list", ORG, "--limit", "100",
                "--json", "name,visibility,updatedAt,description"])


@audited(INTEGRATION)
def list_prs(repo: str, state: str = "open") -> str:
    """List PRs for a repo."""
    return _gh(["pr", "list", "-R", f"{ORG}/{repo}", "--state", state,
                "--json", "number,title,state,author,createdAt,url"])


@audited(INTEGRATION)
def get_pr(repo: str, number: int) -> str:
    """Get details of a specific PR."""
    return _gh(["pr", "view", "-R", f"{ORG}/{repo}", str(number),
                "--json", "number,title,state,body,author,createdAt,files,comments"])


@audited(INTEGRATION)
def list_issues(repo: str, state: str = "open") -> str:
    """List issues for a repo."""
    return _gh(["issue", "list", "-R", f"{ORG}/{repo}", "--state", state,
                "--json", "number,title,state,author,createdAt,url,labels"])


@audited(INTEGRATION)
def get_issue(repo: str, number: int) -> str:
    """Get details of a specific issue."""
    return _gh(["issue", "view", "-R", f"{ORG}/{repo}", str(number),
                "--json", "number,title,state,body,author,createdAt,comments,labels"])


@audited(INTEGRATION)
def comment_pr(repo: str, number: int, body: str) -> str:
    """Add a comment to a PR."""
    _gh(["pr", "comment", "-R", f"{ORG}/{repo}", str(number), "--body", body])
    return f"Comment posted on {ORG}/{repo}#{number}"


@audited(INTEGRATION)
def comment_issue(repo: str, number: int, body: str) -> str:
    """Add a comment to an issue."""
    _gh(["issue", "comment", "-R", f"{ORG}/{repo}", str(number), "--body", body])
    return f"Comment posted on {ORG}/{repo}#{number}"


@audited(INTEGRATION)
def create_issue(repo: str, title: str, body: str = "") -> str:
    """Create a new issue."""
    args = ["issue", "create", "-R", f"{ORG}/{repo}", "--title", title]
    if body:
        args.extend(["--body", body])
    output = _gh(args)
    return f"Issue created: {output.strip()}"


def main():
    parser = argparse.ArgumentParser(description="pureMind GitHub integration")
    parser.add_argument("command", choices=[
        "list_repos", "list_prs", "get_pr", "list_issues", "get_issue",
        "comment_pr", "comment_issue", "create_issue",
        "merge", "push", "close", "delete",  # blocked
    ])
    parser.add_argument("repo", nargs="?", default="")
    parser.add_argument("number", nargs="?", type=int, default=0)
    parser.add_argument("--state", default="open")
    parser.add_argument("--title", default="")
    parser.add_argument("--body", default="")
    parser.add_argument("--json", action="store_true",
                        help="Output as JSON (already default for list/get operations)")

    args = parser.parse_args()

    try:
        if args.command in BLOCKED_OPS:
            deny(INTEGRATION, args.command, {"repo": args.repo})

        if args.command == "list_repos":
            print(list_repos())

        elif args.command == "list_prs":
            if not args.repo:
                print("ERROR: repo name required", file=sys.stderr); sys.exit(1)
            print(list_prs(repo=args.repo, state=args.state))

        elif args.command == "get_pr":
            if not args.repo or not args.number:
                print("ERROR: repo and PR number required", file=sys.stderr); sys.exit(1)
            print(get_pr(repo=args.repo, number=args.number))

        elif args.command == "list_issues":
            if not args.repo:
                print("ERROR: repo name required", file=sys.stderr); sys.exit(1)
            print(list_issues(repo=args.repo, state=args.state))

        elif args.command == "get_issue":
            if not args.repo or not args.number:
                print("ERROR: repo and issue number required", file=sys.stderr); sys.exit(1)
            print(get_issue(repo=args.repo, number=args.number))

        elif args.command == "comment_pr":
            if not args.repo or not args.number or not args.body:
                print("ERROR: repo, number, and --body required", file=sys.stderr); sys.exit(1)
            print(comment_pr(repo=args.repo, number=args.number, body=args.body))

        elif args.command == "comment_issue":
            if not args.repo or not args.number or not args.body:
                print("ERROR: repo, number, and --body required", file=sys.stderr); sys.exit(1)
            print(comment_issue(repo=args.repo, number=args.number, body=args.body))

        elif args.command == "create_issue":
            if not args.repo or not args.title:
                print("ERROR: repo and --title required", file=sys.stderr); sys.exit(1)
            print(create_issue(repo=args.repo, title=args.title, body=args.body))

    except PermissionError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
