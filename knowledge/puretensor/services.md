---
title: "PureTensor Services"
page_type: entity
status: active
source_refs: []
aliases: [services, service-registry]
updated: 2026-04-06
---

# PureTensor Services Reference

## PureClaw / Nexus -- K3s on fox-n1
- Claude Code CLI backend (Max subscription, Sonnet 4.6 default), OAuth auto-refresh, observer framework
- K3s namespace `nexus`, image `nexus:v2.0.0`, NodePort 30876
- Bot: @hal_claude_bot, channels: Telegram, Discord, Email (IMAP)
- Observers: 11 total (9 cron, 2 persistent) -- email_digest, morning_brief, daily_snippet, bretalon_review, git_push, darwin_consumer, followup_reminder, cyber_threat_feed, intel_deep_analysis, memory_sync, daily_report
- Deploy: `cd ~/nexus && bash k8s/deploy.sh`
- Logs: `ssh fox-n1 'kubectl logs -n nexus deploy/nexus --tail=50'`

## Publisher Service -- K3s on fox-n1
- 3 pods (API, Worker, Researcher) sharing single image `publisher:v1.0.0`
- Namespace `publisher`, NodePort 30877 (API)
- API: FastAPI on :8080
- Worker: Redis consumer, publish pipeline (validate, transform, Imagen 4, WP REST API draft, Telegram approve, publish)
- Researcher: Redis consumer, research pipeline (Gemini Deep Research, Grok 48h, GPT-4.1 write, AI Council)

## vLLM Primary LLM (TC)
- Service: `vllm-nemotron.service` (port 5000)
- Conflicts with Ollama (systemd `Conflicts=ollama.service`)

## Ollama (TC, disabled at boot)
- Start: `sudo systemctl start ollama` (auto-stops vLLM)
- Models: qwen3:30b-a3b (18 GB), glm-ocr (2.2 GB), bge-m3 (1.2 GB), nomic-embed-text (274 MB)
- GPU co-residents: Whisper (2.9G), XTTS (2.4G), Qwen3-TTS (4.8G) -- always resident

## LSearch Telegram Bot (TC)
- Service: lsearch-telegram, bot @lsearch_bot
- Backend: vLLM Qwen3.5-35B-A3B, tools: web_search (SearXNG), fetch_page

## Stripe (TC)
- Webhook service on port 5590
- Products: Discovery ($99), Strategy ($499), Hands-On ($1,999) on puretensor.ai/advisory.html
- Flow: Stripe checkout -> webhook -> TC:5590 (via e2-micro nginx proxy) -> Gmail confirmation

## FOX1 K3s Services (192.168.4.50)
- Storage classes: local-path (default), nfs-nvme (ZFS), cephfs-hdd (EC 3+1 HDD RWX), rbd-ssd (EC 3+1 SSD RWO)
- Services: Nexus(30876), Nextcloud(30880), Vaultwarden(30800), Paperless(30850), MinIO(32000), N8n(30678), OpenSearch(30920), Prometheus-LT(30909), Grafana-LT(30300), Gitea(3002/2222), AdGuard(53/3000)

## Observability
- Primary stack: Grafana, Loki, Prometheus -- all on K3s pods (fox-n1)
- mon2 containers: Prometheus (9090), Alertmanager (9093), Uptime Kuma (3001), telegram-forwarder (8080), node-exporter
- Promtail: 13/13 nodes (v3.6.4)
- Alert rules: 23 Prometheus + 5 Loki log-based

## Backup Infrastructure
- TC restic -> /mnt/ceph-backup/restic-repos/tensor-core. Hourly, ~5GB.
- K3s state -> /mnt/ceph/backups/fox-n1/ (hourly, 48 snapshots)
- rsyncd (200G, boot-enabled): TC 10.200.0.3:873, fox-n0 10.200.0.1:873. Throughput: 8 streams 13 GB/s.

## Yggdrasil VPS (93.95.228.138)
- Ubuntu 22.04, 1 vCPU, 957MB. nginx+certbot+fail2ban.
- Warm standby for Vaultwarden vault tunnel.

## Cloudflare Browser Rendering
- Script: ~/tensor-scripts/integrations/cf_crawl.py
- Working endpoints: markdown, content, links, json, screenshot, pdf, scrape
- Rate limit: ~10 req/min free plan

## Vaultwarden (Public)
- URL: https://vault.puretensor.com
- Routing: Cloudflare Tunnel -> K3s vaultwarden namespace
- Namespace vaultwarden, NodePort 30800, PVC 5Gi local-path
- Registration disabled (invite-only). Backup CronJob every 6h.

## Related

- [[corporate]] -- PureTensor entity and document standards
- [[puremind-architecture]] -- how pureMind uses these services
