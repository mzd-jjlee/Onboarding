"""원본 PostgreSQL 집계와 Iceberg의 실제 컬럼 스캔 결과를 대조한다."""
from pathlib import Path
import csv, io, json, subprocess, time
ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'evidence/production-100m'
def query(name,sql):
    started=time.monotonic()
    r=subprocess.run(['bash','scripts/trino.sh','--output-format','CSV_HEADER','--execute',sql],
        cwd=ROOT,check=True,capture_output=True,text=True)
    (OUT/f'{name}.sql').write_text(sql+'\n')
    (OUT/f'{name}.csv').write_text(r.stdout)
    return list(csv.DictReader(io.StringIO(r.stdout))), round(time.monotonic()-started,3)
source=list(csv.DictReader((OUT/'source-summary.csv').open()))
sql=(OUT/'source-summary.sql').read_text().replace('quantity::bigint','CAST(quantity AS bigint)').replace('public.production_orders_100m','iceberg.retail.production_orders_100m')
actual,seconds=query('trino-summary',sql)
assert actual==source, {'source':source,'iceberg':actual}
files,_=query('trino-files','SELECT file_path, record_count, file_size_in_bytes FROM iceberg.retail."production_orders_100m$files" ORDER BY file_path')
assert sum(int(r['record_count']) for r in files)==100_000_000
sample,_=query('trino-sample','SELECT * FROM iceberg.retail.production_orders_100m WHERE order_id IN (1,2,3,50000000,99999999,100000000) ORDER BY order_id')
old,_=query('original-orders','SELECT count(*) AS n, sum(amount) AS amount FROM iceberg.retail.orders')
assert old==[{'n':'5','amount':'170000'}]
report={'status':'PASS','rows':100_000_000,'parquet_files':len(files),
        'parquet_bytes':sum(int(r['file_size_in_bytes']) for r in files),
        'trino_aggregate_seconds_including_cli':seconds,'comparison':'total and per-status count, ID sums/ranges, quantity sums/nulls, date ranges, string lengths; not row-by-row equality',
        'original_orders':old}
(OUT/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
