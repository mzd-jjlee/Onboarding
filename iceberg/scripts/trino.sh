#!/usr/bin/env bash
# 기존 테이블을 SQL로 읽는 CLI. --execute로 SQL을 전달할 수 있다.
set -euo pipefail
cd "$(dirname "$0")/.."
# -T로 파이프 입력 및 결과 파일 저장을 지원한다.
docker compose -f compose.yaml -f compose.analytics.yaml exec -T trino \
  trino --server http://localhost:8080 --user analyst --catalog iceberg --schema retail "$@"
