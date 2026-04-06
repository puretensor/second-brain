---
name: wiki-lint
description: Run wiki lint, review findings, fix or propose fixes, log changes
inputs: [file_filter, fix]
outputs: [lint_report, fixes_applied]
writes_to: [knowledge/, knowledge/index.md, knowledge/log.md]
side_effects: [incremental_reindex]
---

# Wiki Lint

Run deterministic lint checks on wiki pages, review the findings, fix what can be fixed automatically, and propose fixes for judgment calls.

## Workflow

### Step 1: Run lint

```bash
# Full vault lint
python3 ~/pureMind/tools/wiki_lint.py

# Single file
python3 ~/pureMind/tools/wiki_lint.py --file knowledge/puretensor/services.md

# JSON output for structured analysis
python3 ~/pureMind/tools/wiki_lint.py --json
```

### Step 2: Review findings

Analyze the lint output by severity:

- **ERROR** -- must fix: missing frontmatter, missing fields, invalid enums, broken wikilinks
- **WARNING** -- should fix: orphan pages, empty source_refs, stale status, not in index
- **INFO** -- optional: no wikilinks in page body

### Step 3: Fix or propose

**Auto-fix** (do directly):
- `no-frontmatter`: Add wiki frontmatter with best-guess values from page content:
  - `title`: from first heading or filename
  - `page_type`: infer from content (entity for company/people pages, overview for broad topics, concept for technical terms)
  - `status`: `seed` for bare pages, `active` for well-developed pages
  - `source_refs`: `[]` (backfill later if source is known)
  - `aliases`: common alternative names
  - `updated`: today's date
- `missing-field`: Add the specific missing wiki fields to existing frontmatter
- `no-wikilinks`: Add `[[wikilinks]]` to related pages where obvious connections exist
- `not-in-index`: Regenerate the catalog (Step 4)

**Propose to user** (do not auto-fix):
- `stale-page`: Flag for user review, do not change status
- `broken-wikilink`: Propose the correct target or page creation
- `orphan-page`: Suggest where to add inbound links

### Step 4: Regenerate catalog (if pages were modified)

```bash
python3 ~/pureMind/tools/wiki_catalog.py
```

### Step 5: Log changes (if fixes were applied)

Append to `knowledge/log.md`:

```markdown
## [2026-04-06 14:00 UTC] lint | wiki-lint-run

Fixed: [[corporate]] (added frontmatter), [[services]] (added frontmatter)
Fixed: [[lessons]] (added frontmatter, added wikilinks)
Notes: Lint pass resolved 4 no-frontmatter errors and 3 no-wikilinks findings. 2 orphan-page warnings remain (require content-page cross-links).
```

### Step 6: Re-index (if changes were made)

```bash
python3 ~/pureMind/tools/index.py
```

### Step 7: Report

Show:
- Findings before fixes (original lint counts)
- What was fixed
- Remaining findings after fixes
- Re-run lint to confirm improvement

## Constraints

- Never delete page content -- only add or fix metadata and links
- Never change `status` from `needs-review` without user approval
- Log all changes in `knowledge/log.md` before re-indexing
- Run `wiki_catalog.py` after any page modifications
- For pages with ingest-tool frontmatter: add wiki fields alongside, never replace ingest fields
- When adding frontmatter to bare pages, preserve all existing content below the new frontmatter block
