#!/usr/bin/env bash
# OpenMetadata 데모 스택 전체 종료. 기본값은 컨테이너만 내리고 볼륨(=데이터)은 보존한다.
# 데이터까지 지우려면: ./down.sh --volumes
set -euo pipefail
cd "$(dirname "$0")/.."

VOL_FLAG=""
if [[ "${1:-}" == "--volumes" ]]; then
  VOL_FLAG="--volumes"
  echo "==> Stopping and removing containers + volumes (data will be lost)"
else
  echo "==> Stopping and removing containers (volumes kept; pass --volumes to also wipe data)"
fi

# docker compose -f docker-compose.yml down $VOL_FLAG  ## 기존 파일
docker compose -f docker-compose.yml -f docker-compose.dags.yml down $VOL_FLAG # 로컬 dag 경로 포함
docker compose -f docker-compose.sourcedb.yml down $VOL_FLAG
