"""Local Superset: separate metadata DB, synchronous SQL Lab, one web worker."""
import os
from urllib.parse import quote_plus

# 대시보드/연결정보 암호화 키. 재시작할 때도 같은 값을 유지한다.
SECRET_KEY = os.environ['SUPERSET_SECRET_KEY']
# Iceberg 카탈로그 DB가 아니라 Superset 사용자·연결·차트 저장용 DB다.
SQLALCHEMY_DATABASE_URI = (
    'postgresql+psycopg2://superset:'
    + quote_plus(os.environ['POSTGRES_PASSWORD'])
    + '@superset-db:5432/superset'
)
SQLALCHEMY_TRACK_MODIFICATIONS = False
WTF_CSRF_ENABLED = True
# 로컬 동기 조회만 사용한다. 예약 보고서/비동기 worker는 이번 구성에 없다.
FEATURE_FLAGS = {'ALERT_REPORTS': False, 'GLOBAL_ASYNC_QUERIES': False}
SQLLAB_TIMEOUT = 60
SUPERSET_WEBSERVER_TIMEOUT = 120
DATA_CACHE_CONFIG = {'CACHE_TYPE': 'SimpleCache', 'CACHE_DEFAULT_TIMEOUT': 60}
CACHE_CONFIG = {'CACHE_TYPE': 'SimpleCache', 'CACHE_DEFAULT_TIMEOUT': 60}
DEFAULT_TIME_FILTER = 'No filter'
