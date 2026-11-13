#!/usr/bin/env python3
"""Load srcdb.public.production_orders (2M rows) once into a month-partitioned Iceberg table on MinIO.

Source: seatunnel project's Postgres (localhost:5440). Target: iceberg_s3.retail_s3.production_orders.
The table is created first by PrepareRetailS3Catalog.java (month(order_date), no identifier field),
then SeaTunnel appends. Verified with source aggregates; identical data skips, anything else stops.
Requires SOURCE_USER / SOURCE_PASSWORD. Details: tasks/003-production-orders-to-minio.md
"""
from datetime import datetime, timezone
import csv
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent / 'src'))

from public_api import weather  # noqa: E402

ROOT = weather.ROOT
EVIDENCE = ROOT / 'evidence/minio-production-orders'
LOCK = EVIDENCE / '.lock'
SOURCE_CONTAINER = 'seatunnel_practice_postgres'
TARGET = 'iceberg_s3.retail_s3.production_orders'
LOCATION = 's3a://lakehouse/warehouse/retail_s3.db/production_orders'
EXPECTED_SPEC = '[order_date_month:month(5)]'

# 같은 별칭·같은 의미의 집계를 원본(PostgreSQL)과 대상(Trino)에서 각각 실행해 문자열로 비교한다.
SUMMARY = """SELECT count(*) AS row_count, count(DISTINCT order_id) AS distinct_ids,
  min(order_id) AS min_id, max(order_id) AS max_id, sum(order_id) AS sum_id,
  sum({qty}) AS sum_quantity, min(order_date) AS min_date, max(order_date) AS max_date,
  sum(length(factory_id)) AS len_factory, sum(length(product_name)) AS len_product, sum(length(status)) AS len_status,
  count(*) FILTER (WHERE factory_id IS NULL OR product_name IS NULL OR quantity IS NULL
                   OR order_date IS NULL OR status IS NULL) AS null_rows
FROM {table}"""
BY_MONTH = """SELECT {month} AS month, count(*) AS row_count, sum({qty}) AS sum_quantity
FROM {table} GROUP BY 1 ORDER BY 1"""
BY_STATUS = 'SELECT status, count(*) AS row_count FROM {table} GROUP BY 1 ORDER BY 1'
PG = {'table': 'public.production_orders', 'qty': 'quantity::bigint', 'month': "to_char(order_date, 'YYYY-MM')"}
TRINO = {'table': TARGET, 'qty': 'CAST(quantity AS bigint)', 'month': "date_format(order_date, '%Y-%m')"}


def source_query(sql):
    # PGPASSWORD는 값 없이 이름만 넘겨 호출한 셸의 환경변수를 그대로 쓴다 (명령줄에 비밀번호를 남기지 않는다).
    result = subprocess.run(['docker', 'exec', '-e', 'PGPASSWORD', SOURCE_CONTAINER, 'psql', '-X', '--csv',
                             '-v', 'ON_ERROR_STOP=1', '-U', os.environ['SOURCE_USER'], '-d', 'srcdb', '-c', sql],
                            env={**os.environ, 'PGPASSWORD': os.environ['SOURCE_PASSWORD']},
                            check=True, capture_output=True, text=True)
    return list(csv.DictReader(io.StringIO(result.stdout)))


def aggregates(run, params):
    return {name: run(sql.format(**params))
            for name, sql in (('summary', SUMMARY), ('by_month', BY_MONTH), ('by_status', BY_STATUS))}


def table_state(out, name):
    with (out / f'{name}.log').open('w') as log:
        result = subprocess.run(weather.COMPOSE + ['run', '--rm', '--no-deps', '--entrypoint', 'sh', 'seatunnel',
                                                   '/lab/scripts/prepare-retail-s3-catalog.sh', 'check'],
                                cwd=ROOT, check=True, capture_output=True, text=True)
        log.write(result.stdout + result.stderr)
    line = next(l for l in result.stdout.splitlines() if l.startswith('STATE '))
    return json.loads(line[len('STATE '):])


def run(out, name, args, compose_extra=()):
    with (out / f'{name}.log').open('w') as log:
        subprocess.run(weather.COMPOSE + list(compose_extra) + ['run', '--rm', '--no-deps'] + args,
                       cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)


def lake_fingerprint():
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((ROOT / 'lake').rglob('*')) if p.is_file()}


def existing_checks():
    return {
        'orders': weather.query('SELECT count(*) AS n, sum(amount) AS amount FROM iceberg.retail.orders'),
        'weather_minio': weather.query('SELECT count(*) AS n FROM iceberg_s3.public_api_s3.weather_hourly'),
    }


def main():
    for key in ('SOURCE_USER', 'SOURCE_PASSWORD'):
        if not os.environ.get(key):
            sys.exit(f'{key} 환경변수가 필요합니다.')
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    # 이 래퍼의 동시 실행 방지. 비정상 종료로 남았다면 실행 중인 적재가 없는지 확인 후 직접 지운다.
    lock = os.open(LOCK, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    out = EVIDENCE / run_id
    out.mkdir()
    report = {'run_id': run_id, 'status': 'STARTED', 'target': TARGET}
    try:
        lake_before = lake_fingerprint()
        report['existing_before'] = existing_checks()
        expected = aggregates(source_query, PG)
        report['source'] = expected

        state = table_state(out, 'check-before')
        report['table_before'] = state
        if not state['exists']:
            run(out, 'create', ['--entrypoint', 'sh', 'seatunnel', '/lab/scripts/prepare-retail-s3-catalog.sh', 'create'])
            state = table_state(out, 'check-created')
        if state['spec'] != EXPECTED_SPEC or state['identifier_fields'] != 0 or state['location'] != LOCATION:
            raise ValueError(f'Unexpected table definition: {state}. Not loading.')
        if not state['has_snapshot']:
            report['action'] = 'LOAD'
        elif aggregates(weather.query, TRINO) == expected:
            report['action'] = 'SKIP_IDENTICAL'
        else:
            raise ValueError('Target has data that differs from source. No append performed; inspect manually.')

        if report['action'] == 'LOAD':
            print(f'Loading {expected["summary"][0]["row_count"]} rows; log: {out / "seatunnel.log"}', flush=True)
            started = datetime.now(timezone.utc)
            run(out, 'seatunnel', ['seatunnel', '/jobs/06_production_orders_to_minio_iceberg.conf'],
                compose_extra=('-f', 'compose.bulk.yaml'))
            report['seatunnel_seconds'] = round((datetime.now(timezone.utc) - started).total_seconds(), 1)

        actual = aggregates(weather.query, TRINO)
        report['target'] = actual
        if actual != expected:
            raise ValueError('Post-load aggregate verification failed')
        files = weather.query(f'SELECT file_path, record_count, file_size_in_bytes FROM '
                              f'iceberg_s3.retail_s3."production_orders$files" ORDER BY file_path')
        if not all(f['file_path'].startswith(LOCATION + '/') for f in files):
            raise ValueError(f'Data files are not under {LOCATION}')
        partitions = weather.query('SELECT record_count, file_count FROM iceberg_s3.retail_s3."production_orders$partitions"')
        if sorted(int(p['record_count']) for p in partitions) != sorted(int(m['row_count']) for m in expected['by_month']):
            raise ValueError('Partition row counts do not match monthly source counts')
        report['files'] = {'count': len(files), 'bytes': sum(int(f['file_size_in_bytes']) for f in files),
                           'paths': [f['file_path'][len(LOCATION) + 1:] for f in files]}
        report['partitions'] = len(partitions)
        report['snapshots'] = weather.query('SELECT snapshot_id, operation FROM '
                                            'iceberg_s3.retail_s3."production_orders$snapshots" ORDER BY committed_at')

        # 파티션 효과: 한 달 조건이면 그 달 파일만 읽는지 실제 실행 계획의 입력 행 수로 확인한다.
        plan = weather.query("EXPLAIN ANALYZE SELECT sum(quantity) FROM iceberg_s3.retail_s3.production_orders "
                             "WHERE order_date >= DATE '2026-01-01' AND order_date < DATE '2026-02-01'")
        plan_text = '\n'.join(next(iter(r.values())) for r in plan)
        (out / 'explain-analyze-2026-01.txt').write_text(plan_text)
        # 테이블 스캔 단계 줄만 본다 (집계 단계의 "Input: N rows"와 구분하기 위해 Filtered·Splits가 있는 줄).
        scan = re.search(r'Input: ([\d,]+) rows .*Filtered: .*Splits: (\d+)', plan_text)
        report['pruning'] = {'scan_input_rows': int(scan.group(1).replace(',', '')), 'splits': int(scan.group(2)),
                             'expected_rows': next(int(m['row_count']) for m in expected['by_month'] if m['month'] == '2026-01')}
        if report['pruning']['scan_input_rows'] != report['pruning']['expected_rows']:
            raise ValueError(f'Partition pruning not observed: {report["pruning"]}')

        report['existing_after'] = existing_checks()
        if report['existing_after'] != report['existing_before']:
            raise ValueError('Existing tables changed')
        if lake_fingerprint() != lake_before:
            raise ValueError('Existing ./lake files changed')
        report['lake_files_unchanged'] = len(lake_before)
        report['status'] = 'PASS'
    except Exception as exc:
        report['status'] = 'FAILED'
        report['error'] = str(exc)
        raise
    finally:
        (out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print(f'Report: {out / "report.json"}', flush=True)
        os.close(lock)
        LOCK.unlink()
    print(json.dumps({'status': report['status'], 'action': report['action'],
                      'rows': int(report['target']['summary'][0]['row_count']),
                      'files': report['files']['count'], 'bytes': report['files']['bytes'],
                      'partitions': report['partitions'], 'snapshots': len(report['snapshots']),
                      'pruning': report['pruning']}, indent=2))


if __name__ == '__main__':
    main()
