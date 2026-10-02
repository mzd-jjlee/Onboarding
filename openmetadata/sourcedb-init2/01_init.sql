-- sourcedb2 초기 데이터: 제조업 데모 (factories, production_orders)
-- generate_seed_sql.py 같은 생성 스크립트 없이 직접 작성한 파일입니다.
-- 데이터를 바꾸고 싶으면 이 파일을 그냥 직접 수정하세요.

CREATE TABLE factories (
    factory_id       TEXT PRIMARY KEY,
    factory_name     TEXT NOT NULL,
    location         TEXT NOT NULL,
    established_date DATE NOT NULL
);

CREATE TABLE production_orders (
    order_id      INTEGER PRIMARY KEY,
    factory_id    TEXT NOT NULL REFERENCES factories(factory_id),
    product_name  TEXT NOT NULL,
    quantity      INTEGER NOT NULL,
    order_date    DATE NOT NULL
);

INSERT INTO factories (factory_id, factory_name, location, established_date) VALUES
    ('F001', 'Seoul Metal Works', 'Seoul', '2015-03-10'),
    ('F002', 'Busan Auto Parts', 'Busan', '2018-07-22'),
    ('F003', 'Incheon Electronics', 'Incheon', '2020-01-15');

INSERT INTO production_orders (order_id, factory_id, product_name, quantity, order_date) VALUES
    (5001, 'F001', 'Steel Frame', 120, '2026-02-01'),
    (5002, 'F001', 'Steel Frame', 80, '2026-02-15'),
    (5003, 'F002', 'Engine Block', 40, '2026-02-10'),
    (5004, 'F003', 'Circuit Board', 500, '2026-02-20'),
    (5005, 'F002', 'Engine Block', 60, '2026-03-01');
