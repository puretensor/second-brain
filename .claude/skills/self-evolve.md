---
name: self-evolve
description: Create or modify pureMind skills by analyzing patterns and composing existing tools
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

**MUST do:**
- Follow the established skill pattern (YAML frontmatter, steps, constraints)
- Only reference existing CLI tools and integrations
- Test the new skill after creation by running it once
- Log the creation in the daily log

## Examples

### Creating a /cluster-status skill
```bash
cat > ~/pureMind/.claude/skills/cluster-status.md << 'SKILL'
---
name: cluster-status
description: Quick overview of fleet node status and key services
---

# Cluster Status

Check fleet health by querying key endpoints and node status.

## Steps

1. **Check node status:**
\```bash
ssh mon1 "uptime && ceph -s --format json-pretty | head -20"
\```

2. **Check key services:**
\```bash
kubectl get pods -A --field-selector=status.phase!=Running 2>/dev/null || echo "K8s not accessible"
\```

## Constraints

- Read-only. No fleet actions (those go through Immune system).
SKILL
```

### Modifying an existing skill
Read the current version first, then edit the specific section that needs changing.
