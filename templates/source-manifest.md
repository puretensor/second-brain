# Source Manifest Template

## Frontmatter

Every source manifest in `sources/manifests/` must have this YAML frontmatter block:

```yaml
---
source_id: src-YYYYMMDD-slug
title: "Human-readable title of the source"
origin_url: ""
origin_path: ""
captured_at: YYYY-MM-DDTHH:MM:SSZ
content_type: pdf|markdown|text|html|stdin
blob_sha256: ""
untrusted_source: true|false
snapshot_path: "sources/snapshots/..."
canonical_pages: []
---
```

### Field Definitions

| Field | Required | Description |
|-------|----------|-------------|
| `source_id` | Yes | Unique identifier: `src-YYYYMMDD-slug` |
| `title` | Yes | Human-readable title |
| `origin_url` | If URL | Original URL where content was fetched |
| `origin_path` | If file | Filesystem path where the original lives (e.g., Ceph, NAS) |
| `captured_at` | Yes | ISO 8601 timestamp of when the content was captured |
| `content_type` | Yes | Format of the original: pdf, markdown, text, html, stdin |
| `blob_sha256` | Recommended | SHA-256 of the original file for integrity verification |
| `untrusted_source` | Yes | true if content came from external/untrusted origin |
| `snapshot_path` | If captured | Vault-relative path to the markdown snapshot |
| `canonical_pages` | Yes | List of wiki page filenames created/updated from this source |

## Body

Below the frontmatter, include a brief description of the source and any processing notes:

```markdown
# {source title}

Brief description of the source content and its relevance.

## Processing Notes
- How the content was captured (WebFetch, manual upload, ingest.py, etc.)
- Any quality issues or extraction problems
- Sections that were particularly relevant
```

## Naming Convention

Manifest files are named `{source_id}.md` and stored in `sources/manifests/`.
Example: `sources/manifests/src-20260406-arxiv-rag-survey.md`
