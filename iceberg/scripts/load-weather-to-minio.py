#!/usr/bin/env python3
"""Copy one pinned snapshot of the local weather table into an Iceberg table on MinIO.

Source iceberg.public_api.weather_hourly (./lake) is read FOR VERSION AS OF its latest
snapshot, so the daily Airflow append cannot change the copy midway. Target
iceberg_s3.public_api_s3.weather_hourly (s3a://lakehouse/...) is written by SeaTunnel.
Loaded once: identical rows skip, anything else stops before appending.
"""
from datetime import datetime, timezone
import csv
import json
from pathlib import Path
import subprocess
import sys
import uuid

sys.path.append(str(Path(__file__).resolve().parent.parent / 'src'))

from public_api import weather  # noqa: E402

ROOT = weather.ROOT
STAGE = ROOT / 'data/minio-lab'
EVIDENCE = ROOT / 'evidence/minio'
SOURCE = 'iceberg.public_api.weather_hourly'
TARGET = 'iceberg_s3.public_api_s3.weather_hourly'
LOCATION = 's3a://lakehouse/warehouse/public_api_s3.db/'


def rows(table, snapshot=None):
    at = f' FOR VERSION AS OF {snapshot}' if snapshot else ''
    return [weather.to_row(r) for r in weather.query(
        f"SELECT {', '.join(weather.FIELDS)} FROM {table}{at} ORDER BY city, weather_time")]


def target_exists():
    return bool(weather.query("SELECT table_name FROM iceberg_s3.information_schema.tables "
                              "WHERE table_schema='public_api_s3' AND table_name='weather_hourly'"))


def run(out, name, args):
    with (out / f'{name}.log').open('w') as log:
        subprocess.run(weather.COMPOSE + ['run', '--rm', '--no-deps'] + args,
                       cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)


def main():
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    out = EVIDENCE / run_id
    out.mkdir(parents=True)
    report = {'run_id': run_id, 'status': 'STARTED', 'source': SOURCE, 'target': TARGET}
    try:
        snapshot = weather.query(f'SELECT snapshot_id FROM iceberg.public_api."weather_hourly$snapshots" '
                                 'ORDER BY committed_at DESC LIMIT 1')[0]['snapshot_id']
        report['source_snapshot_id'] = snapshot
        expected = rows(SOURCE, snapshot)
        report['expected_rows'] = len(expected)
        with (out / 'weather.csv').open('w', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(weather.FIELDS)
            writer.writerows(expected)

        report['action'] = weather.decision(expected, rows(TARGET) if target_exists() else [])
        if report['action'] == 'LOAD':
            STAGE.mkdir(parents=True, exist_ok=True)
            (STAGE / 'weather.csv').write_bytes((out / 'weather.csv').read_bytes())
            run(out, 'catalog', ['catalog-tools', 'python', 'scripts/prepare-public-api-s3-catalog.py'])
            print(f'Loading {len(expected)} rows; log: {out / "seatunnel.log"}', flush=True)
            run(out, 'seatunnel', ['seatunnel', '/jobs/05_weather_to_minio_iceberg.conf'])

        if rows(TARGET) != expected:
            raise ValueError('Post-load row-by-row verification failed')
        report['files'] = weather.query(f'SELECT file_path, record_count FROM '
                                        f'iceberg_s3.public_api_s3."weather_hourly$files"')
        if not all(f['file_path'].startswith(LOCATION) for f in report['files']):
            raise ValueError(f'Data files are not under {LOCATION}')
        report['snapshots'] = weather.query('SELECT snapshot_id, operation FROM '
            'iceberg_s3.public_api_s3."weather_hourly$snapshots" ORDER BY committed_at')
        report['status'] = 'PASS'
    except Exception as exc:
        report['status'] = 'FAILED'
        report['error'] = str(exc)
        raise
    finally:
        (out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print(f'Report: {out / "report.json"}', flush=True)
    print(json.dumps({'status': 'PASS', 'action': report['action'], 'rows': len(expected),
                      'source_snapshot_id': snapshot, 'table': TARGET}, indent=2))


if __name__ == '__main__':
    main()
