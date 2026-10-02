3-- 자동 생성 파일입니다. 직접 수정하지 말고 generate_seed_sql.py를 다시 실행하세요.
-- source: data/sales_raw.csv, data/customers_raw.csv (etl.py와 동일한 정제 규칙 적용)

CREATE TABLE customers (
    customer      TEXT PRIMARY KEY,
    region        TEXT NOT NULL,
    signup_date   DATE NOT NULL
);

CREATE TABLE sales (
    order_id      INTEGER PRIMARY KEY,
    customer      TEXT NOT NULL REFERENCES customers(customer),
    product       TEXT NOT NULL,
    quantity      INTEGER NOT NULL,
    unit_price    NUMERIC(10, 2) NOT NULL,
    order_date    DATE NOT NULL
);

INSERT INTO customers (customer, region, signup_date) VALUES ('Alice', 'East', '2025-01-01');
INSERT INTO customers (customer, region, signup_date) VALUES ('Bob', 'West', '2025-02-15');
INSERT INTO customers (customer, region, signup_date) VALUES ('Dave', 'South', '2025-03-01');
INSERT INTO sales (order_id, customer, product, quantity, unit_price, order_date) VALUES (1001, 'Alice', 'Widget', 3, 9.99, '2026-01-05');
INSERT INTO sales (order_id, customer, product, quantity, unit_price, order_date) VALUES (1002, 'Bob', 'Gadget', 1, 19.99, '2026-01-06');
INSERT INTO sales (order_id, customer, product, quantity, unit_price, order_date) VALUES (1005, 'Bob', 'Gadget', 2, 19.99, '2026-01-08');
INSERT INTO sales (order_id, customer, product, quantity, unit_price, order_date) VALUES (1008, 'Alice', 'Gadget', 2, 19.99, '2026-01-10');





