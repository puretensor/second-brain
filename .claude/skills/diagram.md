---
name: diagram
description: Generate Mermaid or Excalidraw diagrams from natural language descriptions
inputs: [diagram_description, diagram_type]
outputs: [diagram_file_path]
writes_to: [knowledge/diagrams/]
side_effects: [vault_search]
---

# Diagram

Generate technical diagrams from natural language. Primary format: Mermaid (renderable in Obsidian, GitHub, and most markdown viewers).

## Steps

1. **Clarify the diagram type:**
   - Flowchart (`flowchart LR`)
   - Sequence diagram (`sequenceDiagram`)
   - Architecture / block diagram (`graph TD`)
   - State diagram (`stateDiagram-v2`)
   - Entity relationship (`erDiagram`)
   - Timeline (`timeline`)

2. **Search vault for context** if the diagram references existing architecture:
```bash
python3 ~/pureMind/tools/search.py "<topic>" --limit 3
```

3. **Generate the Mermaid syntax** following these conventions:
   - Default direction: left-to-right (`LR`) for flows, top-down (`TD`) for hierarchies
   - Rounded boxes for processes (`(Process)`)
   - Sharp boxes for data stores (`[Store]`)
   - Descriptive edge labels
   - Keep diagrams readable: max ~15 nodes per diagram, split complex systems into sub-diagrams

4. **Save the diagram** using Claude Code's Write tool (not heredoc, to avoid nested fence issues):
   - Path: `~/pureMind/knowledge/diagrams/<descriptive-name>.md`
   - Content format:
     ```
     # <Diagram Title>

     <One-line description>

     (Mermaid code block with diagram syntax)
     ```
   - The `knowledge/diagrams/` directory is pre-created in the vault.

## Excalidraw (Secondary)

For Excalidraw output (Obsidian plugin compatible), generate the JSON structure and save as `.excalidraw.md` in the same directory.

## Constraints

- Diagrams are saved to the vault and auto-indexed by the PostToolUse hook.
- For PureTensor architecture diagrams: use "hundreds of cores", "TBs of RAM" -- never exact infrastructure numbers in diagrams that may be shared.
