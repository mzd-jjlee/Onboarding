SELECT status, count(*) AS order_count, sum(amount) AS total_amount FROM iceberg.retail.orders GROUP BY status ORDER BY status
