#!/usr/bin/env python3
"""Heading-aware markdown chunker for pureMind vault.

Splits markdown files on heading boundaries (#{1-4}), tracks heading
breadcrumb paths, and falls back to fixed-window splitting for sections
exceeding MAX_CHUNK_CHARS.

Usage:
    python3 chunker.py <file_path>           # Print chunks as JSON
    python3 chunker.py <file_path> --verbose  # Print human-readable
"""

import json
import re
import sys
from pathlib import Path

MAX_CHUNK_CHARS = 2048
MIN_CHUNK_CHARS = 100
OVERLAP_RATIO = 0.2  # 20% overlap for fixed-window splits

HEADING_RE = re.compile(r"^(#{1,4})\s+(.+)$", re.MULTILINE)


def chunk_markdown(content: str, file_path: str = "") -> list[dict]:
    """Split markdown content into heading-aware chunks.

    Returns list of dicts: {content, heading_path, chunk_index}
    """
    # Split content into sections by heading boundaries
    sections = _split_by_headings(content)

    # Merge tiny sections with previous
    sections = _merge_small_sections(sections)

    # Split oversized sections with fixed-window overlap
    chunks = []
    chunk_idx = 0
    for section in sections:
        if len(section["content"]) > MAX_CHUNK_CHARS:
            sub_chunks = _fixed_window_split(section["content"], section["heading_path"])
            for sc in sub_chunks:
                sc["chunk_index"] = chunk_idx
                chunks.append(sc)
                chunk_idx += 1
        else:
            section["chunk_index"] = chunk_idx
            chunks.append(section)
            chunk_idx += 1

    return chunks


def _split_by_headings(content: str) -> list[dict]:
    """Split content on heading boundaries, tracking breadcrumb path.

    Skips headings inside fenced code blocks (``` or ~~~).
    """
    lines = content.splitlines(keepends=True)
    sections = []
    current_headings = {}  # level -> heading text
    current_lines = []
    current_path = ""
    in_fence = False

    for line in lines:
        stripped = line.rstrip()
        # Track fenced code blocks
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            current_lines.append(line)
            continue

        match = HEADING_RE.match(stripped) if not in_fence else None
        if match:
            # Flush previous section
            text = "".join(current_lines).strip()
            if text:
                sections.append({"content": text, "heading_path": current_path})

            # Update heading stack
            level = len(match.group(1))
            heading_text = match.group(2).strip()
            current_headings[level] = heading_text
            # Clear deeper headings
            for deeper in list(current_headings):
                if deeper > level:
                    del current_headings[deeper]

            # Build breadcrumb path
            path_parts = []
            for lvl in sorted(current_headings):
                path_parts.append(current_headings[lvl])
            current_path = " > ".join(path_parts)

            current_lines = [line]
        else:
            current_lines.append(line)

    # Flush final section
    text = "".join(current_lines).strip()
    if text:
        sections.append({"content": text, "heading_path": current_path})

    return sections


def _merge_small_sections(sections: list[dict]) -> list[dict]:
    """Merge sections smaller than MIN_CHUNK_CHARS with previous sibling section.

    Only merges when sections share the same parent heading path to avoid
    combining semantically unrelated content.
    """
    if not sections:
        return sections

    def _parent_path(path: str) -> str:
        """Get parent heading path (everything before last ' > ')."""
        if " > " in path:
            return path.rsplit(" > ", 1)[0]
        return ""

    merged = [sections[0]]
    for section in sections[1:]:
        prev = merged[-1]
        same_parent = _parent_path(section["heading_path"]) == _parent_path(prev["heading_path"])
        if len(section["content"]) < MIN_CHUNK_CHARS and merged and same_parent:
            prev["content"] += "\n\n" + section["content"]
            # Keep the deeper heading path
            if len(section["heading_path"]) > len(prev["heading_path"]):
                prev["heading_path"] = section["heading_path"]
        else:
            merged.append(section)

    return merged


def _fixed_window_split(text: str, heading_path: str) -> list[dict]:
    """Split text into overlapping windows when it exceeds MAX_CHUNK_CHARS."""
    overlap = int(MAX_CHUNK_CHARS * OVERLAP_RATIO)
    step = MAX_CHUNK_CHARS - overlap
    chunks = []
    pos = 0

    while pos < len(text):
        end = pos + MAX_CHUNK_CHARS
        chunk_text = text[pos:end].strip()
        if chunk_text:
            chunks.append({
                "content": chunk_text,
                "heading_path": heading_path,
            })
        pos += step

    return chunks


def main():
    if len(sys.argv) < 2:
        print("Usage: chunker.py <file_path> [--verbose]", file=sys.stderr)
        sys.exit(1)

    file_path = Path(sys.argv[1])
    verbose = "--verbose" in sys.argv

    if not file_path.exists():
        print(f"File not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    content = file_path.read_text(encoding="utf-8")
    chunks = chunk_markdown(content, str(file_path))

    if verbose:
        for i, chunk in enumerate(chunks):
            print(f"\n--- Chunk {i} [{chunk['heading_path']}] ({len(chunk['content'])} chars) ---")
            print(chunk["content"][:200] + ("..." if len(chunk["content"]) > 200 else ""))
        print(f"\nTotal: {len(chunks)} chunks")
    else:
        print(json.dumps(chunks, indent=2))


if __name__ == "__main__":
    main()
