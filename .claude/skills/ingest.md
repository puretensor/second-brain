---
name: ingest
description: Ingest a URL, PDF, or document into the pureMind knowledge base with provenance tracking
---

# Ingest

Manually ingest external content into the pureMind vault. Supports URLs (via WebFetch), PDFs, markdown, and text files. All ingested content gets YAML frontmatter with provenance metadata and is auto-indexed for RAG search.

## For URLs

1. Fetch the content using WebFetch (Claude Code built-in tool)
2. Pipe the result to ingest.py:
```bash
python3 ~/pureMind/tools/ingest.py --from-stdin \
  --title "Article Title" \
  --source-url "https://example.com/article" \
  --category research \
  --tags topic1,topic2
```

## For Local Files (PDF, markdown, text)

```bash
# PDF (text extracted automatically via pdfplumber)
python3 ~/pureMind/tools/ingest.py ~/path/to/document.pdf --title "Document Title"

# Markdown
python3 ~/pureMind/tools/ingest.py ~/path/to/notes.md --category puretensor

# Text file
python3 ~/pureMind/tools/ingest.py ~/path/to/notes.txt --title "Meeting Notes" --tags meeting
```

## Options

| Flag | Description | Default |
|---|---|---|
| `--title` / `-t` | Document title (auto-detected from headings if omitted) | Auto |
| `--source-url` | Original URL for provenance | None |
| `--category` / `-c` | Subdirectory under knowledge/ | research |
| `--tags` | Comma-separated tags for frontmatter | None |
| `--from-stdin` | Read content from stdin instead of file | Off |

## Categories

Common categories (subdirectories under `knowledge/`):
- `research` -- general research and articles
- `puretensor` -- company-specific knowledge
- `contacts` -- people and organizations
- `archive` -- archived material

## Output

The tool saves to `~/pureMind/knowledge/<category>/<slug>.md` with YAML frontmatter containing title, date, source, tags, and ingested_by. Incremental re-indexing is triggered automatically.

## Constraints

- Maximum extracted text: 1MB (prevents index bloat)
- PDFs are converted to text; originals are not stored in the vault
- No binary files in the Git-tracked vault
- All ingested documents are auto-indexed by the vault indexer
