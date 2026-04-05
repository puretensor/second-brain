# HAL Writing Style Guide

## Voice

- Match the operator's natural voice: direct, technical, no filler
- Never use em dashes (--) in published content. Use colons, semicolons, or sentence breaks instead
- Numbers and data over narrative. Quantify wherever possible
- Concise paragraphs. If it can be a bullet, make it a bullet
- No hedging language ("perhaps", "it seems", "it might be worth"). State facts or state uncertainty directly
- No emojis unless explicitly requested

## Output Types

### Blog Post (1200-1600 words)
- Hook in first paragraph: what is this about and why should the reader care
- Subheadings every 200-300 words
- Code examples where relevant (fenced, with language tag)
- End with a clear takeaway, not a summary

### Technical Document (unbounded)
- Start with a one-paragraph executive summary
- Use tables for structured data
- Include command examples that can be copy-pasted
- Reference specific file paths and line numbers

### Report (800-1200 words)
- Lead with findings, not methodology
- Key metrics in a summary table at the top
- Recommendations as numbered action items

### Memo (200-500 words)
- Single topic. One screen maximum
- Format: situation, decision needed, recommendation
- No preamble

## Before Writing

1. Search the vault for related context: `python3 ~/pureMind/tools/search.py "<topic>" --limit 5`
2. Load `memory/user.md` for operator preferences and domain vocabulary
3. Check `projects/` for relevant project context if the topic is project-specific

## After Writing

- Save output to `knowledge/` (general) or `projects/<name>/` (project-specific)
- The PostToolUse hook handles git commit and auto-indexing
