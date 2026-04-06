---
title: "Lessons Learned"
page_type: overview
status: active
source_refs: []
aliases: [lessons, incident-lessons]
updated: 2026-04-06
---

# Lessons Learned

Prevent repeating mistakes. Each entry is a documented incident with root cause.

## Daily Snippet Pipeline
- Quality gates must enforce, not advise. Advisory gates are useless. If council scores below threshold, abort and alert.
- LLMs backfill titles from stale training data. Prompt must instruct: "do NOT add titles from your knowledge."
- Web-grounded entity verification is essential (Grok or Gemini with Google Search grounding).
- Defence in depth: source fidelity + entity verification + council gate, each independent.

## Publishing & Content
- Bretalon: never two articles same day. Alan reviews via email (full HTML body, no summaries/links).
- Bretalon ticker depends on varangian.ai/api/feed.json -- destroying that file breaks both sites.
- Varangian spear-V is intentional branding. Never remove the arrowhead SVG.

## Deployments & Infrastructure
- Never deploy to a webroot without checking existing content.
- Never rsync --delete when local source is incomplete. Always --exclude=api/ or omit --delete.
- Same VM does not equal same site. e2-micro hosts 12 sites in separate webroots.
- Use CI/CD, not manual SCP. Deploy webhook maps repos to webroots correctly.
- Docker bind mount + sed -i: sed creates new inode. Docker keeps old file. Must restart container.

## DNS & Email
- Always ask before setting security/email policies. SPF -all + DMARC reject broke bretalon.com email for 4 days.
- When migrating DNS to Cloudflare, always migrate MX records.
- Never permanently delete emails. Trash only.
- HAL signs own emails from hal@puretensor.com -- never impersonate Heimir.

## Vendor & Support
- Never contact customer support without explicit user approval.

## Security
- GitHub is public-facing. Never push sensitive artifacts (handwriting, signatures, credentials, personal docs).

## Hardware & BMC
- Never stop pve-cluster on Proxmox. Unmounts /etc/pve/ leading to SSH lockout.
- BMC cold reset won't fix I2C bus lockups. Need full AC power cycle.
- Fox BMCs: -I lanplus (password >16 chars). ARX BMCs: -I lan (IPMI v1.5).
- BIOS upgrades reset everything. Verify governor/EPP, fan control, boot order after update.

## K3s & Networking
- MTU black hole: arx nodes have vmbr0 MTU 9000, fox-n1 vmbr0 is MTU 1500. TLS Client Hello gets silently dropped.
- K3s soft affinity loses to resource scoring. Use requiredDuringScheduling for tier placement.
- mon3 is ARM64 (RPi5). Always add kubernetes.io/arch: amd64 to required affinity.
- AdGuard Home (hostNetwork) port conflicts with Grafana (both use 3000). Never co-locate.

## Services & Ports
- Mandatory service replacement: disable old, stop old, deploy+start new, test, enable new, verify port with ss -tlnp.
- All restart-capable services need crash loop limits (StartLimitIntervalSec=300, StartLimitBurst=5).
- Telegram bot token conflicts: check all nodes + K3s pods + systemd before deploying.
- nexus.service on TC must stay disabled -- would conflict with K3s PureClaw on fox-n1.

## Models & GPU
- Quantization kills tool calling. NVFP4/INT4 corrupts JSON output. BF16/FP16 for agentic.
- CPU offload cliff: even 3% costs ~40% gen speed. Size models to fit 100% in VRAM.
- vLLM --generation-config vllm essential. Without it, model config silently overrides sampling.
- vLLM VLLM_SLEEP_WHEN_IDLE=1 mandatory for TP>1. Workers busy-wait at 99% CPU without it.
- Local LLMs can't do agentic tool calling. Even 35B MoE fails at multi-step. Claude Code is the only reliable backend.
- Always archive models to Ceph before ollama rm.

## Context Discipline
- Always check documented tools in CLAUDE.md/MEMORY.md before reaching for MCP or asking the user.
- Playwright DOM snapshots eat context. Prefer screenshots or targeted code execution.

## Misc
- eBay pricing: never trust "used value" estimates during shortages.
- Internal monitoring is blind to public outages. Use GCP Uptime Checks.
- gmail.py multi-recipient: must .split(',') for RCPT TO.
- Google Drive default: ops account. Never personal.

## Related

- [[services]] -- service registry referenced in many incidents
- [[corporate]] -- naming and comms standards that lessons enforce
