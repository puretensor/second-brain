#!/usr/bin/env python3
"""pureMind wiki lint -- check knowledge pages for convention compliance.

Validates frontmatter, wikilinks, orphan pages, and index coverage.

Usage:
    python3 wiki_lint.py                                     # Full lint
    python3 wiki_lint.py --json                              # JSON output
    python3 wiki_lint.py --file knowledge/puretensor/x.md    # Single file
"""

import argparse
import json
import re
import sys
from pathlib import Path

_TOOLS_PARENT = str(Path(__file__).resolve().parent.parent)
if _TOOLS_PARENT not in sys.path:
    sys.path.insert(0, _TOOLS_PARENT)
from tools.wiki_helpers import (
    KNOWLEDGE_DIR, VAULT_ROOT, WIKI_PAGE_TYPES, WIKI_REQUIRED_FIELDS,
    WIKI_STATUSES, build_page_index, extract_wikilinks, find_wiki_pages,
    parse_frontmatter,
)

INDEX_FILE = KNOWLEDGE_DIR / "index.md"


def _lint_page(filepath: Path, fm: dict, body: str,
               page_index: dict) -> list[dict]:
    """Run per-page checks. Returns list of finding dicts."""
    findings = []
    rel = str(filepath.relative_to(VAULT_ROOT))

    def add(check, severity, message):
        findings.append({
            "file": rel,
            "check": check,
            "severity": severity,
            "message": message,
        })

    # No frontmatter at all -> one error, skip field-level checks
    if not fm:
        add("no-frontmatter", "error", "No YAML frontmatter found")
    else:
        # Missing required wiki fields
        for field in WIKI_REQUIRED_FIELDS:
            if field not in fm:
                add("missing-field", "error", field)

        # Validate enum values (only if field exists)
        if "page_type" in fm and fm["page_type"] not in WIKI_PAGE_TYPES:
            add("invalid-page-type", "error",
                f"'{fm['page_type']}' not in {WIKI_PAGE_TYPES}")

        if "status" in fm and fm["status"] not in WIKI_STATUSES:
            add("invalid-status", "error",
                f"'{fm['status']}' not in {WIKI_STATUSES}")

        # Validate date format
        if "updated" in fm:
            val = str(fm["updated"])
            if not re.match(r'^\d{4}-\d{2}-\d{2}$', val):
                add("invalid-date", "error",
                    f"updated '{val}' is not YYYY-MM-DD")

        # Empty source_refs
        if "source_refs" in fm:
            refs = fm["source_refs"]
            if isinstance(refs, list) and len(refs) == 0:
                add("empty-source-refs", "warning",
                    "source_refs is empty")

        # Stale page
        if fm.get("status") == "needs-review":
            add("stale-page", "warning", "Page status is needs-review")

    # Wikilinks in body
    links = extract_wikilinks(body)
    if not links:
        add("no-wikilinks", "info", "Page body contains no wikilinks")
    else:
        for link in links:
            if link.lower() not in page_index:
                add("broken-wikilink", "error",
                    f"[[{link}]] does not resolve to any page")

    return findings


def _cross_page_checks(pages: list[Path], page_index: dict) -> list[dict]:
    """Run cross-page checks: orphans and index coverage."""
    findings = []

    # Build inbound link map (who links to whom) excluding index.md and log.md
    inbound = {p.stem.lower(): set() for p in pages}
    for p in pages:
        _, body = parse_frontmatter(p)
        links = extract_wikilinks(body)
        for link in links:
            key = link.lower()
            if key in inbound:
                inbound[key].add(p.stem.lower())

    # Load index.md wikilinks
    index_links = set()
    if INDEX_FILE.exists():
        index_text = INDEX_FILE.read_text(encoding="utf-8")
        index_links = {l.lower() for l in extract_wikilinks(index_text)}

    for page in pages:
        rel = str(page.relative_to(VAULT_ROOT))
        basename = page.stem.lower()

        # Orphan: no inbound links from other content pages
        if not inbound.get(basename):
            findings.append({
                "file": rel,
                "check": "orphan-page",
                "severity": "warning",
                "message": "No inbound wikilinks from other content pages",
            })

        # Not in index
        if basename not in index_links:
            findings.append({
                "file": rel,
                "check": "not-in-index",
                "severity": "warning",
                "message": "Page not referenced in knowledge/index.md",
            })

    return findings


def lint(target_file: str = "", as_json: bool = False) -> str:
    """Run lint checks and return formatted output."""
    page_index = build_page_index()

    if target_file:
        filepath = Path(target_file).resolve()
        if not filepath.exists():
            raise FileNotFoundError(f"File not found: {filepath}")
        pages = [filepath]
    else:
        pages = find_wiki_pages()

    # Per-page checks
    all_findings = []
    for page in pages:
        fm, body = parse_frontmatter(page)
        all_findings.extend(_lint_page(page, fm, body, page_index))

    # Cross-page checks (only in full mode)
    if not target_file:
        all_findings.extend(_cross_page_checks(pages, page_index))

    # Tally
    counts = {"error": 0, "warning": 0, "info": 0}
    for f in all_findings:
        counts[f["severity"]] += 1

    if as_json:
        return json.dumps({
            "findings": all_findings,
            "summary": {
                "error": counts["error"],
                "warning": counts["warning"],
                "info": counts["info"],
                "pages_checked": len(pages),
            },
        }, indent=2)

    # Human-readable output
    if not all_findings:
        return f"No findings across {len(pages)} pages."

    lines = []
    # Group by file
    by_file = {}
    for f in all_findings:
        by_file.setdefault(f["file"], []).append(f)

    for filepath in sorted(by_file):
        lines.append(filepath)
        for f in by_file[filepath]:
            sev = f["severity"].upper()
            lines.append(f"  {sev:7s} {f['check']}: {f['message']}")
        lines.append("")

    lines.append("---")
    lines.append(
        f"{counts['error']} errors, {counts['warning']} warnings, "
        f"{counts['info']} info across {len(pages)} pages"
    )

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Check knowledge pages for wiki convention compliance")
    parser.add_argument("--json", action="store_true",
                        help="JSON output")
    parser.add_argument("--file", default="",
                        help="Lint a single file")

    args = parser.parse_args()

    try:
        result = lint(target_file=args.file, as_json=args.json)
        print(result)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
