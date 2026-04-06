# Wiki Page Template

## Frontmatter

Every wiki page in `knowledge/` must have this YAML frontmatter block:

```yaml
---
title: "Human-readable page title"
page_type: entity|concept|overview|comparison|project|source-summary
status: seed|active|needs-review
source_refs: []
aliases: []
updated: YYYY-MM-DD
---
```

### Field Definitions

| Field | Required | Values | Description |
|-------|----------|--------|-------------|
| `title` | Yes | string | Human-readable title |
| `page_type` | Yes | entity, concept, overview, comparison, project, source-summary | Classification of the page |
| `status` | Yes | seed, active, needs-review | Editorial lifecycle state |
| `source_refs` | Yes | list of source_id strings | Links to sources/ manifests that informed this page |
| `aliases` | No | list of strings | Alternative names for wikilink resolution |
| `updated` | Yes | YYYY-MM-DD | Last substantive edit date |

### Status Lifecycle

- **seed** -- Stub or newly created page with minimal content
- **active** -- Complete, reviewed, and maintained
- **needs-review** -- Content may be stale or accuracy is uncertain

### Compatibility with Ingest Frontmatter

Pages created by `tools/ingest.py` have their own frontmatter (title, date, source, category, tags, ingested_by). Wiki fields are added alongside ingest fields, not as replacements. Both schemas coexist.

## Body Structure

```markdown
# {Title}

> One-sentence summary of what this page covers.

## Overview
[2-3 paragraphs of core content]

## Details
[Detailed sections as needed]

## Related
- [[other-page]] -- how it relates
- [[another-page]] -- how it relates

## Sources
- src-YYYYMMDD-slug -- what it contributed to this page
```

## Guidelines

- Use `[[wikilinks]]` for cross-references to other knowledge/ pages
- Keep pages focused on a single topic -- split if a page grows beyond ~2000 words
- Prefer updating an existing page over creating a near-duplicate
- Source claims: link to source_refs in frontmatter, cite inline where precision matters
