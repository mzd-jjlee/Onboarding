#!/usr/bin/env bash
# OpenMetadata 데모 스택 전체 기동: 공식 OpenMetadata 스택 + 소스 Postgres(seed 포함)
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> Regenerating seed SQL from data/*.csv"
python3 sourcedb-init/generate_seed_sql.py

echo "==> Starting source Postgres (retaildb)"
docker compose -f docker-compose.sourcedb.yml up --detach --wait

echo "==> Starting official OpenMetadata stack (mysql, elasticsearch, server, ingestion)"
# docker compose -f docker-compose.yml up --detach ## 기존 파일
docker compose -f docker-compose.yml -f docker-compose.dags.yml up --detach # 로컬 dag 경로 포함

cat <<'EOF'

==> Done.
OpenMetadata UI : http://localhost:8585  (admin@open-metadata.org / admin)
Airflow UI      : http://localhost:8080  (admin / admin)
Source Postgres : localhost:5432  (db=retaildb, user=demo, pass=demo)

OpenMetadata 컨테이너 내부에서 소스 Postgres에 접속할 때는 호스트가 아니라
'host.docker.internal'을 사용하세요 (같은 docker network가 아니라 호스트 포트를 통해 접근합니다).

서버가 완전히 뜨는 데 1~2분 걸릴 수 있습니다. UI가 안 뜨면 잠시 후 새로고침하세요.
EOF