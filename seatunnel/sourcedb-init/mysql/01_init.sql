-- SeaTunnel 실습용 대량 데이터 시드 (MySQL) — 제조업 도메인. Postgres 버전과 동일한 스키마/스토리.
-- generate_series가 없어서 숫자 0~9 헬퍼 테이블을 여러 번 CROSS JOIN해서 큰 시퀀스를 만든다
-- (재귀 CTE보다 대량 생성에 훨씬 빠름).

CREATE TABLE seq_helper (i INT);
INSERT INTO seq_helper VALUES (0),(1),(2),(3),(4),(5),(6),(7),(8),(9);

CREATE TABLE factories (
    factory_id       VARCHAR(10) PRIMARY KEY,
    factory_name     VARCHAR(100) NOT NULL,
    location         VARCHAR(50) NOT NULL,
    established_date DATE NOT NULL
);

-- 30개 공장
INSERT INTO factories (factory_id, factory_name, location, established_date)
SELECT
    CONCAT('F', LPAD(n, 3, '0')),
    CONCAT(ELT(1 + (n MOD 5), 'Metal Works','Auto Parts','Electronics','Precision Tools','Heavy Machinery'), ' #', n),
    ELT(1 + (n MOD 7), 'Seoul','Busan','Incheon','Daegu','Gwangju','Daejeon','Ulsan'),
    DATE_ADD('2010-01-01', INTERVAL FLOOR(RAND()*5000) DAY)
FROM (
    SELECT (a.i + b.i*10) + 1 AS n
    FROM seq_helper a, seq_helper b
) t
WHERE n <= 30;

CREATE TABLE production_orders (
    order_id      BIGINT PRIMARY KEY,
    factory_id    VARCHAR(10),
    product_name  VARCHAR(50),
    quantity      INT,
    order_date    DATE,
    status        VARCHAR(20)   -- CDC 실습용: CREATED -> IN_PROGRESS -> COMPLETED / CANCELLED 전이를 흉내냄
);

-- 200만 행 (7자리 조합 10,000,000개 중 200만개만 사용)
INSERT INTO production_orders (order_id, factory_id, product_name, quantity, order_date, status)
SELECT
    n,
    CONCAT('F', LPAD(1 + (n MOD 30), 3, '0')),
    ELT(1 + (n MOD 10), 'Steel Frame','Engine Block','Circuit Board','Gearbox','Bearing Assembly',
        'Chassis Panel','Wiring Harness','Hydraulic Pump','Piston Ring','Turbine Blade'),
    10 + FLOOR(RAND()*490),
    DATE_SUB(CURDATE(), INTERVAL FLOOR(RAND()*365) DAY),
    ELT(1 + (n MOD 4), 'CREATED','IN_PROGRESS','COMPLETED','CANCELLED')
FROM (
    SELECT (a.i + b.i*10 + c.i*100 + d.i*1000 + e.i*10000 + f.i*100000 + g.i*1000000) + 1 AS n
    FROM seq_helper a, seq_helper b, seq_helper c, seq_helper d, seq_helper e, seq_helper f, seq_helper g
) t
WHERE n <= 2000000;

CREATE INDEX idx_production_orders_factory_id ON production_orders (factory_id);

DROP TABLE seq_helper;

-- CDC(binlog) 읽기에 필요한 권한을 demo 계정에 부여
GRANT SELECT, RELOAD, SHOW DATABASES, REPLICATION SLAVE, REPLICATION CLIENT ON *.* TO 'demo'@'%';
FLUSH PRIVILEGES;
