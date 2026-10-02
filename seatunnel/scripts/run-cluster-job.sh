#!/usr/bin/env bash
# 이 파일을 bash 셸로 실행하라는 뜻
set -euo pipefail        # 오류가 발생하면 즉시 중단하고, 정의되지 않은 변수 사용도 오류로 처리
cd "$(dirname "$0")/.."

# 첫 번째 인자로 실행할 SeaTunnel 설정 파일을 받는다.
# 클러스터 노드는 이 스크립트 실행 전에 ./scripts/start-cluster.sh로 시작되어 있어야 한다.
CONFIG_FILE="${1:?사용법: ./scripts/run-cluster-job.sh <config 파일 경로, 예: jobs/12_postgres_200m_to_parquet_cluster.conf> (사전에 ./scripts/start-cluster.sh 로 노드가 떠 있어야 함)}"
CONFIG_NAME="$(basename "$CONFIG_FILE")"  # 경로에서 파일명만 추출해 컨테이너의 /jobs에서 사용

# 이 컨테이너는 작업을 클러스터에 제출하는 클라이언트 역할이다.
# --rm: SeaTunnel 작업 제출이 끝나면 이 임시 클라이언트 컨테이너를 자동 삭제한다.
# 실제 클러스터 워커 컨테이너(seatunnel-node1, seatunnel-node2)는 삭제하지 않는다.
# 아래의 Hazelcast 클라이언트 설정 파일을 마운트해 실행 중인 클러스터에 접속한다.
# 각 줄 끝의 `\`는 다음 줄을 같은 docker run 명령으로 이어준다.
docker run --rm --network seatunnel_default \
  -v "$(pwd)/jobs:/jobs:ro" \
  -v "$(pwd)/output:/output" \
  -v "$(pwd)/cluster/hazelcast-client.yaml:/opt/seatunnel/config/hazelcast-client.yaml" \
  --entrypoint sh \
  apache/seatunnel:2.3.13 \
  -c "
    # 이미지에 포함된 불필요한 JDBC 드라이버와의 충돌을 피한다.
    mv /opt/seatunnel/lib/opengauss-jdbc-5.1.0.jar /opt/seatunnel/lib/opengauss-jdbc-5.1.0.jar.bak 2>/dev/null || true
    # 작업을 기존 SeaTunnel 클러스터에 제출한다.
    ./bin/seatunnel.sh --config /jobs/$CONFIG_NAME -m cluster
  "
