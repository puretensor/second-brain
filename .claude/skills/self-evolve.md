---
name: self-evolve
description: Create or modify pureMind skills by analyzing patterns and composing existing tools
inputs: [capability_request]
outputs: [skill_file]
writes_to: [.claude/skills/, templates/]
side_effects: [daily_log_entry]
---

# Self-Evolve

pureMind creates or modifies its own skills based on usage patterns, operator requests, or identified capability gaps. This is the compounding mechanism -- the system grows capabilities without the operator writing boilerplate.

## When to Trigger

- The operator explicitly asks: "make a skill for X" or "create a /skillname command"
- A repeated multi-step sequence could be captured as a reusable skill
- A task requires composing 3+ existing tools in a pattern not yet captured

## Process

### 1. Analyze the Request

What capability is needed? Is it:
- A new skill (new .md file)
- A modification to an existing skill
- A new template (supporting file for skills)

### 2. Survey Existing Skills

Read all current skills to understand the established pattern:
```bash
ls ~/pureMind/.claude/skills/*.md
```

Read 2-3 representative skills for pattern reference:
```bash
cat ~/pureMind/.claude/skills/draft-email.md
cat ~/pureMind/.claude/skills/research.md
```

### 3. Survey Available Building Blocks

Check what tools and integrations exist:
```bash
ls ~/pureMind/tools/*.py
ls ~/pureMind/.claude/integrations/*_integration.py
```

### 4. Compose the New Skill

Write a new `.md` file following the exact pattern:

```markdown
---
name: <skill-name>
description: <one-line description>
---

# <Skill Title>

<What this skill does, in 1-2 sentences>

## Steps

<Numbered steps with bash code blocks calling existing tools>

## Constraints

<Permission boundaries and limitations>
```

**Conventions to follow:**
- YAML frontmatter with `name` and `description`
- Steps section with `bash` code blocks for CLI invocations
- Constraints section documenting permission boundaries
- Reference only tools and integrations that exist on disk
- Keep skills focused: one capability per skill

### 5. Save and Verify

Save to the skills directory:
```bash
# Write the skill file
cat > ~/pureMind/.claude/skills/<skill-name>.md << 'EOF'
<skill content>
EOF
```

Verify the file was created and follows conventions:
```bash
cat ~/pureMind/.claude/skills/<skill-name>.md
```

### 6. Log the Creation

Note in the daily log that a new skill was created, with rationale:
```
### Work Done
- Created /skill-name skill: <what it does and why>
```

## Guard Rails

**CAN do:**
- Create new skill .md files in `.claude/skills/`
- Modify existing skill .md files
- Create new template files in `templates/`

**CANNOT do:**
- Bypass the pureMind permission model (soul.md red lines apply)
- Reference tools that do not exist on disk (verify with `ls` first)
- Modify `soul.md`, `user.md`, or integration Python code
- Create new Python tools autonomously. If a new tool is needed:
  1. Draft the Python code
  2. Present it to the operator for review
  3. Only create the file after explicit approval
- Call raw shell commands (ssh, kubectl, curl, wget) directly in skills. Skills must compose existing pureMind tools only
- Create skills that invoke integration Python functions directly (e.g., importing `_call_gmail`). All integration access must go through the CLI wrappers

**MUST do:**
- Follow the established skill pattern (YAML frontmatter, steps, constraints)
- Only compose these verified building blocks:
  - `tools/search.py`, `tools/index.py`, `tools/ingest.py` (vault tools)
  - `.claude/integrations/*_integration.py` (CLI interface only)
  - `.claude/hooks/daily_reflect.py` (reflection)
  - Claude Code built-in tools (WebSearch, WebFetch, Read, Write, Glob, Grep)
  - Templates in `templates/`
- Test the new skill after creation by running it once
- Log the creation in the daily log

## Examples

### Creating a /meeting-prep skill

Use Claude Code's Write tool to create the file directly (not heredoc):

Target path: `~/pureMind/.claude/skills/meeting-prep.md`

Content to write:
```markdown
---
name: meeting-prep
description: Prepare a briefing for an upcoming meeting using calendar and vault context
---

# Meeting Prep

Prepare context and talking points for an upcoming meeting.

## Steps

1. **Find the meeting:**
python3 ~/pureMind/.claude/integrations/calendar_integration.py list_events --days 3 --account ops

2. **Search vault for meeting context:**
python3 ~/pureMind/tools/search.py "<attendee or topic>" --limit 5

3. **Check recent activity:**
python3 ~/pureMind/tools/search.py "<topic>" --file-filter daily-logs/ --limit 3

4. **Synthesize** a briefing note with: attendees, agenda, relevant vault context, talking points.

## Constraints

- Read-only. Does not modify any files or create calendar events.
- All calendar and search operations are logged to pm_audit.
```

### Modifying an existing skill
Read the current version first, then edit the specific section that needs changing. Use Claude Code's Edit tool, not heredocs.
