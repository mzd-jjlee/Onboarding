#!/usr/bin/env bash
# 이 파일을 bash 셸로 실행하라는 뜻
set -euo pipefail        # 셸 스크립트의 오류 처리 옵션, 오타가 있어도 계속 실행되는 상황을 줄여준다.
cd "$(dirname "$0")/.."
CONFIG_FILE="${1:?사용법: ./scripts/run-cdc-job.sh <config 파일 경로, 예: jobs/15_postgres_10m_cdc_insert_update.conf>}"  # 첫 번째 인자로 config 파일 받기 (jobs/15_postgres_10m_cdc_insert_update.conf)
CONFIG_NAME="$(basename "$CONFIG_FILE")"  # basename : config 파일 경로에서 파일 이름만 추출 (예: 15_postgres_10m_cdc_insert_update.conf)
JOB_ID="${CONFIG_NAME%.conf}"
CONTAINER_NAME="st_cdc_${JOB_ID}"   # 컨테이너 이름을 config 파일 이름 기반으로 생성 (예: st_cdc_15_postgres_10m_cdc_insert_update)

# 이전에 같은 config로 띄워둔 컨테이너가 남아있으면 정리
docker rm -f "$CONTAINER_NAME" 2>/dev/null || true

# Docker 컨테이너를 백그라운드로 실행한다.
# 아래의 `-v` 옵션은 호스트의 jobs/output 폴더를 컨테이너에 연결한다.
# 각 줄 끝의 `\`는 다음 줄을 같은 docker run 명령으로 이어준다.
# 주석은 `\`로 이어지는 명령 사이에 넣지 않는다.
docker run -d --name "$CONTAINER_NAME" --network seatunnel_default \
  -v "$(pwd)/jobs:/jobs:ro" \
  -v "$(pwd)/output:/output" \
  --entrypoint sh \
  apache/seatunnel:2.3.13 \
  -c "
    mv /opt/seatunnel/lib/opengauss-jdbc-5.1.0.jar /opt/seatunnel/lib/opengauss-jdbc-5.1.0.jar.bak 2>/dev/null || true
    ./bin/seatunnel.sh --config /jobs/$CONFIG_NAME -m local    
  "

echo "CDC 잡 시작됨: $CONTAINER_NAME"
echo "로그 보기:   docker logs -f $CONTAINER_NAME"
echo "잡 종료하기: docker rm -f $CONTAINER_NAME"
