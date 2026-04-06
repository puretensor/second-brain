# Raw Sources

Immutable raw material layer. Files here are never edited after registration.

## Structure

- `manifests/` -- YAML frontmatter files describing each registered source (one .md per source)
- `snapshots/` -- Captured markdown renderings of external content (no binaries)
- `index.md` -- Append-only registry of all registered sources

## Rules

1. Sources are immutable once registered. Never edit a manifest or snapshot after creation.
2. No binaries in Git. PDFs and images stay on Ceph or external storage; manifests link to them via `origin_path`.
3. Every source gets a unique `source_id` in format `src-YYYYMMDD-slug`.
4. Register the source *before* synthesizing wiki pages from it.
5. Wiki pages in `knowledge/` reference sources via `source_refs` in their frontmatter.

## Workflow

1. Content arrives (URL, PDF, document, text)
2. Create a manifest in `manifests/<source_id>.md` using `templates/source-manifest.md`
3. Optionally capture a markdown snapshot in `snapshots/<source_id>.md`
4. Add entry to `index.md`
5. Synthesize or update wiki pages in `knowledge/`, linking back via `source_refs: [<source_id>]`
