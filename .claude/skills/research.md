---
name: research
description: Parallel research pipeline with multi-source investigation, cross-checking, and synthesis
inputs: [topic_query, depth]
outputs: [research_note_path]
writes_to: [knowledge/research/]
side_effects: [vault_search, web_search, agent_subagents]
---

# Research

Conduct deep research on a topic. Two modes:
- **quick** (default): Single-pass vault-first research. Fast, good for focused queries.
- **deep**: Parallel multi-agent pipeline with source cross-checking. Use for comprehensive investigations.

Usage: `/research "topic"` (quick) or `/research "topic" deep` (deep mode)

---

## Quick Mode (default)

### Steps

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

---

## Deep Mode (parallel pipeline)

Use deep mode when the topic requires comprehensive multi-source investigation, when accuracy is critical, or when the operator explicitly requests it.

### Step 1: Vault-first search (same as quick mode)

```bash
python3 ~/pureMind/tools/search.py "<topic>" --limit 5
python3 ~/pureMind/tools/search.py "<topic>" --graph --limit 3
```

Also check for existing research notes on this or related topics:
```bash
python3 ~/pureMind/tools/search.py "<topic>" --file-filter knowledge/research/ --limit 3
```

### Step 2: Decompose into research axes

Based on the topic and vault results, identify 3-4 research axes. Examples:

**Technology topics:**
- Academic/papers (arxiv, conference proceedings, technical standards)
- Industry/vendor (official documentation, engineering blogs, benchmarks)
- Competitive/alternatives (comparisons, alternatives, trade-offs)
- Practical/implementation (tutorials, real-world deployments, lessons learned)

**Business topics:**
- Market data (market size, growth rates, trends)
- Regulatory/compliance (regulations, standards, legal requirements)
- Competitive landscape (competitors, positioning, differentiation)
- Case studies (success stories, failures, lessons)

**Infrastructure topics:**
- Vendor documentation (official guides, release notes, best practices)
- Community experience (forums, blog posts, post-mortems)
- Security considerations (CVEs, hardening guides, audit reports)
- Performance data (benchmarks, capacity planning, scaling patterns)

### Step 3: Spawn parallel research agents

Launch one Agent sub-agent per research axis using the Agent tool. Each agent receives:

- The specific axis and what sources to prioritize
- The vault context from Step 1 (to avoid duplicating existing knowledge)
- A structured output format requirement

**Agent prompt template (adapt per axis):**

> Research axis: [AXIS NAME]
> Topic: [TOPIC]
>
> Existing vault knowledge (do not duplicate):
> [VAULT RESULTS FROM STEP 1]
>
> Your task: Investigate this topic through the lens of [AXIS]. Find 3-5 high-quality sources using WebSearch and WebFetch. For each source, extract the key claims with explicit source URLs.
>
> Return your findings as structured text:
> - Axis: [name]
> - Sources found: [list with URLs and access dates]
> - Key findings: [list of claims, each with source reference]
> - Confidence: [high/medium/low per finding]
> - Gaps: [what you could not find or verify]
> - Contradictions: [anything that conflicts with vault knowledge or other findings]

**Important:** Use the Agent tool (not `claude -p`). Agents need WebSearch and WebFetch access for web research.

### Step 4: Review and cross-check

Launch a single reviewer Agent sub-agent that receives ALL axis findings and:

> You are a research reviewer. You have received findings from [N] parallel research agents investigating "[TOPIC]".
>
> [ALL AGENT OUTPUTS]
>
> Your task:
> 1. Cross-check: identify claims that appear in multiple axes (corroborated) vs. single-source claims (uncorroborated)
> 2. Flag contradictions: any claims that conflict between agents
> 3. Source quality: rate each source (primary/secondary/tertiary)
> 4. Identify gaps: what important aspects were missed across all axes?
> 5. Confidence assessment: overall confidence in the research findings
>
> Return a structured review with: corroborated_claims, contested_claims, uncorroborated_claims, gaps, overall_confidence.

### Step 5: Synthesize and save

The main context combines the reviewer's output into the final research note:

**Frontmatter:**
```yaml
---
title: "<topic>"
date: YYYY-MM-DD
query: "<original query>"
mode: deep
axes: [<list of research axes used>]
sources: [<all URLs from all agents>]
vault_refs: [<vault file paths referenced>]
---
```

**Body structure:**
- `## Key Findings` -- synthesized from all axes, with inline citations `[N]`
- `## Cross-Check Summary` -- from reviewer: corroborated vs contested vs uncorroborated claims
- `## Gaps and Limitations` -- what the research did not cover
- `## Vault Context` -- what was already known vs what is new
- `## Sources` -- numbered list matching inline citations

Save to: `~/pureMind/knowledge/research/<topic-slug>.md`

---

## Output Format (both modes)

- YAML frontmatter with date, query, sources, vault_refs
- Body with synthesized prose (not raw quotes)
- Inline citations using numbered references
- `## Sources` section at the end
- Deep mode adds: `## Cross-Check Summary` and `## Gaps and Limitations`

## Constraints

- **Vault first.** Never skip the vault search. The operator's existing knowledge is primary. Log the vault search results so the operator can verify it happened.
- **Citation discipline.** No uncited claims. Every factual statement references a source.
  - Vault: `[N] vault: knowledge/topic/file.md > Heading`
  - Web: `[N] https://example.com/article (accessed YYYY-MM-DD)`
- **No hallucinated sources.** If an agent returns a URL, verify it was actually fetched via WebFetch. Flag suspicious sources.
- Research notes are auto-indexed by the PostToolUse hook after file write.
- Do not duplicate content already in the vault. Reference existing notes instead.
- Deep mode spawns 3-5 Agent sub-agents. Use sparingly -- this consumes significant compute.
