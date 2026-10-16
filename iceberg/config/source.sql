CREATE TABLE orders (
 order_id BIGINT PRIMARY KEY,
 customer_name TEXT NOT NULL,
 amount INTEGER NOT NULL,
 status TEXT NOT NULL,
 batch_id INTEGER NOT NULL
);
INSERT INTO orders VALUES
 (1001,'Alice',12000,'NEW',1),
 (1002,'Bob',23000,'DONE',1),
 (1003,'Carol',34000,'DONE',1),
 (1004,'Dave',45000,'NEW',2),
 (1005,'Eve',56000,'DONE',2);
