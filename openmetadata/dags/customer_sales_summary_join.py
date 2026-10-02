"""customers + sales를 조인해서 파생 테이블 customer_sales_summary를 만드는 데모 DAG.

목적: OpenMetadata Postgres 커넥터가 이 DAG로 새로 생긴 테이블을 카탈로그에
자동으로 잡아내는 것을 보여준다 (DAG 실행 -> retaildb에 테이블 추가 -> OpenMetadata
Ingestion Pipeline 재실행 -> UI에서 customer_sales_summary 확인).

sourcedb-init/01_init.sql과 동일한 스키마(customers.customer, sales.customer)를 기준으로 조인한다.
"""
from datetime import datetime

import psycopg2
from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator

SOURCEDB_CONN = dict(
    host="host.docker.internal",
    port=5432,
    dbname="retaildb",
    user="demo",
    password="demo",
)

BUILD_SUMMARY_SQL = """
DROP TABLE IF EXISTS customer_sales_summary;
CREATE TABLE customer_sales_summary AS
SELECT
    c.customer,
    c.region,
    COUNT(s.order_id)              AS order_count,
    SUM(s.quantity * s.unit_price) AS total_sales
FROM customers c
JOIN sales s ON s.customer = c.customer
GROUP BY c.customer, c.region;
"""


def build_customer_sales_summary():
    conn = psycopg2.connect(**SOURCEDB_CONN)
    try:
        with conn.cursor() as cur:
            cur.execute(BUILD_SUMMARY_SQL)
        conn.commit()
    finally:
        conn.close()


with DAG(
    dag_id="customer_sales_summary_join",
    description="customers + sales 조인 -> customer_sales_summary 테이블 생성 (OpenMetadata 카탈로그 데모)",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["demo", "openmetadata"],
) as dag:
    PythonOperator(
        task_id="build_customer_sales_summary",
        python_callable=build_customer_sales_summary,
    )
