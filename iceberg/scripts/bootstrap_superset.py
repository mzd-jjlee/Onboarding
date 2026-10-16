"""Superset REST API로 로컬 연결·Dataset·차트·대시보드를 한 번 등록한다."""
import json
import os
from pathlib import Path
import requests

BASE = 'http://localhost:8088/api/v1'
s = requests.Session()
def api(method, path, **kwargs):
    r = s.request(method, BASE + path, timeout=120, **kwargs)
    if not r.ok:
        raise RuntimeError(f'{method} {path}: {r.status_code} {r.text[:2000]}')
    return r.json()
login = api('POST', '/security/login', json={
    'username': os.environ['SUPERSET_ADMIN_USERNAME'],
    'password': os.environ['SUPERSET_ADMIN_PASSWORD'], 'provider': 'db', 'refresh': True,
})
s.headers['Authorization'] = 'Bearer ' + login['access_token']
s.headers['X-CSRFToken'] = api('GET', '/security/csrf_token/')['result']
def ensure(resource, key, value, payload):
    rows = api('GET', f'/{resource}/', params={'q': json.dumps({'page_size':100})})['result']
    for row in rows:
        if row.get(key) == value:
            return row['id']
    return api('POST', f'/{resource}/', json=payload)['id']
database = ensure('database', 'database_name', 'Local Iceberg / Trino', {
    'database_name':'Local Iceberg / Trino', 'sqlalchemy_uri':'trino://superset@trino:8080/iceberg',
    'expose_in_sqllab':True, 'allow_run_async':False, 'allow_dml':False,
})
dataset = ensure('dataset', 'table_name', 'orders', {
    'database':database, 'catalog':'iceberg', 'schema':'retail', 'table_name':'orders',
})
metric = {'expressionType':'SIMPLE','column':{'column_name':'amount'},'aggregate':'SUM',
          'label':'Total amount','optionName':'metric_total_amount','hasCustomLabel':True}
charts = []
for title, viz, specific, query in [
    ('Orders — all 5 rows', 'table', {'query_mode':'raw','all_columns':['order_id','customer_name','amount','status'],'order_by_cols':['["order_id", true]']},
     {'columns':['order_id','customer_name','amount','status'],'metrics':[],'orderby':[['order_id',True]]}),
    ('Amount by status', 'echarts_timeseries_bar', {'x_axis':'status','metrics':[metric],'groupby':[],'show_value':True,'orientation':'vertical','x_axis_sort_asc':True},
     {'columns':['status'],'metrics':[metric],'orderby':[[metric,False]]}),
]:
    form = {'datasource':f'{dataset}__table','viz_type':viz,'time_range':'No filter','row_limit':100,'adhoc_filters':[], **specific}
    context = {'datasource':{'id':dataset,'type':'table'},'queries':[{'filters':[],'extras':{'having':'','where':''},'row_limit':100,'time_range':'No filter',**query}], 'form_data':form,'result_format':'json','result_type':'full'}
    chart = ensure('chart','slice_name',title,{'slice_name':title,'viz_type':viz,'datasource_id':dataset,'datasource_type':'table','params':json.dumps(form),'query_context':json.dumps(context)})
    charts.append((chart,title,context))
layout = {'DASHBOARD_VERSION_KEY':'v2', 'ROOT_ID':{'id':'ROOT_ID','type':'ROOT','children':['GRID_ID']},
          'GRID_ID':{'id':'GRID_ID','type':'GRID','children':['ROW-1'],'parents':['ROOT_ID']},
          'ROW-1':{'id':'ROW-1','type':'ROW','children':[],'parents':['ROOT_ID','GRID_ID'],'meta':{'background':'BACKGROUND_TRANSPARENT'}}}
for chart,title,_ in charts:
    key = f'CHART-{chart}'
    layout['ROW-1']['children'].append(key)
    layout[key] = {'id':key,'type':'CHART','children':[],'parents':['ROOT_ID','GRID_ID','ROW-1'],'meta':{'chartId':chart,'width':6,'height':60,'sliceName':title}}
dashboard = ensure('dashboard','slug','local-iceberg',{'dashboard_title':'Local Iceberg — Orders','slug':'local-iceberg','published':True,'position_json':json.dumps(layout),'json_metadata':json.dumps({'refresh_frequency':0,'color_scheme':'supersetColors'})})
for chart,_,_ in charts:
    existing = api('GET',f'/chart/{chart}')['result']
    ids = [d['id'] for d in existing.get('dashboards',[])]
    if dashboard not in ids:
        api('PUT',f'/chart/{chart}',json={'dashboards':ids+[dashboard]})
# 실제 Superset → Trino → Iceberg 조회 결과를 비밀정보 없이 남긴다.
evidence = Path('/lab/evidence'); evidence.mkdir(parents=True,exist_ok=True)
for chart,title,context in charts:
    result = api('POST','/chart/data',json=context)
    (evidence / f'chart-{chart}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(title, result['result'][0].get('data'))
summary = {'superset_version':'6.0.0','database_id':database,'dataset_id':dataset,'dashboard_id':dashboard,'dashboard_url':'http://localhost:8088/superset/dashboard/local-iceberg/','chart_ids':[c[0] for c in charts]}
(evidence / 'setup.json').write_text(json.dumps(summary,indent=2))
print(json.dumps(summary,indent=2))
sql = 'SELECT COUNT(*) AS order_count, SUM(amount) AS total_amount FROM iceberg.retail.orders'
result = api('POST','/sqllab/execute/',json={'database_id':database,'catalog':'iceberg','schema':'retail','sql':sql,'runAsync':False,'json':True,'queryLimit':100})
(evidence / 'sql-lab.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print('SQL Lab:',result.get('data'))
