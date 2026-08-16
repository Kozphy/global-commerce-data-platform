"""Seed a local warehouse with demo e-commerce finance events."""

from __future__ import annotations

from commerce_finance import finance_control_checks, initialize_commerce_finance, reconcile_order
from pipeline.config import get_settings
from pipeline.warehouse import connect, initialize_warehouse


def main() -> None:
    settings = get_settings()
    with connect(settings.duckdb_path) as conn:
        initialize_warehouse(conn)
        initialize_commerce_finance(conn)

        if conn.execute("SELECT COUNT(*) FROM fact_order WHERE order_id = 'ECOM-DEMO-1'").fetchone()[0] == 0:
            conn.execute(
                """
                INSERT INTO fact_order (
                    order_id, customer_id, order_ts, order_date, quantity, unit_price,
                    currency, product_sku, gross_sales, recognized_revenue
                ) VALUES (
                    'ECOM-DEMO-1', 'C001', current_timestamp, current_date,
                    1, 100, 'USD', 'SKU-DEMO', 100, 100
                )
                """
            )

        conn.execute(
            "INSERT OR REPLACE INTO dim_product VALUES ('SKU-DEMO','Demo Product','Demo',100,'USD',TRUE)"
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO fact_payment VALUES
            ('PAY-DEMO-1','ECOM-DEMO-1',current_timestamp,'demo-pay','paid',105,'USD',2.5)
            """
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO fact_tax VALUES
            ('TAX-DEMO-1','ECOM-DEMO-1','US-DEMO','SALES_TAX',100,0.05,5,'USD')
            """
        )

        print(reconcile_order(conn, "ECOM-DEMO-1"))
        print(finance_control_checks(conn))


if __name__ == "__main__":
    main()
