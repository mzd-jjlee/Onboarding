#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 scripts/prepare_superset_env.py
compose=(docker compose -f compose.yaml -f compose.analytics.yaml)
"${compose[@]}" build superset
"${compose[@]}" run --rm superset-init
"${compose[@]}" up -d --wait --wait-timeout 180 superset
"${compose[@]}" exec -T superset python /lab/scripts/bootstrap_superset.py
