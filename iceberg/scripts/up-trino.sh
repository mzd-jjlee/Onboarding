#!/usr/bin/env bash
# 기존 HMS와 Trino를 기동한다. SeaTunnel 적재는 실행하지 않는다.
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose -f compose.yaml -f compose.analytics.yaml up -d --wait --wait-timeout 180 trino
