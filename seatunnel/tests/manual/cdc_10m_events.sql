-- jobs/15 CDC가 RUNNING인 상태에서 1회 실행한다.
-- 2026-09-18 시연: 이전 SQL의 30000000·40000000번대 대신 50000000번대를 사용한다.
-- DB 내 해당 PK의 존재 여부는 별도로 확인한다. 이미 사용한 범위라면 새 범위로 바꾼다.
-- psql -v ON_ERROR_STOP=1로 실행한다. 중복 PK가 있으면 INSERT가 실패하며 중단된다.
-- INSERT 200건, UPDATE 100건, DELETE 50건을 각각 별도 트랜잭션으로 발생시킨다.
-- 15번 설정의 예상 Parquet: INSERT 200 + UPDATE_AFTER 100 = 300행.
BEGIN;
INSERT INTO public.cdc_demo_orders(order_id,factory_id,status)
SELECT i,114,'PENDING' FROM generate_series(50000000,50000199) i;
COMMIT;

BEGIN;
UPDATE public.cdc_demo_orders SET status='SHIPPED' WHERE order_id BETWEEN 50000000 AND 50000099;
COMMIT;

BEGIN;
DELETE FROM public.cdc_demo_orders WHERE order_id BETWEEN 50000150 AND 50000199;
COMMIT;
