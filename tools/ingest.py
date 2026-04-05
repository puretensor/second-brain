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
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from datetime import datetime, timezone
from pathlib import Path

VAULT_ROOT = Path.home() / "pureMind"
KNOWLEDGE_DIR = VAULT_ROOT / "knowledge"
TOOLS_DIR = Path(__file__).parent
INDEX_SCRIPT = TOOLS_DIR / "index.py"

# Maximum extracted text size (1MB) to prevent index bloat
MAX_TEXT_BYTES = 1_000_000
MAX_PDF_PAGES = 200
PDF_TIMEOUT_SECONDS = 120

# Import sanitize after path setup
_TOOLS_PARENT = str(Path(__file__).resolve().parent.parent)
if _TOOLS_PARENT not in sys.path:
    sys.path.insert(0, _TOOLS_PARENT)
from tools.sanitize import sanitize_content


def _slugify(title: str, max_len: int = 60) -> str:
    """Convert a title to a filesystem-safe slug."""
    slug = title.lower().strip()
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'[\s]+', '-', slug)
    slug = slug.strip('-')[:max_len]
    return slug or "untitled"


def _yaml_scalar(value: str) -> str:
    """Safely format a string as a YAML scalar value.

    B-01 fix: prevents YAML injection from titles with quotes, colons,
    or other special characters.
    """
    if not value:
        return '""'
    needs_quoting = any(c in value for c in ':{}[]&*?|>!%@`#,\n\r\t"') \
        or value.startswith(('-', ' ', "'")) \
        or value.endswith(' ') \
        or value.lower() in ('true', 'false', 'null', 'yes', 'no', 'on', 'off')
    if needs_quoting:
        escaped = value.replace("'", "''")
        return f"'{escaped}'"
    return value


def _safe_category(category: str) -> str:
    """Validate and sanitize category to prevent path traversal.

    B-02 fix: rejects categories that would resolve outside knowledge/.
    """
    safe = re.sub(r'[^a-z0-9_-]', '', category.lower().strip())
    if not safe:
        safe = "research"
    resolved = (KNOWLEDGE_DIR / safe).resolve()
    if not str(resolved).startswith(str(KNOWLEDGE_DIR.resolve())):
        raise ValueError(f"Invalid category: '{category}' resolves outside knowledge/")
    return safe


def _unique_path(directory: Path, slug: str, ext: str = ".md") -> Path:
    """Find a unique file path, appending -2, -3 etc. on collision.

    Bounded to 100 attempts to prevent infinite loops.
    """
    candidate = directory / f"{slug}{ext}"
    if not candidate.exists():
        return candidate
    for counter in range(2, 102):
        candidate = directory / f"{slug}-{counter}{ext}"
        if not candidate.exists():
            return candidate
    raise ValueError(f"Too many collisions for slug '{slug}' (checked up to -101)")


def _extract_pdf_inner(filepath: Path) -> str:
    """Inner PDF extraction (called within timeout wrapper)."""
    text = ""

    try:
        import pdfplumber
        try:
            text_parts = []
            with pdfplumber.open(str(filepath)) as pdf:
                pages = pdf.pages[:MAX_PDF_PAGES]
                if len(pdf.pages) > MAX_PDF_PAGES:
                    print(f"WARNING: PDF has {len(pdf.pages)} pages, "
                          f"capping at {MAX_PDF_PAGES}", file=sys.stderr)
                for page in pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
            text = "\n\n".join(text_parts)
        except Exception as e:
            raise RuntimeError(
                f"PDF parse failed ({filepath.name}): {e}. "
                f"The file may be corrupted or password-protected.")
    except ImportError:
        try:
            import fitz  # PyMuPDF
            try:
                doc = fitz.open(str(filepath))
                pages = list(doc)[:MAX_PDF_PAGES]
                text_parts = [page.get_text() for page in pages]
                doc.close()
                text = "\n\n".join(text_parts)
            except Exception as e:
                raise RuntimeError(
                    f"PDF parse failed ({filepath.name}): {e}. "
                    f"The file may be corrupted or password-protected.")
        except ImportError:
            raise RuntimeError(
                "No PDF parser available. Install: pip install pdfplumber "
                "or pip install PyMuPDF")

    if not text.strip():
        raise ValueError(
            f"No text extracted from {filepath.name}. "
            f"This may be a scanned/image-only PDF that requires OCR.")

    return text


def _extract_pdf(filepath: Path) -> str:
    """Extract text from a PDF with timeout and page limit.

    B-03 fix: catches malformed PDFs, detects scanned/image-only PDFs.
    Phase 8: 120s timeout via ThreadPoolExecutor, 200-page cap.
    """
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_extract_pdf_inner, filepath)
        try:
            return future.result(timeout=PDF_TIMEOUT_SECONDS)
        except FuturesTimeout:
            raise RuntimeError(
                f"PDF extraction timed out after {PDF_TIMEOUT_SECONDS}s "
                f"for {filepath.name}. The file may be too large or complex.")


def _read_text_file(filepath: Path) -> str:
    """Read a text file with encoding fallback.

    B-03 fix: tries UTF-8 first, then Latin-1 (covers most Western encodings).
    """
    try:
        return filepath.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            return filepath.read_text(encoding="latin-1")
        except UnicodeDecodeError:
            raise ValueError(
                f"Cannot decode {filepath.name} as UTF-8 or Latin-1. "
                f"Convert to UTF-8 first.")


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
        return _read_text_file(filepath), "markdown"
    elif suffix in (".txt", ".text", ".rst", ".org"):
        return _read_text_file(filepath), "text"
    else:
        try:
            return _read_text_file(filepath), "text"
        except ValueError:
            raise ValueError(
                f"Cannot read {filepath.name} as text. "
                f"Supported formats: .pdf, .md, .txt")


def _build_frontmatter(title: str, source: str, source_url: str,
                        category: str, tags: list[str],
                        detected_type: str) -> str:
    """Generate YAML frontmatter for the ingested document.

    B-01 fix: uses _yaml_scalar() to safely escape all string values.
    I-01 fix: marks stdin/URL content as untrusted for RAG safety.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    lines = ["---"]
    lines.append(f"title: {_yaml_scalar(title)}")
    lines.append(f"date: {today}")
    if source_url:
        lines.append(f"source: {_yaml_scalar(source_url)}")
    elif source and source != "--stdin":
        lines.append(f"source_file: {_yaml_scalar(source)}")
    lines.append(f"ingested: {now}")
    lines.append(f"category: {category}")
    lines.append(f"source_type: {detected_type}")
    if tags:
        safe_tags = [_yaml_scalar(t) for t in tags]
        lines.append(f"tags: [{', '.join(safe_tags)}]")
    lines.append("ingested_by: pureMind")
    # I-01: mark external/untrusted content for RAG safety
    if detected_type == "stdin" or source_url:
        lines.append("untrusted_source: true")
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

    # B-02: validate category before any file operations
    category = _safe_category(category)

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

    # Sanitize ingested content to strip injection patterns before vault storage
    # This prevents indirect injection via ingested documents entering RAG context
    stripped = sanitize_content(stripped, max_chars=MAX_TEXT_BYTES)

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
