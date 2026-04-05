---
name: research
description: Deep research combining vault knowledge and web sources, producing cited Obsidian notes
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

5. **Save the research note:**
```bash
cat > ~/pureMind/knowledge/research/<topic-slug>.md << 'RESEARCH'
---
title: "<Topic Title>"
date: YYYY-MM-DD
query: "<original research query>"
sources:
  - <url1>
  - <url2>
vault_refs:
  - <file_path:heading>
---

# <Topic Title>

<Synthesized findings with inline citations [1], [2]>

## Key Findings
- <finding 1>
- <finding 2>

## Vault Context
<What the vault already knew about this topic>

## Sources
1. <citation with URL or vault path>
2. <citation>
RESEARCH
```

## Output Format

- YAML frontmatter with date, query, sources, vault_refs
- Body with synthesized prose (not raw quotes)
- Inline citations using numbered references
- `## Sources` section at the end

## Constraints

- **Vault first.** Never skip the vault search. The operator's existing knowledge is primary.
- **Citation discipline.** No uncited claims. Every factual statement references a source.
- Research notes are auto-indexed by the PostToolUse hook after file write.
- Do not duplicate content already in the vault. Reference existing notes instead.
