SELECT count(*) AS row_count, sum(amount) AS total_amount FROM iceberg.retail.orders FOR VERSION AS OF 2162422063555107563
