"""query_my_orders must only ever return the verified customer's own rows.

Run: uv run python -m unittest tests.test_query_my_orders
"""

import sqlite3
import unittest
from types import SimpleNamespace

from config import DEFAULT_DB_PATH
from tools.database import query_my_orders

CUSTOMER = "CUST-003"
OTHER_CUSTOMERS_ORDER = "ORD-2023-0006"  # belongs to CUST-019


def run(query: str, customer_id: str | None = CUSTOMER) -> str:
    return query_my_orders.func(query, SimpleNamespace(context={"customer_id": customer_id}))


class OwnDataTest(unittest.TestCase):
    def test_order_count_matches_database(self):
        with sqlite3.connect(DEFAULT_DB_PATH) as conn:
            expected = conn.execute("SELECT COUNT(*) FROM orders WHERE customer_id = ?", (CUSTOMER,)).fetchone()[0]
        self.assertEqual(run("SELECT COUNT(*) FROM orders"), f"COUNT(*)\n{expected}")

    def test_join_with_public_products(self):
        out = run(
            "SELECT p.category, COUNT(*) FROM order_items oi JOIN products p USING(product_id) GROUP BY p.category"
        )
        self.assertNotIn("Error", out)

    def test_cte_over_scoped_views(self):
        self.assertNotIn("Error", run("WITH x AS (SELECT * FROM orders) SELECT COUNT(*) FROM x"))

    def test_only_one_customer_visible(self):
        self.assertEqual(run("SELECT COUNT(DISTINCT customer_id) FROM orders"), "COUNT(DISTINCT customer_id)\n1")
        self.assertEqual(run("SELECT COUNT(*) FROM customers"), "COUNT(*)\n1")


class OtherCustomersTest(unittest.TestCase):
    def test_other_customers_order_is_invisible(self):
        self.assertEqual(run(f"SELECT * FROM orders WHERE order_id = '{OTHER_CUSTOMERS_ORDER}'"), "No rows.")

    def test_bypass_attempts_are_denied(self):
        attempts = [
            "SELECT COUNT(*) FROM main.orders",
            "SELECT email FROM main.customers",
            "SELECT * FROM main.order_items",
            "WITH x AS (SELECT * FROM main.orders) SELECT COUNT(*) FROM x",
            "SELECT COUNT(*) FROM (SELECT customer_id FROM main.orders)",
            "SELECT c.email FROM orders o JOIN main.customers c USING(customer_id)",
            "SELECT sql FROM sqlite_temp_master",
            "SELECT name FROM sqlite_master",
        ]
        for query in attempts:
            with self.subTest(query=query):
                self.assertTrue(run(query).startswith("SQL Error"), run(query))

    def test_no_writes_or_side_channels(self):
        for query in [
            "DELETE FROM orders",
            "UPDATE products SET price = 1",
            "PRAGMA table_info(orders)",
            "ATTACH DATABASE ':memory:' AS x",
            "SELECT 1; DELETE FROM orders",
        ]:
            with self.subTest(query=query):
                self.assertTrue(run(query).startswith("SQL Error"), run(query))

    def test_runaway_query_is_stopped(self):
        out = run("WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c) SELECT COUNT(*) FROM c")
        self.assertEqual(out, "SQL Error: interrupted")


class IdentityTest(unittest.TestCase):
    def test_no_verified_customer(self):
        self.assertTrue(run("SELECT 1", customer_id=None).startswith("Access denied"))

    def test_malformed_customer_id(self):
        self.assertTrue(run("SELECT 1", customer_id="CUST-003' OR '1'='1").startswith("Access denied"))


if __name__ == "__main__":
    unittest.main()
