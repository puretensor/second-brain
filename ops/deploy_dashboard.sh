#!/bin/bash
# Deploy pureMind Grafana dashboard to K3s Grafana instance.
#
# Prerequisites:
#   1. PostgreSQL datasource configured in Grafana (name: "pureMind-PG")
#   2. Grafana accessible at fox-n1:30302
#
# Usage:
#   bash ops/deploy_dashboard.sh
#   bash ops/deploy_dashboard.sh --check  # Verify dashboard exists

set -euo pipefail

GRAFANA_URL="http://100.103.248.9:30302"
GRAFANA_AUTH="admin:consort-crazy-curl"
DASHBOARD_FILE="$(dirname "$0")/grafana/puremind-overview.json"

if [[ "${1:-}" == "--check" ]]; then
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
        -u "$GRAFANA_AUTH" \
        "$GRAFANA_URL/api/dashboards/uid/puremind-overview")
    if [[ "$HTTP_CODE" == "200" ]]; then
        echo "Dashboard exists (200 OK)"
        exit 0
    else
        echo "Dashboard not found (HTTP $HTTP_CODE)"
        exit 1
    fi
fi

if [[ ! -f "$DASHBOARD_FILE" ]]; then
    echo "ERROR: Dashboard file not found: $DASHBOARD_FILE"
    exit 1
fi

echo "Deploying pureMind dashboard to $GRAFANA_URL..."

RESPONSE=$(curl -s -w "\n%{http_code}" \
    -u "$GRAFANA_AUTH" \
    -H "Content-Type: application/json" \
    -X POST "$GRAFANA_URL/api/dashboards/db" \
    -d @"$DASHBOARD_FILE")

HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | head -n -1)

if [[ "$HTTP_CODE" == "200" ]]; then
    echo "Dashboard deployed successfully"
    echo "$BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'  URL: $GRAFANA_URL{d.get(\"url\", \"/d/puremind-overview\")}')" 2>/dev/null || true
else
    echo "ERROR: Deploy failed (HTTP $HTTP_CODE)"
    echo "$BODY"
    exit 1
fi
