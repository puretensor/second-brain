# pureMind -- Durable Knowledge

## Agent Identity

- **HAL** = Heterarchical Agentic Layer. Agentic AI across PureTensor infrastructure.
- **Email accounts:** hal@puretensor.ai (Workspace, primary), hal@puretensor.com (Krakumail, internal), hal@puretensor.org (Workspace), ops@puretensor.ai (operator)
- **Telegram:** @hal_claude_bot (PureClaw, K3s nexus), @lsearch_bot (LSearch, TC), @puretensor_alert_bot (alerts, mon2)
- **Email identities (gmail.py):** hal, hal-krakumail, hal-org, heimir, personal, ops, galactic

## Git & Repos

- **Gitea:** ssh://git@100.92.245.5:2222, HTTP http://100.92.245.5:3002. K3s pod on mon2.
- **GitHub:** puretensor org. 56 repos (55 private, 1 public: nexus).
- **Key repos:** nexus (PureClaw), tensor-scripts (ops tooling), immune (fleet self-healing), bookengine

## Pending Items

See `memory/pending.md` for time-sensitive follow-ups (Google Startups, EUSS, Harrods VAT, third Blackwell, AWS credits). Not loaded into RAM -- check on demand.

## Top Lessons

1. **rsync --delete needs --dry-run first.** Session 63426b08 overwrote varangian.co.uk by deploying without checking existing content.
2. **Quality gates must enforce, not advise.** Advisory gates are useless. If council scores below threshold, abort and alert. Don't send anyway.
3. **Always check documented tools before reaching for MCP.** gmail.py has ALL accounts. Long conversations degrade attention to foundational context.
4. **Quantization kills tool calling.** NVFP4/INT4 corrupts JSON output. For agentic workloads: BF16/FP16 on smaller model.
5. **Same VM does not mean same site.** e2-micro hosts 12 sites in separate webroots. Check which webroot you're targeting.
6. **Never set DNS security policies without asking.** SPF -all + DMARC reject on bretalon.com broke email for 4 days.
7. **CPU offload cliff.** Even 3% CPU offload costs ~40% gen speed. Size models to fit 100% in VRAM.

## Infrastructure Quick-Ref

- **K3s:** fox-n1 (192.168.4.50:6443), 9 nodes. Traefik HA (3 replicas).
- **Ceph:** Squid v19.2.3, arx1-4, 170 TiB raw. Storage classes: cephfs-hdd, rbd-ssd.
- **Ray Trinity:** TC + fox-n0 + fox-n1. Head: fox-n1:6380. Dashboard: :8265. 160 CPUs, 2 GPUs, 1.02 TB object store, 200 GbE.
- **Monitoring:** Grafana-LT (K3s 30300), Prometheus-LT (30909), Uptime Kuma (mon1 3001, mon2 3001).
- **pgvector:** K3s databases namespace, NodePort 30433. Extension on rag_vectors DB.
- **GCP ops:** e2-micro (104.196.66.112, 13 static sites) + gcp-medium (34.145.179.226, WordPress).
- **AWS:** Account 427046118972, us-east-1. Bedrock for Claude.
- **Azure:** ops@puretensor.ai, ~$1K credits. tensorforge.store on Blob Storage (NOT GCP).

## Tool Manifest

- **Email:** `~/nexus/tools/gmail.py {account} {command}` -- all 6 accounts
- **Drive:** `~/nexus/tools/gdrive.py {ops|personal} {command}`
- **Admin:** `~/nexus/tools/gadmin.py ops {command}`
- **Deploy:** `~/tensor-scripts/deploy/deploy-site.sh <domain>`
- **PDF template:** `~/tensor-scripts/templates/puretensor_doc_template.py`
- **X/Twitter:** `~/tensor-scripts/x_post.py` (personal), `~/tensor-scripts/x_company.py` (company)
- **Power:** `pwake/psleep <node>`, `pwake-tier/psleep-tier <0|1|2|4>`
- **Crawl:** `~/tensor-scripts/integrations/cf_crawl.py`
- **Ray:** `/opt/ray-env/bin/python`, `ray.init(address='10.200.0.2:6380')`

## Corporate

- **US:** PureTensor, Inc. Delaware C-corp, EIN 30-1474565. 131 Continental Dr, Suite 305, Newark, DE 19713.
- **UK:** PureTensor Ltd. Company 16957867. Director: Heimir Helgason. VAT: 514 7995 57 (effective 12 Jan 2026).

## Cloudflare Zones

11 domains: alanapter.com, bretalon.com, krakumail.com, nesdia.com, pureclaw.ai, puretensor.ai/.com/.org, varangian.ai/.co.uk
