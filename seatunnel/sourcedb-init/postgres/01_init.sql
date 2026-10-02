-- SeaTunnel 실습용 대량 데이터 시드 (Postgres) — 제조업 도메인.
-- openmetadata/sourcedb-init2/01_init.sql의 factories/production_orders 스키마를 그대로 이어받아
-- 200만 행 규모로 확장했다 (저장소 전체에서 같은 제조 도메인 스토리를 공유하기 위함).
-- FK 제약은 일부러 걸지 않음 — 200만 행 INSERT 중 매번 참조 무결성 검사를 하면 속도가 느려지고
-- 이번 실습(배치/CDC 처리량 체감) 목적에는 불필요한 오버헤드라 뺐다.

CREATE TABLE factories (
    factory_id       TEXT PRIMARY KEY,
    factory_name     TEXT NOT NULL,
    location         TEXT NOT NULL,
    established_date DATE NOT NULL
);

INSERT INTO factories (factory_id, factory_name, location, established_date)
SELECT
    'F' || LPAD(gs::text, 3, '0'),
    (ARRAY['Metal Works','Auto Parts','Electronics','Precision Tools','Heavy Machinery'])[1 + (gs % 5)] || ' #' || gs,
    (ARRAY['Seoul','Busan','Incheon','Daegu','Gwangju','Daejeon','Ulsan'])[1 + (gs % 7)],
    DATE '2010-01-01' + (random() * 5000)::int
FROM generate_series(1, 30) AS gs;

CREATE TABLE production_orders (
    order_id      BIGINT PRIMARY KEY,
    factory_id    TEXT,
    product_name  TEXT,
    quantity      INT,
    order_date    DATE,
    status        TEXT   -- CDC 실습용: CREATED -> IN_PROGRESS -> COMPLETED / CANCELLED 전이를 흉내냄
);

INSERT INTO production_orders (order_id, factory_id, product_name, quantity, order_date, status)
SELECT
    gs,
    'F' || LPAD((1 + (gs % 30))::text, 3, '0'),
    (ARRAY['Steel Frame','Engine Block','Circuit Board','Gearbox','Bearing Assembly',
           'Chassis Panel','Wiring Harness','Hydraulic Pump','Piston Ring','Turbine Blade'])[1 + (gs % 10)],
    10 + (random() * 490)::int,
    CURRENT_DATE - (random() * 365)::int,
    (ARRAY['CREATED','IN_PROGRESS','COMPLETED','CANCELLED'])[1 + (gs % 4)]
FROM generate_series(1, 2000000) AS gs;

CREATE INDEX idx_production_orders_factory_id ON production_orders (factory_id);

-- CDC 실습(logical decoding)을 위해 UPDATE/DELETE 시 이전 값 전체를 WAL에 남기도록 설정
ALTER TABLE factories REPLICA IDENTITY FULL;
ALTER TABLE production_orders REPLICA IDENTITY FULL;
