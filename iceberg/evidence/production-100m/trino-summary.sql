SELECT CASE WHEN GROUPING(status)=1 THEN '__TOTAL__' ELSE status END AS status_group,
       COUNT(*) AS row_count, MIN(order_id) AS min_order_id, MAX(order_id) AS max_order_id,
       SUM(order_id) AS sum_order_id, SUM(CAST(quantity AS bigint)) AS sum_quantity,
       COUNT(*)-COUNT(quantity) AS null_quantity, MIN(order_date) AS min_order_date,
       MAX(order_date) AS max_order_date,
       SUM(length(factory_id)) AS factory_chars, SUM(length(product_name)) AS product_chars
FROM iceberg.retail.production_orders_100m
GROUP BY GROUPING SETS ((), (status))
ORDER BY GROUPING(status) DESC, status;

