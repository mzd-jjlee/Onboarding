"""data/*.csv를 정제해 Postgres seed SQL(01_init.sql)로 만든다.

etl.py의 transform()/transform_customers() 정제 규칙(중복 제거, 빈 값 제거)을
그대로 따라서 OpenMetadata 시연용 소스 DB에도 같은 정제 데이터가 들어가게 한다.
CSV(data/sales_raw.csv, data/customers_raw.csv)가 바뀌면 이 스크립트를 다시 실행해
01_init.sql을 재생성한다: python3 generate_seed_sql.py
"""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
RAW_SALES_CSV = ROOT / "data" / "sales_raw.csv"
RAW_CUSTOMERS_CSV = ROOT / "data" / "customers_raw.csv"
OUT_SQL = Path(__file__).parent / "01_init.sql"


def extract(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def transform_sales(rows):
    seen_order_ids = set()
    cleaned = []
    for row in rows:
        order_id = row["order_id"]
        if order_id in seen_order_ids:
            continue
        if not row["customer"] or not row["quantity"]:
            continue
        seen_order_ids.add(order_id)
        quantity = int(row["quantity"])
        unit_price = float(row["unit_price"])
        cleaned.append({
            "order_id": int(order_id),
            "customer": row["customer"],
            "product": row["product"],
            "quantity": quantity,
            "unit_price": unit_price,
            "order_date": row["order_date"],
        })
    return cleaned


def transform_customers(rows):
    seen_customers = set()
    cleaned = []
    for row in rows:
        customer = row["customer"]
        if customer in seen_customers:
            continue
        if not row["region"]:
            continue
        seen_customers.add(customer)
        cleaned.append({
            "customer": customer,
            "region": row["region"],
            "signup_date": row["signup_date"],
        })
    return cleaned


def sql_str(value):
    return "'" + str(value).replace("'", "''") + "'"


def render(sales_rows, customer_rows):
    lines = [
        "-- 자동 생성 파일입니다. 직접 수정하지 말고 generate_seed_sql.py를 다시 실행하세요.",
        "-- source: data/sales_raw.csv, data/customers_raw.csv (etl.py와 동일한 정제 규칙 적용)",
        "",
        "CREATE TABLE customers (",
        "    customer      TEXT PRIMARY KEY,",
        "    region        TEXT NOT NULL,",
        "    signup_date   DATE NOT NULL",
        ");",
        "",
        "CREATE TABLE sales (",
        "    order_id      INTEGER PRIMARY KEY,",
        "    customer      TEXT NOT NULL REFERENCES customers(customer),",
        "    product       TEXT NOT NULL,",
        "    quantity      INTEGER NOT NULL,",
        "    unit_price    NUMERIC(10, 2) NOT NULL,",
        "    order_date    DATE NOT NULL",
        ");",
        "",
    ]

    for row in customer_rows:
        lines.append(
            "INSERT INTO customers (customer, region, signup_date) VALUES "
            f"({sql_str(row['customer'])}, {sql_str(row['region'])}, {sql_str(row['signup_date'])});"
        )

    lines.append("")

    for row in sales_rows:
        lines.append(
            "INSERT INTO sales (order_id, customer, product, quantity, unit_price, order_date) VALUES "
            f"({row['order_id']}, {sql_str(row['customer'])}, {sql_str(row['product'])}, "
            f"{row['quantity']}, {row['unit_price']}, {sql_str(row['order_date'])});"
        )

    lines.append("")
    return "\n".join(lines)


def main():
    raw_sales = extract(RAW_SALES_CSV)
    raw_customers = extract(RAW_CUSTOMERS_CSV)

    clean_customers = transform_customers(raw_customers)
    valid_customers = {row["customer"] for row in clean_customers}
    clean_sales = [row for row in transform_sales(raw_sales) if row["customer"] in valid_customers]

    OUT_SQL.write_text(render(clean_sales, clean_customers), encoding="utf-8")
    print(f"Wrote {len(clean_customers)} customers, {len(clean_sales)} sales rows to {OUT_SQL}")


if __name__ == "__main__":
    main()
