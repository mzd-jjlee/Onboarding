#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

docker rm -f seatunnel-node1 seatunnel-node2 2>/dev/null || true

for node in seatunnel-node1 seatunnel-node2; do
  docker run -d --name "$node" --network seatunnel_default \
    -v "$(pwd)/cluster/hazelcast.yaml:/opt/seatunnel/config/hazelcast.yaml" \
    -v "$(pwd)/cluster/jvm_options:/opt/seatunnel/config/jvm_options" \
    -v "$(pwd)/output:/output" \
    --entrypoint sh apache/seatunnel:2.3.13 \
    -c '
      mv /opt/seatunnel/lib/opengauss-jdbc-5.1.0.jar /opt/seatunnel/lib/opengauss-jdbc-5.1.0.jar.bak 2>/dev/null || true
      ./bin/seatunnel-cluster.sh
    '
done

echo "노드 기동 중, 클러스터 형성 대기... (최대 90초)"
for i in $(seq 1 45); do
  if docker logs seatunnel-node1 2>&1 | grep -q "Members {size:2"; then
    echo "클러스터 형성 완료:"
    docker logs seatunnel-node1 2>&1 | grep -A4 "Members {size:2" | tail -5
    exit 0
  fi
  sleep 2
done

echo "경고: 90초 안에 클러스터 형성을 확인하지 못했습니다. 'docker logs seatunnel-node1'로 직접 확인하세요." >&2
exit 1
