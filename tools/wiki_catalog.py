#!/usr/bin/env python3
"""pureMind wiki catalog -- regenerate knowledge/index.md from page inventory.

Walks knowledge/ recursively, groups pages by directory, and generates
a navigable index with wikilinks, summaries, and migration stats.

Usage:
    python3 wiki_catalog.py              # Regenerate index.md
    python3 wiki_catalog.py --dry-run    # Print to stdout
    python3 wiki_catalog.py --json       # JSON page inventory
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

_TOOLS_PARENT = str(Path(__file__).resolve().parent.parent)
if _TOOLS_PARENT not in sys.path:
    sys.path.insert(0, _TOOLS_PARENT)
from tools.wiki_helpers import (
    KNOWLEDGE_DIR, SECTION_DISPLAY, SECTION_ORDER, VAULT_ROOT,
    classify_frontmatter, extract_first_summary, find_wiki_pages,
    get_empty_sections, parse_frontmatter,
)

INDEX_FILE = KNOWLEDGE_DIR / "index.md"

HEADER = """# pureMind Wiki

Navigation entrypoint for the knowledge base. Pages here are canonical wiki content -- curated, cross-linked, and kept current.

## How to Use

- Browse by section below, or search with `/puremind-search`
- Each page has YAML frontmatter with `page_type`, `status`, and `source_refs`
- Cross-link pages with `[[wikilinks]]`
- New pages should use the `templates/wiki-page.md` template

## Pages by Section
"""


def _section_display(name: str) -> str:
    return SECTION_DISPLAY.get(name, name.title())


def _build_page_entry(page: Path, fm: dict, body: str) -> tuple[str, str, str]:
    """Returns (basename, title, summary) for a page."""
    basename = page.stem
    title = fm.get("title", "") if fm else ""
    if not title:
        # Try first heading
        for line in body.splitlines():
            line = line.strip()
            if line.startswith("# "):
                title = line[2:].strip()
                break
    if not title:
        title = basename.replace("-", " ").replace("_", " ").title()

    summary = extract_first_summary(body)
    if not summary:
        summary = title

    return basename, title, summary


def catalog(dry_run: bool = False, as_json: bool = False) -> str:
    """Build the catalog and return output."""
    pages = find_wiki_pages()

    # Collect page data
    sections = defaultdict(list)
    page_records = []
    stats = {"wiki": 0, "ingest": 0, "bare": 0}

    for page in pages:
        fm, body = parse_frontmatter(page)
        fm_type = classify_frontmatter(fm)
        stats[fm_type] = stats.get(fm_type, 0) + 1

        basename, title, summary = _build_page_entry(page, fm, body)
        section = page.parent.name if page.parent != KNOWLEDGE_DIR else "root"
        sections[section].append((basename, summary))

        page_records.append({
            "path": str(page.relative_to(VAULT_ROOT)),
            "basename": basename,
            "section": section,
            "title": title,
            "summary": summary,
            "frontmatter_type": fm_type,
            "has_wiki_frontmatter": fm_type == "wiki",
        })

    total = len(pages)

    if as_json:
        return json.dumps({
            "pages": page_records,
            "stats": {
                "total": total,
                "wiki_frontmatter": stats["wiki"],
                "ingest_frontmatter": stats["ingest"],
                "bare": stats["bare"],
            },
        }, indent=2)

    # Build markdown output
    lines = [HEADER]

    # Determine section order: known sections first, then unknown alphabetically
    empty_sections = get_empty_sections()
    all_sections = list(dict.fromkeys(
        SECTION_ORDER +
        sorted(s for s in sections if s not in SECTION_ORDER) +
        sorted(s for s in empty_sections if s not in SECTION_ORDER)
    ))

    for section in all_sections:
        display = _section_display(section)
        lines.append(f"### {display}\n")

        page_list = sections.get(section, [])
        if page_list:
            for basename, summary in sorted(page_list):
                lines.append(f"- [[{basename}]] -- {summary}")
            lines.append("")
        else:
            lines.append("*No pages yet.*\n")

    # Footer (no timestamp -- deterministic output)
    lines.append("---\n")
    lines.append(
        f"**Catalog:** {total} pages "
        f"({stats['wiki']} wiki, {stats['ingest']} ingest, {stats['bare']} bare).\n"
    )

    output = "\n".join(lines).rstrip("\n") + "\n"

    if dry_run:
        # Print without extra newline so stdout matches file content exactly
        sys.stdout.write(output)
        return None

    INDEX_FILE.write_text(output, encoding="utf-8")
    return f"Regenerated {INDEX_FILE.relative_to(VAULT_ROOT)} ({total} pages)"


def main():
    parser = argparse.ArgumentParser(
        description="Regenerate knowledge/index.md from page inventory")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print to stdout instead of writing")
    parser.add_argument("--json", action="store_true",
                        help="JSON page inventory")

    args = parser.parse_args()

    try:
        result = catalog(dry_run=args.dry_run, as_json=args.json)
        if result is not None:
            print(result)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
