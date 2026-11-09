"""Open-Meteo archive -> validated CSV -> SeaTunnel Iceberg -> Trino comparison.

Standard library only. Shared by scripts/public_api_weather.py (CLI) and
dags/public_weather_to_iceberg.py (Airflow). Each step reads/writes the run's
report.json so the steps can run in separate processes.
No automatic retry of Iceberg writes.
"""
import contextlib
import csv
from datetime import date, datetime, timedelta, timezone
import fcntl
import hashlib
import io
import json
import math
from pathlib import Path
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen
import uuid

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'data/public-api'
EVIDENCE = ROOT / 'evidence/public-api'
FIELDS = ['city', 'weather_time', 'temperature_2m', 'relative_humidity_2m', 'precipitation']
TABLE = 'iceberg.public_api.weather_hourly'
COMPOSE = ['docker', 'compose', '-f', 'compose.yaml', '-f', 'compose.analytics.yaml']
MAX_DAYS = 31


def api_url(start, end):
    return 'https://archive-api.open-meteo.com/v1/archive?' + urlencode({
        'latitude': 37.5665, 'longitude': 126.9780, 'start_date': str(start),
        'end_date': str(end), 'hourly': ','.join(FIELDS[2:]),
        'timezone': 'Asia/Seoul', 'models': 'era5',
    })


def fetch(url):
    for attempt in range(3):
        try:
            with urlopen(url, timeout=30) as response:
                return response.read()
        except HTTPError as exc:
            if exc.code != 429 and exc.code < 500:
                raise
            if attempt == 2:
                raise
        except (URLError, TimeoutError):
            if attempt == 2:
                raise
        time.sleep(2 ** (attempt + 1))
    raise RuntimeError('API fetch failed')


def normalize(payload, start, end):
    if payload.get('error'):
        raise ValueError(f"API error: {payload.get('reason')}")
    if payload.get('utc_offset_seconds') != 32400:
        raise ValueError('Expected Asia/Seoul UTC+09:00')
    units = payload['hourly_units']
    if any(units.get(k) != v for k, v in {
        'temperature_2m': '°C', 'relative_humidity_2m': '%', 'precipitation': 'mm'
    }.items()):
        raise ValueError('Unexpected measurement units')
    hourly = payload['hourly']
    count = ((end - start).days + 1) * 24
    if any(len(hourly[k]) != count for k in ['time'] + FIELDS[2:]):
        raise ValueError('Missing hours or mismatched array lengths')
    rows = []
    for i, stamp in enumerate(hourly['time']):
        expected = datetime.combine(start, datetime.min.time()) + timedelta(hours=i)
        if datetime.fromisoformat(stamp) != expected:
            raise ValueError('Duplicate, missing, or unordered hourly timestamp')
        values = [hourly[k][i] for k in FIELDS[2:]]
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
            raise ValueError('Null/non-finite measurement: stop before loading')
        temp, humidity, rain = values
        if not 0 <= humidity <= 100 or int(humidity) != humidity or rain < 0:
            raise ValueError('Invalid humidity or precipitation')
        rows.append(['seoul', expected.isoformat(timespec='seconds') + '+09:00',
                     float(temp), int(humidity), float(rain)])
    return rows


def query(sql):
    result = subprocess.run(COMPOSE + ['exec', '-T', 'trino', 'trino', '--server',
        'http://localhost:8080', '--user', 'analyst', '--output-format', 'CSV_HEADER',
        '--execute', sql], cwd=ROOT, check=True, capture_output=True, text=True)
    return list(csv.DictReader(io.StringIO(result.stdout)))


def table_exists():
    return bool(query("SELECT table_name FROM iceberg.information_schema.tables "
                      "WHERE table_schema='public_api' AND table_name='weather_hourly'"))


def to_row(r):
    return [r['city'], r['weather_time'], float(r['temperature_2m']),
            int(r['relative_humidity_2m']), float(r['precipitation'])]


def existing_rows(start, end):
    if not table_exists():
        return []
    result = query(f"SELECT {', '.join(FIELDS)} FROM {TABLE} WHERE city='seoul' "
                   f"AND weather_time >= '{start}T00:00:00+09:00' "
                   f"AND weather_time < '{end + timedelta(days=1)}T00:00:00+09:00' "
                   'ORDER BY weather_time')
    return [to_row(r) for r in result]


def decision(expected, existing):
    if not existing:
        return 'LOAD'
    if existing == expected:
        return 'SKIP_IDENTICAL'
    raise ValueError('Existing range differs or is partially loaded. No append performed; '
                     'inspect evidence and plan a correction explicitly.')


def latest_loaded_date():
    """Last Korean date already in the table, or None if the table is missing/empty."""
    if not table_exists():
        return None
    # weather_time is fixed-format '+09:00' text, so the max string is the latest hour.
    found = query(f"SELECT max(weather_time) AS latest FROM {TABLE} WHERE city='seoul'")
    latest = found[0]['latest'] if found else ''
    return date.fromisoformat(latest[:10]) if latest else None


def plan_window(latest, today, batch_days, lag_days, first_date):
    """Next unloaded range: starts the day after the table's latest date, so runs never overlap.

    ERA5 values arrive about five days late; anything newer than today - lag_days is left
    for a later run. Returns (start, end) or None when nothing new is available yet.
    """
    if not 1 <= batch_days <= MAX_DAYS:
        raise ValueError(f'batch_days must be 1..{MAX_DAYS}')
    start = latest + timedelta(days=1) if latest else first_date
    end = min(start + timedelta(days=batch_days - 1), today - timedelta(days=lag_days))
    return (start, end) if start <= end else None


@contextlib.contextmanager
def staging_lock():
    """Host-local lock for the shared staging CSV. Not shared between host and containers."""
    DATA.mkdir(parents=True, exist_ok=True)
    with (DATA / '.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


@contextlib.contextmanager
def run_report(out):
    """Load report.json, let a step update it, and always write it back (FAILED on error)."""
    report = json.loads((out / 'report.json').read_text())
    try:
        yield report
    except Exception as exc:
        report['status'] = 'FAILED'
        report['error'] = str(exc)
        raise
    finally:
        (out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')


def read_csv_rows(path):
    with path.open(newline='') as stream:
        return [to_row(r) for r in csv.DictReader(stream)]


def new_run(start, end, replay=None, trigger='cli'):
    if not 0 <= (end - start).days < MAX_DAYS:
        raise ValueError(f'Choose an inclusive range of 1 to {MAX_DAYS} days')
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    out = EVIDENCE / run_id
    out.mkdir()
    report = {'run_id': run_id, 'status': 'STARTED', 'trigger': trigger, 'table': TABLE,
              'start': str(start), 'end': str(end),
              'timezone': 'Asia/Seoul', 'model': 'era5',
              'source_url': api_url(start, end),
              'attribution': 'Weather data by Open-Meteo.com (CC BY 4.0)',
              'replay': str(replay) if replay else None}
    (out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(f'Report: {out / "report.json"}', flush=True)
    return out


def collect(out):
    """API (or replay JSON) -> validated weather.csv in the run's evidence folder."""
    with run_report(out) as report:
        start, end = date.fromisoformat(report['start']), date.fromisoformat(report['end'])
        replay = report['replay']
        raw = Path(replay).read_bytes() if replay else fetch(report['source_url'])
        (out / 'response.json').write_bytes(raw)
        report['raw_sha256'] = hashlib.sha256(raw).hexdigest()
        rows = normalize(json.loads(raw), start, end)
        report['expected_rows'] = len(rows)
        with (out / 'weather.csv').open('w', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(FIELDS)
            writer.writerows(rows)
        return len(rows)


def precheck(out):
    """Compare the target range in Iceberg with the CSV: LOAD, SKIP_IDENTICAL, or fail."""
    with run_report(out) as report:
        start, end = date.fromisoformat(report['start']), date.fromisoformat(report['end'])
        report['action'] = decision(read_csv_rows(out / 'weather.csv'), existing_rows(start, end))
        return report['action']


def load(out):
    """Run the SeaTunnel APPEND job only when precheck decided LOAD."""
    with run_report(out) as report:
        if report.get('action') != 'LOAD':
            return report.get('action')
        with staging_lock():
            (DATA / 'weather.csv').write_bytes((out / 'weather.csv').read_bytes())
            with (out / 'catalog.log').open('w') as log:
                subprocess.run(COMPOSE + ['run', '--rm', '--no-deps', 'catalog-tools',
                    'python', 'scripts/prepare-public-api-catalog.py'],
                    cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
            print(f'Loading {report["expected_rows"]} rows; log: {out / "seatunnel.log"}', flush=True)
            with (out / 'seatunnel.log').open('w') as log:
                subprocess.run(COMPOSE + ['run', '--rm', '--no-deps', 'seatunnel',
                    '/jobs/04_public_weather_to_iceberg.conf'],
                    cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
        report['loaded'] = True
        return 'LOAD'


def verify(out):
    """Row-by-row comparison with the CSV, plus snapshot/file/daily summaries."""
    with run_report(out) as report:
        start, end = date.fromisoformat(report['start']), date.fromisoformat(report['end'])
        rows = read_csv_rows(out / 'weather.csv')
        actual = existing_rows(start, end)
        if actual != rows:
            raise ValueError('Post-load row-by-row verification failed')
        report['verified_rows'] = len(actual)
        report['total_rows'] = query(f'SELECT count(*) AS count FROM {TABLE}')
        report['snapshots'] = query('SELECT snapshot_id, operation FROM '
            'iceberg.public_api."weather_hourly$snapshots" ORDER BY committed_at')
        report['files'] = query('SELECT file_path, record_count FROM '
            'iceberg.public_api."weather_hourly$files"')
        report['daily_summary'] = query(f'SELECT CAST(from_iso8601_timestamp(weather_time) AS date) AS day, '
            f'count(*) AS hours, round(avg(temperature_2m), 2) AS avg_temp_c, '
            f'round(sum(precipitation), 2) AS rain_mm FROM {TABLE} '
            f"WHERE city='seoul' AND CAST(from_iso8601_timestamp(weather_time) AS date) BETWEEN DATE '{start}' "
            f"AND DATE '{end}' GROUP BY 1 ORDER BY 1")
        report['status'] = 'PASS'
        return {'status': 'PASS', 'action': report['action'], 'run_id': report['run_id'],
                'start': report['start'], 'end': report['end'], 'rows': len(rows),
                'total_rows': int(report['total_rows'][0]['count'])}
