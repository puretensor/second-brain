#!/usr/bin/env python3
"""pureMind content ingestion tool -- ingest URLs, PDFs, and documents into the vault.

Downloads or reads external content, converts to markdown, adds provenance
frontmatter, saves to the vault knowledge directory, and triggers incremental
indexing.

Usage:
    python3 ingest.py document.pdf --title "Paper Title"
    python3 ingest.py article.md --category contacts --tags nvidia,inception
    python3 ingest.py --from-stdin --title "Article" --source-url https://example.com
    echo "content" | python3 ingest.py --from-stdin --title "Piped Content"
"""

import argparse
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

VAULT_ROOT = Path.home() / "pureMind"
KNOWLEDGE_DIR = VAULT_ROOT / "knowledge"
TOOLS_DIR = Path(__file__).parent
INDEX_SCRIPT = TOOLS_DIR / "index.py"

# Maximum extracted text size (1MB) to prevent index bloat
MAX_TEXT_BYTES = 1_000_000


def _slugify(title: str, max_len: int = 60) -> str:
    """Convert a title to a filesystem-safe slug."""
    slug = title.lower().strip()
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'[\s]+', '-', slug)
    slug = slug.strip('-')[:max_len]
    return slug or "untitled"


def _unique_path(directory: Path, slug: str, ext: str = ".md") -> Path:
    """Find a unique file path, appending -2, -3 etc. on collision."""
    candidate = directory / f"{slug}{ext}"
    if not candidate.exists():
        return candidate
    counter = 2
    while True:
        candidate = directory / f"{slug}-{counter}{ext}"
        if not candidate.exists():
            return candidate
        counter += 1


def _extract_pdf(filepath: Path) -> str:
    """Extract text from a PDF file using pdfplumber (primary) or PyMuPDF (fallback)."""
    try:
        import pdfplumber
        text_parts = []
        with pdfplumber.open(str(filepath)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
        return "\n\n".join(text_parts)
    except ImportError:
        pass

    try:
        import fitz  # PyMuPDF
        doc = fitz.open(str(filepath))
        text_parts = [page.get_text() for page in doc]
        doc.close()
        return "\n\n".join(text_parts)
    except ImportError:
        raise RuntimeError(
            "No PDF parser available. Install: pip install pdfplumber "
            "or pip install PyMuPDF")


def _read_source(source: str, from_stdin: bool) -> tuple[str, str]:
    """Read content from source. Returns (content, detected_type).

    detected_type: 'pdf', 'markdown', 'text', 'stdin'
    """
    if from_stdin:
        content = sys.stdin.read()
        return content, "stdin"

    filepath = Path(source).expanduser().resolve()
    if not filepath.exists():
        raise FileNotFoundError(f"Source file not found: {filepath}")

    suffix = filepath.suffix.lower()

    if suffix == ".pdf":
        return _extract_pdf(filepath), "pdf"
    elif suffix in (".md", ".markdown"):
        return filepath.read_text(encoding="utf-8"), "markdown"
    elif suffix in (".txt", ".text", ".rst", ".org"):
        return filepath.read_text(encoding="utf-8"), "text"
    else:
        # Try reading as text
        try:
            return filepath.read_text(encoding="utf-8"), "text"
        except UnicodeDecodeError:
            raise ValueError(
                f"Cannot read {filepath.name} as text. "
                f"Supported formats: .pdf, .md, .txt")


def _build_frontmatter(title: str, source: str, source_url: str,
                        category: str, tags: list[str],
                        detected_type: str) -> str:
    """Generate YAML frontmatter for the ingested document."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    lines = ["---"]
    lines.append(f'title: "{title}"')
    lines.append(f"date: {today}")
    if source_url:
        lines.append(f"source: {source_url}")
    elif source and source != "--stdin":
        lines.append(f"source_file: {source}")
    lines.append(f"ingested: {now}")
    lines.append(f"category: {category}")
    lines.append(f"source_type: {detected_type}")
    if tags:
        lines.append(f"tags: [{', '.join(tags)}]")
    lines.append("ingested_by: pureMind")
    lines.append("---")
    return "\n".join(lines)


def _trigger_index():
    """Spawn incremental re-index in the background."""
    if INDEX_SCRIPT.exists():
        try:
            subprocess.Popen(
                ["python3", str(INDEX_SCRIPT), "--quiet"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass


def ingest(source: str, title: str, from_stdin: bool = False,
           source_url: str = "", category: str = "research",
           tags: list[str] = None) -> str:
    """Ingest content into the pureMind vault.

    Returns the vault path of the saved file.
    """
    tags = tags or []

    # Read content
    content, detected_type = _read_source(source, from_stdin)

    if not content or not content.strip():
        raise ValueError("Source content is empty.")

    # Size guard
    if len(content.encode("utf-8")) > MAX_TEXT_BYTES:
        raise ValueError(
            f"Extracted text is {len(content.encode('utf-8')):,} bytes "
            f"(limit: {MAX_TEXT_BYTES:,}). Trim the source or split into parts.")

    # Auto-detect title from content if not provided
    if not title:
        # Try first heading
        heading_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
        if heading_match:
            title = heading_match.group(1).strip()
        else:
            title = Path(source).stem if source else "untitled"

    # Build output
    frontmatter = _build_frontmatter(
        title=title, source=source, source_url=source_url,
        category=category, tags=tags, detected_type=detected_type)

    # Strip existing frontmatter from content if present
    stripped = content
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            stripped = content[end + 3:].lstrip("\n")

    output = f"{frontmatter}\n\n# {title}\n\n{stripped}"

    # Save to vault
    target_dir = KNOWLEDGE_DIR / category
    target_dir.mkdir(parents=True, exist_ok=True)

    slug = _slugify(title)
    target_path = _unique_path(target_dir, slug)
    target_path.write_text(output, encoding="utf-8")

    # Trigger incremental re-index
    _trigger_index()

    # Report
    vault_relative = target_path.relative_to(VAULT_ROOT)
    word_count = len(content.split())
    return (
        f"Ingested: {vault_relative}\n"
        f"  Title: {title}\n"
        f"  Type: {detected_type}\n"
        f"  Words: {word_count:,}\n"
        f"  Category: {category}\n"
        f"  Indexing triggered (incremental)")


def main():
    parser = argparse.ArgumentParser(
        description="pureMind content ingestion tool")
    parser.add_argument("source", nargs="?", default="",
                        help="File path to ingest")
    parser.add_argument("--title", "-t", default="",
                        help="Document title (auto-detected if omitted)")
    parser.add_argument("--source-url", default="",
                        help="Original URL for provenance tracking")
    parser.add_argument("--category", "-c", default="research",
                        help="Subdirectory under knowledge/ (default: research)")
    parser.add_argument("--tags", default="",
                        help="Comma-separated tags for frontmatter")
    parser.add_argument("--from-stdin", action="store_true",
                        help="Read content from stdin")

    args = parser.parse_args()

    if not args.source and not args.from_stdin:
        parser.error("Provide a source file path or use --from-stdin")

    if args.from_stdin and not args.title:
        parser.error("--title is required when using --from-stdin")

    tags = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else []

    try:
        result = ingest(
            source=args.source,
            title=args.title,
            from_stdin=args.from_stdin,
            source_url=args.source_url,
            category=args.category,
            tags=tags,
        )
        print(result)
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
