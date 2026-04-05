---
name: puremind-search
description: Search the pureMind knowledge vault using hybrid BM25+vector retrieval
---

# pureMind Search

Search the pureMind vault for relevant knowledge using hybrid retrieval
(BM25 full-text + vector semantic search with Reciprocal Rank Fusion).

## Usage

```bash
python3 ~/pureMind/tools/search.py "<query>" --limit 5
```

Options:
- `--limit N` -- number of results (default: 5)
- `--json` -- output as JSON instead of markdown
- `--file-filter prefix` -- restrict to files matching prefix (e.g., `knowledge/`)

## Examples

```bash
# Find GPU-related lessons
python3 ~/pureMind/tools/search.py "GPU batch processing lessons"

# Search contacts only
python3 ~/pureMind/tools/search.py "NVIDIA contacts" --file-filter knowledge/contacts/

# Get raw JSON for programmatic use
python3 ~/pureMind/tools/search.py "K3s deployment" --json --limit 3
```

## How It Works

1. Embeds query with nomic-embed-text-v1.5 (768-dim)
2. Runs BM25 full-text search via PostgreSQL tsvector
3. Runs vector similarity search via pgvector HNSW index
4. Fuses results via Reciprocal Rank Fusion (k=60)
5. Returns ranked results with file path, heading path, and relevance score

## Re-indexing

The vault auto-indexes on file changes. To manually re-index:

```bash
python3 ~/pureMind/tools/index.py            # Incremental (changed files)
python3 ~/pureMind/tools/index.py --full      # Full re-index
```
