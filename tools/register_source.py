#!/usr/bin/env python3
"""pureMind source registration tool -- register immutable source manifests.

Registers external content as a source in the pureMind wiki layer.
Creates a manifest in sources/manifests/, optionally captures a text
snapshot in sources/snapshots/, and updates sources/index.md.

Usage:
    python3 register_source.py document.md --title "Article Title"
    python3 register_source.py paper.pdf --title "Paper Title"
    python3 register_source.py --from-stdin --title "Content" --source-url https://example.com
"""

import argparse
import hashlib
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

VAULT_ROOT = Path.home() / "pureMind"
SOURCES_DIR = VAULT_ROOT / "sources"
MANIFESTS_DIR = SOURCES_DIR / "manifests"
SNAPSHOTS_DIR = SOURCES_DIR / "snapshots"
INDEX_FILE = SOURCES_DIR / "index.md"
SENTINEL = "<!-- New entries appended above this line -->"

MAX_SNAPSHOT_BYTES = 1_000_000  # 1MB cap

# Import helpers from ingest.py
_TOOLS_PARENT = str(Path(__file__).resolve().parent.parent)
if _TOOLS_PARENT not in sys.path:
    sys.path.insert(0, _TOOLS_PARENT)
from tools.ingest import _slugify, _yaml_scalar, _unique_path, _read_text_file


def _generate_source_id(slug: str) -> str:
    """Generate source_id in format src-YYYYMMDD-slug."""
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"src-{today}-{slug}"


def _compute_sha256(filepath: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    with open(filepath, "rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def _detect_content_type(source: str, from_stdin: bool) -> str:
    """Detect content type from input mode and file extension."""
    if from_stdin:
        return "stdin"
    suffix = Path(source).suffix.lower()
    type_map = {
        ".pdf": "pdf",
        ".md": "markdown",
        ".markdown": "markdown",
        ".txt": "text",
        ".text": "text",
        ".rst": "text",
        ".org": "text",
        ".html": "html",
        ".htm": "html",
    }
    return type_map.get(suffix, "text")


def _sanitize_table_cell(value: str) -> str:
    """Escape a string for safe use in a markdown table cell."""
    value = re.sub(r'[\n\r]+', ' ', value)
    value = value.replace('|', '\\|')
    return value.strip()


def _build_manifest_frontmatter(source_id: str, title: str, origin_url: str,
                                 origin_path: str, captured_at: str,
                                 content_type: str, blob_sha256: str,
                                 untrusted_source: bool,
                                 snapshot_path: str) -> str:
    """Build YAML frontmatter for a source manifest."""
    lines = ["---"]
    lines.append(f"source_id: {source_id}")
    lines.append(f"title: {_yaml_scalar(title)}")
    lines.append(f"origin_url: {_yaml_scalar(origin_url)}")
    lines.append(f"origin_path: {_yaml_scalar(origin_path)}")
    lines.append(f"captured_at: {captured_at}")
    lines.append(f"content_type: {content_type}")
    lines.append(f"blob_sha256: {_yaml_scalar(blob_sha256)}")
    lines.append(f"untrusted_source: {'true' if untrusted_source else 'false'}")
    lines.append(f"snapshot_path: {_yaml_scalar(snapshot_path)}")
    lines.append("---")
    return "\n".join(lines)


def _build_manifest_body(title: str, description: str,
                          processing_note: str) -> str:
    """Build the markdown body of a manifest."""
    lines = [f"\n# {title}\n"]
    if description:
        lines.append(f"{description}\n")
    lines.append("## Processing Notes\n")
    lines.append(f"- {processing_note}\n")
    return "\n".join(lines)


def _save_snapshot(source_id: str, content: str) -> str:
    """Save a text snapshot. Returns vault-relative path."""
    snapshot_path = SNAPSHOTS_DIR / f"{source_id}.md"
    encoded = content.encode("utf-8")
    if len(encoded) > MAX_SNAPSHOT_BYTES:
        print(f"WARNING: Snapshot truncated at {MAX_SNAPSHOT_BYTES:,} bytes",
              file=sys.stderr)
        # Truncate by bytes, then decode safely to avoid splitting a multi-byte char
        truncated = encoded[:MAX_SNAPSHOT_BYTES].decode("utf-8", errors="ignore")
        content = truncated + \
            f"\n\n[...snapshot truncated at {MAX_SNAPSHOT_BYTES:,} bytes]"
    snapshot_path.write_text(content, encoding="utf-8")
    return str(snapshot_path.relative_to(VAULT_ROOT))


def _update_index(source_id: str, title: str, captured_date: str,
                   content_type: str, manifest_filename: str) -> None:
    """Append a row to sources/index.md above the sentinel."""
    safe_title = _sanitize_table_cell(title)
    manifest_link = f"[manifest](manifests/{manifest_filename})"
    row = f"| {source_id} | {safe_title} | {captured_date} | {content_type} | {manifest_link} |"

    text = INDEX_FILE.read_text(encoding="utf-8")
    if SENTINEL in text:
        text = text.replace(SENTINEL, f"{row}\n{SENTINEL}")
    else:
        print("WARNING: sentinel not found in sources/index.md, appending",
              file=sys.stderr)
        text = text.rstrip("\n") + f"\n{row}\n"
    INDEX_FILE.write_text(text, encoding="utf-8")


def register_source(source: str, title: str, from_stdin: bool = False,
                     source_url: str = "",
                     content_type_override: str = "", untrusted: bool = False,
                     description: str = "") -> str:
    """Register a source in the pureMind wiki layer.

    Returns a summary string of what was created.
    """
    for d in (MANIFESTS_DIR, SNAPSHOTS_DIR):
        if not d.exists():
            raise FileNotFoundError(
                f"{d} does not exist. Run Phase 1 scaffolding first.")
    if not INDEX_FILE.exists():
        raise FileNotFoundError(
            f"{INDEX_FILE} does not exist. Run Phase 1 scaffolding first.")

    content = ""
    filepath = None

    # Read content based on input mode
    if from_stdin:
        content = sys.stdin.read()
        if not content or not content.strip():
            raise ValueError("Stdin content is empty.")
    elif source:
        filepath = Path(source).expanduser().resolve()
        if not filepath.exists():
            raise FileNotFoundError(f"Source file not found: {filepath}")

    # Detect content type
    content_type = content_type_override or _detect_content_type(
        source, from_stdin)

    # For local text files, read content for snapshot
    if filepath and content_type != "pdf":
        content = _read_text_file(filepath)

    # Auto-detect title
    if not title:
        if filepath:
            title = filepath.stem.replace("-", " ").replace("_", " ").title()
        else:
            title = "untitled"

    # Generate source_id with collision resolution
    slug = _slugify(title)
    source_id_base = _generate_source_id(slug)
    manifest_path = _unique_path(MANIFESTS_DIR, source_id_base, ext=".md")
    source_id = manifest_path.stem

    # Compute SHA-256
    if filepath:
        sha256_hex = _compute_sha256(filepath)
    elif content:
        sha256_hex = hashlib.sha256(content.encode("utf-8")).hexdigest()
    else:
        sha256_hex = ""

    # Save snapshot (non-PDF only)
    snapshot_rel = ""
    if content_type != "pdf" and content:
        snapshot_rel = _save_snapshot(source_id, content)

    # Build manifest
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    origin_url_val = source_url
    origin_path_val = str(filepath) if filepath else ""
    untrusted_val = untrusted or from_stdin

    if from_stdin:
        processing_note = "Registered from stdin"
    elif content_type == "pdf":
        processing_note = f"PDF registered (manifest only, binary not in Git)"
    else:
        processing_note = f"Registered from local file: {filepath.name}"

    frontmatter = _build_manifest_frontmatter(
        source_id=source_id, title=title, origin_url=origin_url_val,
        origin_path=origin_path_val, captured_at=now,
        content_type=content_type, blob_sha256=sha256_hex,
        untrusted_source=untrusted_val, snapshot_path=snapshot_rel)

    body = _build_manifest_body(title, description, processing_note)
    manifest_path.write_text(frontmatter + body, encoding="utf-8")

    # Update index
    _update_index(source_id, title, today, content_type, manifest_path.name)

    return (
        f"Registered: {source_id}\n"
        f"  Title: {title}\n"
        f"  Type: {content_type}\n"
        f"  SHA-256: {sha256_hex[:16]}...\n"
        f"  Manifest: sources/manifests/{manifest_path.name}\n"
        + (f"  Snapshot: {snapshot_rel}\n" if snapshot_rel else
           "  Snapshot: none (binary)\n")
        + f"  Untrusted: {untrusted_val}")


def main():
    parser = argparse.ArgumentParser(
        description="pureMind source registration tool")
    parser.add_argument("source", nargs="?", default="",
                        help="File path to register")
    parser.add_argument("--title", "-t", default="",
                        help="Source title (auto-detected from filename if omitted)")
    parser.add_argument("--source-url", default="",
                        help="Original URL for provenance (metadata only)")
    parser.add_argument("--from-stdin", action="store_true",
                        help="Read content from stdin")
    parser.add_argument("--content-type", default="",
                        choices=["pdf", "markdown", "text", "html", "stdin"],
                        help="Override auto-detected content type")
    parser.add_argument("--untrusted", action="store_true",
                        help="Mark source as untrusted (auto for stdin/url)")
    parser.add_argument("--description", "-d", default="",
                        help="Brief description for manifest body")

    args = parser.parse_args()

    modes = sum([bool(args.source), args.from_stdin])
    if modes == 0:
        parser.error("Provide a source file or use --from-stdin")
    if modes > 1:
        parser.error("Use only one of: source file, --from-stdin")
    if args.from_stdin and not args.title:
        parser.error("--title is required when using --from-stdin")

    try:
        result = register_source(
            source=args.source,
            title=args.title,
            from_stdin=args.from_stdin,
            source_url=args.source_url,
            content_type_override=args.content_type,
            untrusted=args.untrusted,
            description=args.description,
        )
        print(result)
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
