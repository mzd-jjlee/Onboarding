#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p lake vendor evidence
# HMS → PostgreSQL 연결에 필요한 JDBC 드라이버가 없으면 준비한다.
if [[ ! -s vendor/postgresql.jar ]]; then
 docker run --rm --entrypoint sh -v "$PWD/vendor:/vendor" apache/seatunnel:2.3.13 \
  -c 'cp /opt/seatunnel/lib/postgresql-42.4.3.jar /vendor/postgresql.jar'
fi
# namespace 준비용 Python 실행 이미지를 빌드한다.
docker compose build catalog-tools
# 원본 DB·카탈로그 DB·HMS를 시작한다. 이 명령은 SeaTunnel 적재를 실행하지 않는다.
docker compose up -d source-db catalog-db hms
# HMS가 준비될 때까지 기다린 뒤 retail namespace를 만들고 도구 컨테이너는 종료한다.
docker compose run --rm --no-deps catalog-tools python scripts/prepare_catalog.py