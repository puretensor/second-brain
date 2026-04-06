"""Shared helpers for wiki tools (catalog, lint).

Not a CLI tool. Imported by wiki_catalog.py and wiki_lint.py.
"""

import re
import sys
from datetime import date
from pathlib import Path

import yaml

VAULT_ROOT = Path.home() / "pureMind"
KNOWLEDGE_DIR = VAULT_ROOT / "knowledge"

WIKI_REQUIRED_FIELDS = ["title", "page_type", "status", "source_refs", "updated"]
WIKI_PAGE_TYPES = ["entity", "concept", "overview", "comparison", "project",
                    "source-summary"]
WIKI_STATUSES = ["seed", "active", "needs-review"]

SECTION_ORDER = ["puretensor", "contacts", "research", "drafts", "diagrams",
                 "archive"]
SECTION_DISPLAY = {"puretensor": "PureTensor"}

META_FILES = {"index.md", "log.md"}


def find_wiki_pages(knowledge_dir: Path = KNOWLEDGE_DIR) -> list[Path]:
    """Find all content .md pages under knowledge/, excluding meta files."""
    pages = []
    for p in sorted(knowledge_dir.rglob("*.md")):
        if p.name in META_FILES:
            continue
        if p.name == ".gitkeep":
            continue
        pages.append(p)
    return pages


def parse_frontmatter(filepath: Path) -> tuple[dict, str]:
    """Parse YAML frontmatter from a markdown file.

    Returns (frontmatter_dict, body_text). If no frontmatter, returns ({}, full_text).
    Coerces datetime.date values to strings.
    """
    text = filepath.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}, text

    end = text.find("---", 3)
    if end == -1:
        return {}, text

    yaml_block = text[3:end].strip()
    body = text[end + 3:].lstrip("\n")

    try:
        fm = yaml.safe_load(yaml_block)
    except yaml.YAMLError as e:
        print(f"WARNING: Malformed YAML in {filepath.name}: {e}", file=sys.stderr)
        return {}, text

    if not isinstance(fm, dict):
        return {}, text

    # Coerce date objects to strings (safe_load auto-converts YYYY-MM-DD)
    for k, v in fm.items():
        if isinstance(v, date):
            fm[k] = v.isoformat()

    return fm, body


def extract_wikilinks(text: str) -> list[str]:
    """Extract [[wikilink]] targets from text, ignoring code blocks."""
    # Strip fenced code blocks
    stripped = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    # Strip inline code
    stripped = re.sub(r'`[^`]+`', '', stripped)
    # Match [[target]] and [[target|display]]
    matches = re.findall(r'\[\[([^\]|]+?)(?:\|[^\]]+?)?\]\]', stripped)
    # Deduplicate preserving order
    seen = set()
    result = []
    for m in matches:
        key = m.strip().lower()
        if key not in seen:
            seen.add(key)
            result.append(m.strip())
    return result


def _clean_summary(line: str) -> str:
    """Strip markdown list markers, bold, and formatting from a summary line."""
    # Strip list markers (-, *, numbered)
    line = re.sub(r'^[-*]\s+', '', line)
    line = re.sub(r'^\d+\.\s+', '', line)
    # Strip bold markers
    line = line.replace('**', '')
    return line.strip()


def extract_first_summary(body: str) -> str:
    """Extract the first summary line from page body.

    Prefers > blockquote lines, falls back to first non-heading paragraph line.
    Cleans markdown formatting from the result.
    """
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("> "):
            summary = _clean_summary(line[2:])
            return summary[:120] if len(summary) > 120 else summary

    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            continue
        if line.startswith("---"):
            continue
        if line.startswith("*No "):
            continue
        summary = _clean_summary(line)
        if not summary:
            continue
        return summary[:120] if len(summary) > 120 else summary

    return ""


def build_page_index(knowledge_dir: Path = KNOWLEDGE_DIR) -> dict[str, Path]:
    """Map lowercase basenames and aliases to Paths for wikilink resolution.

    Includes meta files (index, log) so [[index]] doesn't flag as broken.
    Reads aliases from frontmatter to support alias-based wikilinks.
    """
    index = {}
    for p in sorted(knowledge_dir.rglob("*.md")):
        if p.name == ".gitkeep":
            continue
        key = p.stem.lower()
        if key in index:
            print(f"WARNING: Name collision: {key} -> {index[key]} and {p}",
                  file=sys.stderr)
        index[key] = p

        # Also index aliases from frontmatter
        if p.name not in META_FILES:
            fm, _ = parse_frontmatter(p)
            aliases = fm.get("aliases", [])
            if isinstance(aliases, list):
                for alias in aliases:
                    alias_key = str(alias).lower().strip()
                    if alias_key and alias_key not in index:
                        index[alias_key] = p
    return index


def classify_frontmatter(fm: dict) -> str:
    """Classify frontmatter type: 'wiki', 'ingest', or 'bare'."""
    if not fm:
        return "bare"
    has_wiki = any(f in fm for f in ["page_type", "status", "source_refs"])
    if has_wiki:
        return "wiki"
    if any(f in fm for f in ["ingested_by", "ingested", "source_type"]):
        return "ingest"
    return "bare"


def get_empty_sections(knowledge_dir: Path = KNOWLEDGE_DIR) -> list[str]:
    """Find subdirectories that exist but have no .md content pages."""
    empty = []
    for d in sorted(knowledge_dir.iterdir()):
        if not d.is_dir():
            continue
        md_files = [f for f in d.rglob("*.md") if f.name != ".gitkeep"]
        if not md_files:
            empty.append(d.name)
    return empty
