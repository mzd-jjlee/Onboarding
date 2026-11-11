#!/usr/bin/env bash
# MinIO를 띄우고 bucket을 만든 뒤, .env.minio와 S3 설정을 읽도록 HMS·Trino를 다시 만든다.
# HMS 등록 정보는 catalog-db 볼륨에 있어 유지된다. 적재는 하지 않는다.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 scripts/prepare_minio_env.py
compose=(docker compose -f compose.yaml -f compose.analytics.yaml -f compose.minio.yaml)
"${compose[@]}" up -d minio
"${compose[@]}" run --rm minio-init
"${compose[@]}" up -d --wait --wait-timeout 180 hms trino
echo 'MinIO console: http://localhost:9001 (login: .env.minio MINIO_ROOT_USER / MINIO_ROOT_PASSWORD)'
