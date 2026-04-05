#!/bin/bash
# Deploy pureMind Grafana dashboard to the K3s Grafana instance.
#
# Credentials come from env vars or ~/.config/puremind/secrets.env:
#   PUREMIND_GRAFANA_AUTH=admin:...
#   PUREMIND_GRAFANA_URL=http://100.103.248.9:30302
#   PUREMIND_GRAFANA_DATASOURCE=pureMind-PG
#
# Usage:
#   bash ops/deploy_dashboard.sh
#   bash ops/deploy_dashboard.sh --check

set -euo pipefail

SECRETS_FILE="${PUREMIND_SECRETS_FILE:-$HOME/.config/puremind/secrets.env}"
if [[ -f "$SECRETS_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$SECRETS_FILE"
  set +a
fi

GRAFANA_URL="${PUREMIND_GRAFANA_URL:-http://100.103.248.9:30302}"
GRAFANA_AUTH="${PUREMIND_GRAFANA_AUTH:-}"
GRAFANA_DATASOURCE="${PUREMIND_GRAFANA_DATASOURCE:-pureMind-PG}"
DASHBOARD_FILE="$(dirname "$0")/grafana/puremind-overview.json"

if [[ -z "$GRAFANA_AUTH" ]]; then
  echo "ERROR: PUREMIND_GRAFANA_AUTH is not set."
  echo "Set it in the environment or in $SECRETS_FILE"
  exit 1
fi

if [[ ! -f "$DASHBOARD_FILE" ]]; then
  echo "ERROR: Dashboard file not found: $DASHBOARD_FILE"
  exit 1
fi

resolve_datasource_uid() {
  local datasources_json
  datasources_json="$(curl -fsS -u "$GRAFANA_AUTH" "$GRAFANA_URL/api/datasources")"
  DATASOURCES_JSON="$datasources_json" python3 - "$GRAFANA_DATASOURCE" <<'PY'
import json
import os
import sys

target_name = sys.argv[1]
items = json.loads(os.environ["DATASOURCES_JSON"])

def is_pg(item):
    raw = f"{item.get('type', '')} {item.get('name', '')}".lower()
    return "postgres" in raw

for item in items:
    if item.get("name") == target_name:
        print(item.get("uid", ""))
        raise SystemExit(0)

for item in items:
    if is_pg(item):
        print(item.get("uid", ""))
        raise SystemExit(0)

raise SystemExit(1)
PY
}

if [[ "${1:-}" == "--check" ]]; then
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -u "$GRAFANA_AUTH" \
    "$GRAFANA_URL/api/dashboards/uid/puremind-overview")
  if [[ "$HTTP_CODE" == "200" ]]; then
    echo "Dashboard exists (200 OK)"
    exit 0
  fi
  echo "Dashboard not found (HTTP $HTTP_CODE)"
  exit 1
fi

echo "Resolving Grafana datasource..."
DATASOURCE_UID="$(resolve_datasource_uid || true)"
if [[ -z "$DATASOURCE_UID" ]]; then
  echo "ERROR: Could not find PostgreSQL datasource '$GRAFANA_DATASOURCE' at $GRAFANA_URL"
  exit 1
fi

TMP_DASHBOARD="$(mktemp)"
python3 - "$DASHBOARD_FILE" "$TMP_DASHBOARD" "$DATASOURCE_UID" <<'PY'
import json, sys
from pathlib import Path

source = Path(sys.argv[1])
dest = Path(sys.argv[2])
uid = sys.argv[3]

payload = json.loads(source.read_text())
dashboard = payload["dashboard"]

for panel in dashboard.get("panels", []):
    panel["datasource"] = {
        "type": "grafana-postgresql-datasource",
        "uid": uid,
    }

dest.write_text(json.dumps(payload))
PY

echo "Deploying pureMind dashboard to $GRAFANA_URL using datasource UID $DATASOURCE_UID..."
RESPONSE=$(curl -s -w "\n%{http_code}" \
  -u "$GRAFANA_AUTH" \
  -H "Content-Type: application/json" \
  -X POST "$GRAFANA_URL/api/dashboards/db" \
  -d @"$TMP_DASHBOARD")
rm -f "$TMP_DASHBOARD"

HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | head -n -1)

if [[ "$HTTP_CODE" == "200" ]]; then
  echo "Dashboard deployed successfully"
  echo "$BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('url', '/d/puremind-overview'))" 2>/dev/null || true
else
  echo "ERROR: Deploy failed (HTTP $HTTP_CODE)"
  echo "$BODY"
  exit 1
fi
