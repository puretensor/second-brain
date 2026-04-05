---
name: research
description: Deep research combining vault knowledge and web sources, producing cited Obsidian notes
inputs: [topic_query]
outputs: [research_note_path]
writes_to: [knowledge/research/]
side_effects: [vault_search, web_search]
---

# Research

Conduct deep research on a topic. Always check the vault first, then extend to the web. Produce a cited Obsidian note saved to the knowledge base.

## Steps

1. **Vault-first search** (always do this before going to the web):
```bash
python3 ~/pureMind/tools/search.py "<topic>" --limit 5
python3 ~/pureMind/tools/search.py "<related terms>" --limit 3
```

2. **Check operator context** for relevance:
```bash
cat ~/pureMind/memory/user.md
```
Reference focus areas and domain vocabulary to prioritize relevant angles.

3. **Web research** (only after vault search):
   - Use `WebSearch` to discover sources (target 3-5 high-quality results)
   - Use `WebFetch` to read full content from the best sources
   - Prefer primary sources: official docs, papers, vendor blogs
   - Avoid: SEO spam, aggregator sites, outdated content (check dates)

4. **Synthesize findings** into a research note:
   - Combine vault knowledge with web discoveries
   - Every claim must cite either a vault chunk (file path + heading) or a web URL
   - Identify gaps: what did the vault not know that the web revealed?

5. **Save the research note** using Claude Code's Write tool.

   Generate the slug using the same pattern as ingest.py: lowercase, strip non-alphanumeric, hyphens for spaces, max 60 chars. Path: `~/pureMind/knowledge/research/<topic-slug>.md`

   Content format (YAML frontmatter + markdown body):
   - Frontmatter: title, date (YYYY-MM-DD), query, sources (list of URLs), vault_refs (list of file_path:heading)
   - Body: synthesized prose with `[1]` inline citations, Key Findings section, Vault Context section
   - Sources section: numbered list matching inline citations
   - Vault citations: `[N] vault: knowledge/topic/file.md > Heading`
   - Web citations: `[N] https://example.com/article (accessed YYYY-MM-DD)`

## Output Format

- YAML frontmatter with date, query, sources, vault_refs
- Body with synthesized prose (not raw quotes)
- Inline citations using numbered references
- `## Sources` section at the end

## Constraints

- **Vault first.** Never skip the vault search. The operator's existing knowledge is primary. Log the vault search results in step 1 output so the operator can verify it happened.
- **Citation discipline.** No uncited claims. Every factual statement references a source. Use the exact formats above (vault: path > heading, or URL with access date).
- Research notes are auto-indexed by the PostToolUse hook after file write.
- Do not duplicate content already in the vault. Reference existing notes instead.
