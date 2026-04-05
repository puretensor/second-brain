---
name: puremind-search
description: Search the pureMind knowledge vault using hybrid BM25+vector retrieval with optional graph traversal and HyDE
inputs: [query, limit, file_filter, graph, hyde, lang]
outputs: [search_results]
writes_to: []
side_effects: []
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
- `--graph` -- graph-augmented search: find entities in query, traverse knowledge graph, fuse graph-sourced chunks with hybrid results
- `--hyde` -- HyDE search: generate hypothetical answer via Claude CLI, embed it, use for improved semantic retrieval on vague queries
- `--lang LANG` -- FTS language config (default: `english`). Use `simple` for non-English or mixed-language content (applies unaccent)

## When to Use Each Mode

| Mode | Best For | Cost |
|---|---|---|
| Default | Specific factual queries | Fast, no LLM call |
| `--graph` | Relationship queries ("how is X connected to Y") | Fast (DB only) |
| `--hyde` | Vague/abstract queries ("what should I focus on") | +1 Claude CLI call |
| `--lang simple` | Non-English content (Icelandic, Spanish names) | Same as default |

## Examples

```bash
# Standard hybrid search
python3 ~/pureMind/tools/search.py "GPU batch processing lessons"

# Graph-augmented: traverse entity relationships
python3 ~/pureMind/tools/search.py "How is PureClaw connected to pgvector?" --graph

# HyDE: better retrieval for vague queries
python3 ~/pureMind/tools/search.py "What should I focus on next?" --hyde

# Multilingual: Icelandic content
python3 ~/pureMind/tools/search.py "Sjova" --lang simple

# Combined: filter + JSON
python3 ~/pureMind/tools/search.py "NVIDIA contacts" --file-filter knowledge/contacts/ --json
```

## How It Works

1. Embeds query with nomic-embed-text-v1.5 (768-dim)
2. Runs BM25 full-text search via PostgreSQL tsvector
3. Runs vector similarity search via pgvector HNSW index
4. Fuses results via Reciprocal Rank Fusion (k=60)
5. (--graph) Also traverses pm_entities/pm_relationships graph, retrieves connected chunks
6. (--hyde) Generates hypothetical answer via Claude CLI, embeds that instead of raw query

## Entity Extraction

Entities are extracted from vault files and stored in pm_entities/pm_relationships:

```bash
python3 ~/pureMind/tools/extract.py                    # Incremental
python3 ~/pureMind/tools/extract.py --full              # Full re-extraction
python3 ~/pureMind/tools/extract.py --file <path>       # Single file
```

## Hierarchical Summaries

Tree-structured summaries at file/project/vault levels:

```bash
python3 ~/pureMind/tools/summarize.py --file <path>     # Single file
python3 ~/pureMind/tools/summarize.py --project <name>  # Project
python3 ~/pureMind/tools/summarize.py --build-all       # Full tree
```

## Re-indexing

The vault auto-indexes on file changes. To manually re-index:

```bash
python3 ~/pureMind/tools/index.py            # Incremental (changed files)
python3 ~/pureMind/tools/index.py --full      # Full re-index
```
