# Operator Profile

## Identity

- **Name:** Heimir Helgason
- **Timezone:** Europe/London (UTC+0/+1)
- **Role:** Founder and sole operator of PureTensor (US Inc + UK Ltd)
- **Languages:** English (fluent), Icelandic (native), Spanish (conversational), Danish (conversational)
- **Nationality:** Icelandic (EEA), UK resident
- **Background:** Autodidact, serial entrepreneur. Deep technical knowledge across infrastructure, ML, and systems.

## Working Style

- Direct. Says "do X now" and means execute immediately.
- Prefers concise output -- numbers and summaries over verbose listings.
- Plans for complex tasks, immediate execution for straightforward ones.
- Expects autonomous bug fixing -- point at the problem, fix it, report back.
- Reviews after the fact, not during. Does not want to be asked obvious questions.

## Communication Channels

- Primary: Telegram (via PureClaw bot @hal_claude_bot)
- Claude Code for infrastructure and development work
- Email: hal@puretensor.ai (always CC ops@puretensor.ai)
- Calendar: ops@puretensor.ai (single calendar, no separate personal)
- X/Twitter: @puretensor (personal), @puretensorai (company)

## Domain Vocabulary

Use these terms correctly. Misuse is a red line.
- **"sovereign compute cluster"** -- the PureTensor fleet. Never "homelab," "lab," or "home server."
- **"PureTensor"** -- one word, CamelCase. Never "Pure Tensor."
- **"the Trinity"** -- the Ray cluster (TC + fox-n0 + fox-n1, 160 CPUs, 2 GPUs, 200 GbE)
- **"TC" / "tensor-core"** -- the bridge node with 2x RTX PRO 6000 Blackwell GPUs
- **"fleet"** or **"cluster"** -- acceptable shorthand for the full infrastructure

## Current Projects

- **PureClaw/Nexus** -- Agentic AI across Telegram, Discord, email. K3s on fox-n1. Production.
- **Immune System** -- Self-healing autonomous fleet services. immune_core on TC. Active.
- **pureMind** -- Second brain (this vault). Phase 1 complete, Phase 2 next.
- **Synapse** -- Set-theoretic ML network intelligence. FastAPI :8900, Neo4j + Redis. Active.
- **Sentinel (mon3)** -- Gemma 4 on Pi 5, hourly health reports. Phase 1 live.
- **Bretalon** -- AI-focused news publication. WordPress + Imagen 4 pipeline.
- **Third Blackwell GPU** -- Pending for fox-n0 (always-on 24/7 node).

## Key Contacts

- **Alan Apter** -- CTO, PureTensor. alan.apter@puretensor.ai. Reviews Bretalon articles.
- **Sean Ardura** -- NVIDIA US SDS. sardura@nvidia.com. AWS Activate, Inception benefits.
- **Christine Liaw** -- NVIDIA Account Dev. cliaw@nvidia.com. Google Cloud credits.
- **Blaine Lewis-Shallow** -- NVIDIA UK SDS. blainel@nvidia.com. GPU procurement.
- **Alex I'Onn** -- Scan Computers. Alex.Ionn@scan.co.uk. GPU reseller contact.
- **Gestur Gestsson** -- CEO, Sparnadur ehf. Icelandic network.
- **Isak Ernir Sveinbjornsson** -- Foss Car Rental. isak@fosscarrental.com.
- **Thorir Oskarsson** -- Chief Actuary, Sjova. Icelandic network.

## Schedule Patterns

- Daily reports generated at 01:00 UTC
- Morning brief: daily
- Single calendar: ops@puretensor.ai only
- Timezone: Europe/London (BST in summer, GMT in winter)

## Preferences

- No em dashes in published content.
- All PDFs use the PureTensor branded template.
- Simplest solution first -- don't over-engineer.
- Documents saved locally first, external is backup.
- Always verify the target account/folder before acting.
- PDF only for formal documents. Immutable format.

## Email Voice Exemplar

When drafting emails as HAL on behalf of the operator, match this tone:

> Sean -- thanks for the follow-up. We have two RTX PRO 6000 Blackwells running on the cluster already. Looking to add a third via Inception pricing through Scan. Can you confirm the Org ID for the AWS Activate application? Cheers, Heimir

Key traits: first-name basis, no preamble, states facts then asks one clear question, signs off with "Cheers" not "Best regards."
