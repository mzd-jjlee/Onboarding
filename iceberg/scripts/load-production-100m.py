"""1억 행 일회 적재. 테이블 또는 실행 기록이 있으면 자동 재적재하지 않는다."""
from pathlib import Path
from datetime import datetime, timezone
import json
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'evidence/production-100m'
OUT.mkdir(parents=True, exist_ok=True)
for key in ('SOURCE_USER', 'SOURCE_PASSWORD'):
    if not os.environ.get(key):
        sys.exit(f'{key} 환경변수가 필요합니다.')
reuse_empty = sys.argv[1:] == ['--reuse-empty']
if sys.argv[1:] and not reuse_empty:
    sys.exit('지원 옵션: --reuse-empty (미커밋 빈 테이블만 검증 후 재사용)')
base = ['docker', 'compose', '-f', 'compose.yaml', '-f', 'compose.analytics.yaml']
# HMS DB는 읽기만 한다. 오류가 나면 적재를 진행하지 않는다.
sql = """SELECT count(*) FROM "TBLS" t JOIN "DBS" d ON d."DB_ID"=t."DB_ID"
WHERE d."NAME"='retail' AND t."TBL_NAME"='production_orders_100m';"""
check = subprocess.run(base + ['exec', '-T', 'catalog-db', 'psql', '-X', '-U', 'hive',
    '-d', 'metastore', '-At', '-v', 'ON_ERROR_STOP=1', '-c', sql], cwd=ROOT,
    check=True, capture_output=True, text=True)
if check.stdout.strip() != '0' and not reuse_empty:
    sys.exit('대상 테이블이 이미 있습니다. APPEND 재실행을 막았습니다. 기존 실행 결과를 확인하세요.')
target = ROOT / 'lake/warehouse/retail.db/production_orders_100m_append'
if reuse_empty and any((target / 'data').rglob('*')):
    sys.exit('data 경로에 파일이 있습니다. 자동 재시도하지 않습니다.')
if target.exists() and not reuse_empty:
    sys.exit('대상 경로가 이미 있습니다. 이전 시도의 상태를 먼저 확인하세요.')
marker = OUT / 'load-state.json'
state = {'started_at': datetime.now(timezone.utc).isoformat(), 'status':'RUNNING',
         'table':'iceberg.retail.production_orders_100m', 'parallelism':4}
# 한 번 실행을 시작하면 실패/중단돼도 다음 실행은 중복 방지를 위해 멈춘다.
with marker.open('x') as f:
    json.dump(state, f, indent=2)
try:
    subprocess.run(base + ['run', '--rm', '--no-deps', '--entrypoint', 'sh',
        'seatunnel', '/lab/scripts/prepare-production-catalog.sh'] +
        (['require-empty-append'] if reuse_empty else []), cwd=ROOT, check=True)
    command = base + ['-f', 'compose.bulk.yaml', 'run', '--no-deps',
        '--name', 'iceberg-learning-production-100m-final', 'seatunnel', '/jobs/03_production_orders_100m.conf']
    with (OUT / 'seatunnel.log').open('w') as log:
        result = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
except BaseException as exc:
    state.update(finished_at=datetime.now(timezone.utc).isoformat(), status='INTERRUPTED_OR_FAILED',
                 error_type=type(exc).__name__)
    marker.write_text(json.dumps(state,indent=2)+'\n')
    raise
state.update(finished_at=datetime.now(timezone.utc).isoformat(), exit_code=result.returncode,
             status='SUCCEEDED' if result.returncode==0 else 'FAILED')
marker.write_text(json.dumps(state,indent=2)+'\n')
print(json.dumps(state,indent=2))
sys.exit(result.returncode)
