"""Read-only checks for the existing five-order lab table through Trino."""
import csv
import io
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'evidence' / 'trino'
OUT.mkdir(parents=True, exist_ok=True)


def query(name, sql):
    result = subprocess.run(
        ['bash', 'scripts/trino.sh', '--output-format', 'CSV_HEADER', '--execute', sql],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    (OUT / f'{name}.csv').write_text(result.stdout)
    (OUT / f'{name}.sql').write_text(sql + '\n')
    return list(csv.DictReader(io.StringIO(result.stdout)))


version = query('version', 'SELECT version() AS version')
tables = query('tables', 'SHOW TABLES FROM iceberg.retail')
assert any('orders' in row.values() for row in tables), tables
rows = query('orders', 'SELECT order_id, customer_name, amount, status FROM iceberg.retail.orders ORDER BY order_id')
expected = [
    ('1001', 'Alice', '12000', 'NEW'), ('1002', 'Bob', '23000', 'DONE'),
    ('1003', 'Carol', '34000', 'DONE'), ('1004', 'Dave', '45000', 'NEW'),
    ('1005', 'Eve', '56000', 'DONE'),
]
assert [tuple(row.values()) for row in rows] == expected, rows
summary = query('summary', 'SELECT count(*) AS row_count, sum(amount) AS total_amount FROM iceberg.retail.orders')
assert summary == [{'row_count': '5', 'total_amount': '170000'}], summary
groups = query('status-totals', 'SELECT status, count(*) AS order_count, sum(amount) AS total_amount FROM iceberg.retail.orders GROUP BY status ORDER BY status')
assert groups == [
    {'status': 'DONE', 'order_count': '3', 'total_amount': '113000'},
    {'status': 'NEW', 'order_count': '2', 'total_amount': '57000'},
], groups
snapshots = query('snapshots', 'SELECT snapshot_id, parent_id, operation FROM iceberg.retail."orders$snapshots" ORDER BY committed_at')
assert len(snapshots) == 2, snapshots
first_id = snapshots[0]['snapshot_id']
assert first_id.isdigit(), first_id
history = query('first-snapshot', f'SELECT count(*) AS row_count, sum(amount) AS total_amount FROM iceberg.retail.orders FOR VERSION AS OF {first_id}')
assert history == [{'row_count': '3', 'total_amount': '69000'}], history
files = query('files', 'SELECT file_path, record_count FROM iceberg.retail."orders$files" ORDER BY file_path')
assert len(files) == 2 and sum(int(row['record_count']) for row in files) == 5, files
report = {'version': version, 'rows': len(rows), 'summary': summary, 'historical': history, 'snapshots': len(snapshots), 'files': len(files), 'status': 'PASS'}
(OUT / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
