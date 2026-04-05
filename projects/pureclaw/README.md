# PureClaw / Nexus

Agentic AI service across Telegram, Discord, and email.

- **Status:** Production
- **Repo:** github:puretensor/PureClaw + gitea:puretensor/nexus
- **Runtime:** K3s on fox-n1, namespace `nexus`, NodePort 30876
- **Owner:** Heimir Helgason

## Architecture

- Claude Code CLI backend (Max subscription, Sonnet 4.6 default)
- Dispatcher + handler pattern. Multi-channel (Telegram, Discord, Email IMAP).
- Observer framework: 11 observers (9 cron, 2 persistent)
- Observers: email_digest, morning_brief, daily_snippet, bretalon_review, git_push, darwin_consumer, followup_reminder, cyber_threat_feed, intel_deep_analysis, memory_sync, daily_report
- Per-sender session continuity. Tool access for research, system checks, web search.

## Key Operations

- Deploy: `cd ~/nexus && bash k8s/deploy.sh`
- Logs: `ssh fox-n1 'kubectl logs -n nexus deploy/nexus --tail=50'`
- Restart: `ssh fox-n1 'kubectl rollout restart deployment/nexus -n nexus'`
