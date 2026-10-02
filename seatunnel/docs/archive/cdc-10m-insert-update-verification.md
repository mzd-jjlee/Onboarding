# 1천만 행 테이블 CDC 필터 검증

원본: srcdb.public.cdc_demo_orders. 기존 2행 보존 + 기준 데이터 10,000,000행 = 10,000,002행.

기준 데이터 적재 후 latest 모드로 15번 잡 시작. 초기 1천만 행 복제 성능 테스트가 아님.

검증 ID 30000000~30000149에 INSERT 150, UPDATE 150, DELETE 150 수행(각 SQL은 별도 커밋).

Parquet에서 INSERT/PENDING 150행 + UPDATE_AFTER/SHIPPED 150행 확인. 모든 ID·factory_id·status·cdc_op의 예상 멀티셋과 정확히 일치, 중복 및 누락 없음. UPDATE_BEFORE/DELETE 0행.

결과: {'files': 1, 'rows': 300, 'operations': {'INSERT': 150, 'UPDATE_AFTER': 150}, 'exact_match': True}

15번 CDC 잡 실행 중. 14번 잡은 중지됨. 기존 14번 복제 슬롯은 보존됨.
