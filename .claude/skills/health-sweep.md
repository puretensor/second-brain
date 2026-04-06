---
name: health-sweep
description: Comprehensive fleet health sweep with parallel per-node deep checks and targeted diagnostics
inputs: [node_filter, tier_filter]
outputs: [health_report]
writes_to: []
side_effects: [fleet_ssh_reads, audit_log]
---

# Fleet Health Sweep

Comprehensive infrastructure health check across the PureTensor sovereign compute cluster. Runs deep checks on all nodes with role-specific diagnostics (K3s pods, Ceph health, Docker containers, failed systemd units).

More thorough than the heartbeat's quick check (which runs every 30 min and must complete in <30s). This skill can take 2-3 minutes for a full sweep.

## Steps

### 1. Run deep fleet health check

```bash
python3 ~/pureMind/.claude/integrations/fleet_health_integration.py deep_check --json
```

Or for a single node:
```bash
python3 ~/pureMind/.claude/integrations/fleet_health_integration.py deep_check --node fox-n1 --json
```

### 2. Parse results and identify degraded nodes

From the JSON output, identify any nodes with `status != "healthy"`. Group by tier:
- **Tier 0** (tensor-core): GPU bridge, control node
- **Tier 1** (fox-n0, fox-n1): Compute and K3s control plane
- **Tier 2** (arx1-4): Ceph storage
- **Tier 3** (mon1-3): Monitoring and infrastructure

### 3. For degraded nodes, run targeted diagnostics

Spawn an Agent sub-agent per degraded node for deeper investigation. Each sub-agent should SSH to the node and run:

```bash
# Recent errors
ssh root@<ip> 'journalctl --priority=err --since "1 hour ago" --no-pager | tail -20'
# Kernel messages
ssh root@<ip> 'dmesg --time-format iso | tail -15'
# Failed systemd units with details
ssh root@<ip> 'systemctl --failed --no-pager; for u in $(systemctl --failed --no-legend --no-pager | awk "{print \$1}"); do echo "--- $u ---"; systemctl status "$u" --no-pager | tail -10; done'
```

Note: tensor-core SSH user is `puretensorai`, all others are `root`.
Note: mon3 is ARM64 (Raspberry Pi 5) -- some commands may differ.

### 4. Check Ceph cluster health (if arx nodes are involved)

```bash
ssh root@100.118.169.103 'ceph health detail; ceph osd tree; ceph df'
```

### 5. Check vault for known issues

```bash
python3 ~/pureMind/tools/search.py "fleet health degraded node issue" --limit 3
```

### 6. Synthesise report

Present a structured report:

```
## Fleet Health Sweep -- <timestamp>

### Summary
- Total nodes: N
- Healthy: N | Degraded: N | Unreachable: N
- Elapsed: Ns

### Tier 0 -- Bridge
| Node | Status | Load | Disk | Notes |
...

### Tier 1 -- Engine Room
...

### Tier 2 -- Memory Banks (Ceph)
| Ceph Health | OSD Status | Pool Usage |
...

### Tier 3 -- Infrastructure
...

### Alerts
- <list of active alerts>

### Recommendations
- <actionable items based on findings>
```

### 7. Optional: post summary to Telegram

```bash
python3 ~/pureMind/.claude/integrations/telegram_integration.py post_alert "Fleet sweep: N/N healthy, N alerts"
```

## Constraints

- **Read-only.** No remediation actions. Flag issues for operator decision.
- All SSH and integration calls logged to pm_audit via @audited decorator.
- Does NOT wake sleeping nodes. Only checks nodes that are currently reachable.
- ARM64 awareness: mon3 is a Raspberry Pi 5. Some x86-specific commands may not apply.
- If a node is unreachable, report it but do not attempt to power it on.
