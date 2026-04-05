---
name: write
description: Long-form writing in the operator's voice with vault context and style templates
inputs: [topic, output_type]
outputs: [document_path]
writes_to: [knowledge/, projects/, knowledge/drafts/]
side_effects: [vault_search]
---

# Write

Produce long-form content (blog posts, reports, memos, technical documents) calibrated to the operator's voice and informed by vault context.

## Steps

1. **Load style guide:**
```bash
cat ~/pureMind/templates/writing-style.md
```

2. **Load operator preferences:**
```bash
cat ~/pureMind/memory/user.md
```
Key rules: no em dashes, concise, technical, numbers over narratives.

3. **Search vault for related context:**
```bash
python3 ~/pureMind/tools/search.py "<topic>" --limit 5
```

4. **Determine output type and target length:**

| Type | Words | Key Rule |
|---|---|---|
| Blog post | 1200-1600 | Hook first, subheadings every 200-300 words, end with takeaway |
| Report | 800-1200 | Lead with findings, key metrics table at top, numbered recommendations |
| Memo | 200-500 | Single topic, one screen: situation, decision needed, recommendation |
| Technical doc | Unbounded | Executive summary first, command examples, file paths and line numbers |

5. **Write the content** following the style guide.

6. **Save the output:**
   - General knowledge: `~/pureMind/knowledge/<topic-slug>.md`
   - Project-specific: `~/pureMind/projects/<project>/`
   - Blog posts: draft to `~/pureMind/knowledge/drafts/<slug>.md` for review

## Constraints

- Always validate against writing-style.md before presenting to the operator.
- Never use em dashes in any published content.
- For Bretalon blog posts: the operator must approve before publishing. Schedule as future, send for review.
- For external-facing content: use approximate infrastructure numbers ("hundreds of cores", not exact counts).
