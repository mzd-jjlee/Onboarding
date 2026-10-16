"""기존 Superset에 1억 행 Dataset/저장 SQL을 등록하고 SQL Lab 조회 결과를 남긴다."""
import json, os, time
from pathlib import Path
import requests
s=requests.Session(); base='http://localhost:8088/api/v1'
def api(method,path,**kw):
    r=s.request(method,base+path,timeout=120,**kw)
    if not r.ok: raise RuntimeError(f'{method} {path}: {r.status_code} {r.text[:1200]}')
    return r.json()
token=api('POST','/security/login',json={'username':os.environ['SUPERSET_ADMIN_USERNAME'],
    'password':os.environ['SUPERSET_ADMIN_PASSWORD'],'provider':'db','refresh':True})
s.headers['Authorization']='Bearer '+token['access_token']
s.headers['X-CSRFToken']=api('GET','/security/csrf_token/')['result']
def listing(resource): return api('GET',f'/{resource}/',params={'q':json.dumps({'page_size':100})})['result']
db=next(d['id'] for d in listing('database') if d['database_name']=='Local Iceberg / Trino')
existing=[d for d in listing('dataset') if d['table_name']=='production_orders_100m' and d.get('schema')=='retail']
dataset=existing[0]['id'] if existing else api('POST','/dataset/',json={'database':db,'catalog':'iceberg','schema':'retail','table_name':'production_orders_100m'})['id']
queries={
 'Production 100M - totals':'SELECT COUNT(*) AS row_count, SUM(CAST(quantity AS BIGINT)) AS total_quantity, MIN(order_id) AS min_id, MAX(order_id) AS max_id FROM iceberg.retail.production_orders_100m',
 'Production 100M - by status':'SELECT status, COUNT(*) AS row_count, SUM(CAST(quantity AS BIGINT)) AS total_quantity FROM iceberg.retail.production_orders_100m GROUP BY status ORDER BY status',
 'Production 100M - sample':'SELECT * FROM iceberg.retail.production_orders_100m WHERE order_id BETWEEN 1 AND 100 ORDER BY order_id LIMIT 100',
}
out=Path('/lab/evidence/production-100m');out.mkdir(exist_ok=True)
saved=listing('saved_query'); report={'dataset_id':dataset,'database_id':db,'queries':[]}
for label,sql in queries.items():
    found=next((q for q in saved if q['label']==label),None)
    qid=found['id'] if found else api('POST','/saved_query/',json={'db_id':db,'catalog':'iceberg','schema':'retail','label':label,'sql':sql,'description':'SeaTunnel → Iceberg 100M rows. Read-only SQL.'})['id']
    start=time.monotonic()
    result=api('POST','/sqllab/execute/',json={'database_id':db,'catalog':'iceberg','schema':'retail','sql':sql,'runAsync':False,'json':True,'queryLimit':1000})
    if result.get('status')!='success': raise RuntimeError(result)
    if label.endswith('totals'):
        assert result['data'][0]['row_count']==100000000,result
        assert result['data'][0]['total_quantity']==25500992494,result
    (out/f'sql-{qid}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    report['queries'].append({'label':label,'id':qid,'seconds':round(time.monotonic()-start,3),'returned_rows':len(result['data'])})
    print(label,report['queries'][-1],result['data'][:4])
(out/'setup.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
