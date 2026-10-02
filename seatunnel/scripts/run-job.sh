#!/usr/bin/env bash
# SeaTunnel 잡 실행 래퍼. 매번 긴 docker run 커맨드를 치는 대신 이 스크립트를 씀.
#
# 사용법:
#   ./scripts/run-job.sh jobs/01_postgres_to_parquet.conf
#
# 전제:
#   - docker-compose.sourcedb.yml로 띄운 postgres/mysql 컨테이너가 seatunnel_default 네트워크에 떠 있어야 함
#   - config 파일에서 Postgres/MySQL 접속 시 host는 컨테이너 이름(예: postgres)을 써야 함 (localhost 아님)
set -euo pipefail
cd "$(dirname "$0")/.."

CONFIG_FILE="${1:?사용법: ./scripts/run-job.sh <config 파일 경로, 예: jobs/01_postgres_to_parquet.conf>}"
CONFIG_NAME="$(basename "$CONFIG_FILE")"
if [[ ! -f "jobs/$CONFIG_NAME" ]]; then
  echo "설정 파일 없음: jobs/$CONFIG_NAME" >&2
  exit 1
fi
JVM_OPTIONS="$(pwd)/cluster/jvm_client_options"
if [[ ! -f "$JVM_OPTIONS" ]]; then
  echo "JVM 옵션 파일 없음: $JVM_OPTIONS" >&2
  exit 1
fi
# 실행마다 이름을 달리하여 이전 실행의 컨테이너와 로그를 보존한다.
CONTAINER_NAME="st_batch_${CONFIG_NAME%.conf}_$(date +%Y%m%d_%H%M%S)_$$"

# 배치는 끝나면 Exited 상태가 되지만 삭제하지 않아 docker logs로 조회할 수 있다.
docker run -d --name "$CONTAINER_NAME" --network seatunnel_default \
  -v "$(pwd)/jobs:/jobs:ro" \
  -v "$(pwd)/output:/output" \
  -v "$JVM_OPTIONS:/opt/seatunnel/config/jvm_client_options:ro" \
  --entrypoint sh \
  apache/seatunnel:2.3.13 \
  -c "
    mv /opt/seatunnel/lib/opengauss-jdbc-5.1.0.jar /opt/seatunnel/lib/opengauss-jdbc-5.1.0.jar.bak 2>/dev/null || true
    exec ./bin/seatunnel.sh --config \"\$1\" -m local
  " sh "/jobs/$CONFIG_NAME"

echo "컨테이너 시작 요청 완료: $CONTAINER_NAME (잡 성공 여부는 로그에서 확인)"
echo "Local 힙: 초기 1GiB / 최대 3GiB (cluster/jvm_client_options)"
echo "로그 보기: docker logs -f $CONTAINER_NAME"
echo "상태 보기: docker inspect --format '{{json .State}}' $CONTAINER_NAME"
echo "종료 후 정리: docker rm $CONTAINER_NAME"
