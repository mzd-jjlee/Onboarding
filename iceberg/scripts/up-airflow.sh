#!/usr/bin/env bash
# Airflow만 기동한다. 기존 DB/HMS/Trino/Superset 설정과 데이터는 바꾸지 않는다.
# DAG가 Trino를 조회하므로 Trino가 떠 있어야 한다: bash scripts/up-trino.sh
set -euo pipefail
cd "$(dirname "$0")/.."
export LAB_ROOT="$(pwd)"
export DOCKER_SOCKET_GID="$(docker run --rm --entrypoint stat \
  -v /var/run/docker.sock:/var/run/docker.sock apache/airflow:3.3.1 -c %g /var/run/docker.sock)"
docker compose -f compose.yaml -f compose.analytics.yaml -f compose.airflow.yaml \
  up -d --build --wait --wait-timeout 300 airflow
echo "Airflow UI: http://localhost:8082"
