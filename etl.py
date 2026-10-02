import csv
import sqlite3
from pathlib import Path

RAW_CSV = Path(__file__).parent / "data" / "sales_raw.csv"
CUSTOMERS_CSV = Path(__file__).parent / "data" / "customers_raw.csv"
DB_PATH = Path(__file__).parent / "data" / "sales.db"


def extract(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def transform(rows):
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
            "total": round(quantity * unit_price, 2),
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


def enrich_with_region(sales_rows, customers_rows):
    region_by_customer = {row["customer"]: row["region"] for row in customers_rows}

    enriched = []
    for row in sales_rows:
        enriched.append({
            **row,
            "region": region_by_customer.get(row["customer"], "Unknown"),
        })

    return enriched


def summarize_by_customer(enriched_rows):
    summary = {}

    for row in enriched_rows:
        key = row["customer"]
        if key not in summary:
            summary[key] = {
                "customer": row["customer"],
                "region": row["region"],
                "order_count": 0,
                "total_amount": 0.0,
            }
        summary[key]["order_count"] += 1
        summary[key]["total_amount"] += row["total"]

    for entry in summary.values():
        entry["total_amount"] = round(entry["total_amount"], 2)

    return list(summary.values())


def load_sales(conn, rows):
    conn.execute("DROP TABLE IF EXISTS sales")
    conn.execute("""
        CREATE TABLE sales (
            order_id INTEGER PRIMARY KEY,
            customer TEXT,
            product TEXT,
            quantity INTEGER,
            unit_price REAL,
            total REAL,
            order_date TEXT,
            region TEXT
        )
    """)
    conn.executemany(
        """
        INSERT INTO sales (order_id, customer, product, quantity, unit_price, total, order_date, region)
        VALUES (:order_id, :customer, :product, :quantity, :unit_price, :total, :order_date, :region)
        """,
        rows,
    )


def load_customer_summary(conn, rows):
    conn.execute("DROP TABLE IF EXISTS customer_summary")
    conn.execute("""
        CREATE TABLE customer_summary (
            customer TEXT PRIMARY KEY,
            region TEXT,
            order_count INTEGER,
            total_amount REAL
        )
    """)
    conn.executemany(
        """
        INSERT INTO customer_summary (customer, region, order_count, total_amount)
        VALUES (:customer, :region, :order_count, :total_amount)
        """,
        rows,
    )


def load(sales_rows, summary_rows, db_path):
    conn = sqlite3.connect(db_path)
    load_sales(conn, sales_rows)
    load_customer_summary(conn, summary_rows)
    conn.commit()
    conn.close()


def main():
    raw_sales = extract(RAW_CSV)
    raw_customers = extract(CUSTOMERS_CSV)

    clean_sales = transform(raw_sales)
    clean_customers = transform_customers(raw_customers)

    enriched_sales = enrich_with_region(clean_sales, clean_customers)
    summary = summarize_by_customer(enriched_sales)

    load(enriched_sales, summary, DB_PATH)
    print(f"Loaded {len(enriched_sales)} of {len(raw_sales)} sales rows into {DB_PATH}")
    print(f"Loaded {len(summary)} customer_summary rows")


if __name__ == "__main__":
    main()
