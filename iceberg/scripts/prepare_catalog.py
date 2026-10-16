"""Wait for HMS and create the namespace only; SeaTunnel creates the table."""
import time
from pyiceberg.catalog import load_catalog
for attempt in range(60):
    try:
        # catalog-db에 직접 SQL을 보내지 않고 HMS API에 연결한다.
        cat=load_catalog('hive',type='hive',uri='thrift://hms:9083')
        # namespace는 테이블을 묶는 이름 공간이다: retail.orders의 retail.
        # 새 namespace의 기본 저장 위치만 등록하고, 테이블·데이터는 만들지 않는다.
        # 이미 존재하면 재생성하거나 기존 location을 변경하지 않는다.
        cat.create_namespace_if_not_exists('retail',properties={'location':'file:///lake/warehouse/retail.db'})
        print('HMS ready; retail namespace exists. No table/data was written by PyIceberg.')
        break
    except Exception:
        # 컨테이너 시작 직후 HMS가 아직 요청을 받을 준비가 안 된 경우 등을 재시도한다.
        if attempt==59: raise
        time.sleep(2)
