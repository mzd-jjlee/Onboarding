#!/usr/bin/env bash
set -euo pipefail
# Superset 전용 DB의 내부 테이블을 초기화/업그레이드한다.
superset db upgrade
python /lab/scripts/superset_admin.py
superset init
