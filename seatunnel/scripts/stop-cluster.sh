#!/usr/bin/env bash
set -euo pipefail
docker rm -f seatunnel-node1 seatunnel-node2 2>/dev/null || true
echo "cluster 노드 정리 완료"
