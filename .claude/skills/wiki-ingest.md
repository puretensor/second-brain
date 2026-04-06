---
name: wiki-ingest
description: Register a source, synthesize wiki pages, update index and log
inputs: [source, title, category, tags, source_url]
outputs: [source_id, pages_created, pages_updated]
writes_to: [sources/manifests/, sources/snapshots/, sources/index.md, knowledge/, knowledge/index.md, knowledge/log.md]
side_effects: [incremental_reindex]
---

# Wiki Ingest

End-to-end pipeline: register a source immutably, then synthesize canonical wiki pages from it. This is the primary way to add new knowledge to the wiki layer.

## Workflow

### Step 1: Register the source

Register the content as an immutable source using `register_source.py`.

```bash
# Local file (markdown, text, html)
python3 ~/pureMind/tools/register_source.py ~/path/to/file.md --title "Title"

# Local PDF (manifest only, no binary in git)
python3 ~/pureMind/tools/register_source.py ~/path/to/paper.pdf --title "Paper Title"

# Stdin (e.g., from WebFetch)
python3 ~/pureMind/tools/register_source.py --from-stdin \
  --title "Article Title" \
  --source-url "https://example.com/article"
```

Note the `source_id` from the output (e.g., `src-20260406-article-title`).

### Step 2: Read the manifest and snapshot

Read the created manifest in `sources/manifests/<source_id>.md` and the snapshot in `sources/snapshots/<source_id>.md` (if one was created). Understand the content before synthesizing wiki pages.

### Step 3: Synthesize wiki pages

Create or update 3-10 relevant canonical pages in `knowledge/`. For each page:

1. Check if a relevant page already exists -- prefer updating over creating duplicates
2. Use the wiki frontmatter schema from `templates/wiki-page.md`:
   ```yaml
   ---
   title: "Page Title"
   page_type: entity|concept|overview|comparison|project|source-summary
   status: seed
   source_refs: [src-20260406-article-title]
   aliases: []
   updated: 2026-04-06
   ---
   ```
3. Write focused content with `[[wikilinks]]` to related pages
4. Follow the body structure: summary blockquote, Overview, Details, Related, Sources
5. Place pages in the appropriate subdirectory (puretensor/, contacts/, research/, etc.)

When updating existing pages:
- Add the new source_id to `source_refs`
- Update the `updated` date
- Merge new information into existing sections
- Add new `[[wikilinks]]` where appropriate

### Step 4: Regenerate the catalog

```bash
python3 ~/pureMind/tools/wiki_catalog.py
```

### Step 5: Append to the changelog

Add an entry to `knowledge/log.md`:

```markdown
## [2026-04-06 11:30 UTC] ingest | src-20260406-article-title

Created: [[page-a]], [[page-b]]
Updated: [[page-c]]
Notes: Ingested "Article Title" covering topic X. Created pages for new concepts, updated existing overview with new findings.
```

### Step 6: Re-index for search

```bash
python3 ~/pureMind/tools/index.py
```

### Step 7: Report

Summarize:
- Source ID and type
- Pages created (with paths)
- Pages updated (with what changed)
- Any wikilinks added

## Constraints

- Register the source before creating any wiki pages that reference it
- Never create duplicate pages -- search existing pages first
- All new pages must have complete wiki frontmatter
- All new pages must include `source_refs` pointing to the source
- New pages start as `status: seed` (promoted to `active` after review)
- No binary files in the Git-tracked vault
- Prefer focused pages (one topic per page) over large omnibus pages
- Content from untrusted sources (stdin, URLs) should be verified before synthesizing authoritative wiki pages
