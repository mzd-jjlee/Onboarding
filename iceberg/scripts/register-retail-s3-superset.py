"""MinIO용 Trino 연결·200만 행 Dataset·월별 차트를 Superset에 등록하고 조회 결과를 stdout(JSON)으로 낸다.

Superset 컨테이너 안에서 실행: docker compose ... exec -T superset python /lab/scripts/register-retail-s3-superset.py
기존 연결 'Local Iceberg / Trino'(기본 catalog iceberg)와 그 Dataset·대시보드는 건드리지 않는다.
"""
import json, os, sys
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
def ensure(resource,match,payload):
    for row in api('GET',f'/{resource}/',params={'q':json.dumps({'page_size':100})})['result']:
        if all(row.get(k)==v for k,v in match.items()): return row['id']
    return api('POST',f'/{resource}/',json=payload)['id']
CATALOG,SCHEMA,TABLE='iceberg_s3','retail_s3','production_orders'
# 기본 catalog가 iceberg_s3인 연결을 따로 둔다. 기존 연결의 catalog 설정을 바꾸지 않기 위해서다.
db=ensure('database',{'database_name':'MinIO Iceberg / Trino'},{'database_name':'MinIO Iceberg / Trino',
    'sqlalchemy_uri':f'trino://superset@trino:8080/{CATALOG}','expose_in_sqllab':True,'allow_run_async':False,'allow_dml':False})
dataset=ensure('dataset',{'table_name':TABLE,'schema':SCHEMA},{'database':db,'catalog':CATALOG,'schema':SCHEMA,'table_name':TABLE})
metric={'expressionType':'SQL','sqlExpression':'COUNT(*)','label':'Orders','hasCustomLabel':True,'optionName':'metric_orders'}
x_axis={'columnType':'BASE_AXIS','expressionType':'SQL','sqlExpression':'order_date','label':'order_date','timeGrain':'P1M'}
title='MinIO production orders — monthly count'
form={'datasource':f'{dataset}__table','viz_type':'echarts_timeseries_bar','x_axis':'order_date','time_grain_sqla':'P1M',
      'metrics':[metric],'groupby':[],'time_range':'No filter','row_limit':100,'adhoc_filters':[],'show_value':True}
context={'datasource':{'id':dataset,'type':'table'},'queries':[{'columns':[x_axis],'metrics':[metric],'orderby':[[metric,False]],
         'filters':[],'extras':{'having':'','where':''},'row_limit':100,'time_range':'No filter'}],
         'form_data':form,'result_format':'json','result_type':'full'}
chart=ensure('chart',{'slice_name':title},{'slice_name':title,'viz_type':'echarts_timeseries_bar','datasource_id':dataset,
    'datasource_type':'table','params':json.dumps(form),'query_context':json.dumps(context)})
# 차트와 같은 쿼리를 Superset 경유로 실행해 월별 13행·합계 200만을 확인한다.
chart_rows=api('POST','/chart/data',json=context)['result'][0]['data']
totals=api('POST','/sqllab/execute/',json={'database_id':db,'catalog':CATALOG,'schema':SCHEMA,'runAsync':False,'json':True,'queryLimit':10,
    'sql':f'SELECT COUNT(*) AS row_count, SUM(CAST(quantity AS BIGINT)) AS total_quantity FROM {CATALOG}.{SCHEMA}.{TABLE}'})
if totals.get('status')!='success': raise RuntimeError(totals)
report={'database_id':db,'dataset_id':dataset,'chart_id':chart,'chart_url':f'http://localhost:8088/explore/?slice_id={chart}',
        'chart_months':len(chart_rows),'chart_total':sum(r['Orders'] for r in chart_rows),'sqllab_totals':totals['data'][0]}
assert report['chart_months']==13 and report['chart_total']==2000000, report
assert report['sqllab_totals']=={'row_count':2000000,'total_quantity':509812561}, report
json.dump(report,sys.stdout,ensure_ascii=False,indent=2); print()
