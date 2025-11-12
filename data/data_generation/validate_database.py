#!/usr/bin/env python3
"""
Validate TechHub SQLite database.

Comprehensive validation checks from full_project_plan.md lines 1428-1486:
- Record counts
- Foreign key integrity
- Date logic
- Status distributions
- Order totals
- Query performance
"""

import sqlite3
import time
from pathlib import Path

# Configuration
DATA_DIR = Path(__file__).parent.parent / "data" / "structured"
DB_PATH = DATA_DIR / "techhub.db"


def connect_database():
    """Connect to database with foreign keys enabled."""
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def validate_record_counts(cursor):
    """Validate record counts match expectations."""
    print("\n" + "=" * 60)
    print("RECORD COUNT VALIDATION")
    print("=" * 60)

    expected = {
        "customers": 50,
        "products": 25,
        "orders": 250,
        "order_items": (420, 600),  # Range
    }

    for table, expected_count in expected.items():
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        actual = cursor.fetchone()[0]

        if isinstance(expected_count, tuple):
            min_count, max_count = expected_count
            status = "✓" if min_count <= actual <= max_count else "✗"
            print(f"{status} {table}: {actual} (expected: {min_count}-{max_count})")
            assert min_count <= actual <= max_count, f"{table} count out of range"
        else:
            status = "✓" if actual == expected_count else "✗"
            print(f"{status} {table}: {actual} (expected: {expected_count})")
            assert actual == expected_count, f"{table} count mismatch"


def validate_foreign_keys(cursor):
    """Validate no orphaned records."""
    print("\n" + "=" * 60)
    print("FOREIGN KEY INTEGRITY")
    print("=" * 60)

    # Check orders reference valid customers
    cursor.execute(
        """
        SELECT COUNT(*) 
        FROM orders 
        WHERE customer_id NOT IN (SELECT customer_id FROM customers)
    """
    )
    orphaned_orders = cursor.fetchone()[0]
    print(
        f"{'✓' if orphaned_orders == 0 else '✗'} Orders with invalid customer_id: {orphaned_orders}"
    )
    assert orphaned_orders == 0, "Found orphaned orders"

    # Check order_items reference valid orders
    cursor.execute(
        """
        SELECT COUNT(*) 
        FROM order_items 
        WHERE order_id NOT IN (SELECT order_id FROM orders)
    """
    )
    orphaned_items_orders = cursor.fetchone()[0]
    print(
        f"{'✓' if orphaned_items_orders == 0 else '✗'} Order items with invalid order_id: {orphaned_items_orders}"
    )
    assert orphaned_items_orders == 0, "Found order items with invalid order_id"

    # Check order_items reference valid products
    cursor.execute(
        """
        SELECT COUNT(*) 
        FROM order_items 
        WHERE product_id NOT IN (SELECT product_id FROM products)
    """
    )
    orphaned_items_products = cursor.fetchone()[0]
    print(
        f"{'✓' if orphaned_items_products == 0 else '✗'} Order items with invalid product_id: {orphaned_items_products}"
    )
    assert orphaned_items_products == 0, "Found order items with invalid product_id"


def validate_date_logic(cursor):
    """Validate date relationships."""
    print("\n" + "=" * 60)
    print("DATE LOGIC VALIDATION")
    print("=" * 60)

    # Check shipped_date >= order_date
    cursor.execute(
        """
        SELECT COUNT(*) 
        FROM orders 
        WHERE shipped_date IS NOT NULL 
        AND shipped_date < order_date
    """
    )
    invalid_dates = cursor.fetchone()[0]
    print(
        f"{'✓' if invalid_dates == 0 else '✗'} Orders with shipped_date < order_date: {invalid_dates}"
    )
    assert invalid_dates == 0, "Found orders with invalid date logic"

    # Check processing/cancelled orders have no shipped_date
    cursor.execute(
        """
        SELECT COUNT(*) 
        FROM orders 
        WHERE status IN ('Processing', 'Cancelled')
        AND shipped_date IS NOT NULL
    """
    )
    invalid_processing = cursor.fetchone()[0]
    print(
        f"{'✓' if invalid_processing == 0 else '✗'} Processing/Cancelled orders with shipped_date: {invalid_processing}"
    )
    assert (
        invalid_processing == 0
    ), "Processing/Cancelled orders should not have shipped_date"


def validate_status_distribution(cursor):
    """Validate order status distribution."""
    print("\n" + "=" * 60)
    print("STATUS DISTRIBUTION VALIDATION")
    print("=" * 60)

    cursor.execute(
        """
        SELECT status, 
               COUNT(*) as count,
               ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM orders), 1) as percentage
        FROM orders
        GROUP BY status
        ORDER BY count DESC
    """
    )

    expected_ranges = {
        "Delivered": (70, 90),
        "Shipped": (5, 20),
        "Processing": (0, 15),
        "Cancelled": (0, 5),
    }

    print("\nStatus Distribution:")
    for status, count, percentage in cursor.fetchall():
        min_pct, max_pct = expected_ranges.get(status, (0, 100))
        status_ok = min_pct <= percentage <= max_pct
        symbol = "✓" if status_ok else "✗"
        print(
            f"  {symbol} {status}: {count} ({percentage}%) [expected: {min_pct}-{max_pct}%]"
        )
        assert status_ok, f"{status} percentage {percentage}% outside expected range"


def validate_order_totals(cursor):
    """Validate order totals match line items."""
    print("\n" + "=" * 60)
    print("ORDER TOTAL VALIDATION")
    print("=" * 60)

    cursor.execute(
        """
        SELECT o.order_id, 
               o.total_amount as stored_total,
               ROUND(COALESCE(SUM(oi.quantity * oi.price_per_unit), 0), 2) as calculated_total,
               ABS(o.total_amount - COALESCE(SUM(oi.quantity * oi.price_per_unit), 0)) as difference
        FROM orders o
        LEFT JOIN order_items oi ON o.order_id = oi.order_id
        GROUP BY o.order_id, o.total_amount
        HAVING difference > 0.02
    """
    )

    mismatches = cursor.fetchall()
    print(
        f"{'✓' if len(mismatches) == 0 else '✗'} Orders with total mismatches: {len(mismatches)}"
    )

    if mismatches:
        print("\nMismatched orders:")
        for order_id, stored, calculated, diff in mismatches[:5]:
            print(
                f"  {order_id}: stored=${stored}, calculated=${calculated}, diff=${diff}"
            )

    assert len(mismatches) == 0, "Found orders with total mismatches"


def validate_cancelled_orders(cursor):
    """Validate cancelled orders have no items and zero total."""
    print("\n" + "=" * 60)
    print("CANCELLED ORDERS VALIDATION")
    print("=" * 60)

    # Check cancelled orders have no items
    cursor.execute(
        """
        SELECT COUNT(DISTINCT oi.order_id)
        FROM order_items oi
        JOIN orders o ON oi.order_id = o.order_id
        WHERE o.status = 'Cancelled'
    """
    )
    cancelled_with_items = cursor.fetchone()[0]
    print(
        f"{'✓' if cancelled_with_items == 0 else '✗'} Cancelled orders with items: {cancelled_with_items}"
    )
    assert cancelled_with_items == 0, "Cancelled orders should not have items"

    # Check cancelled orders have zero total
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM orders
        WHERE status = 'Cancelled'
        AND total_amount != 0
    """
    )
    cancelled_nonzero = cursor.fetchone()[0]
    print(
        f"{'✓' if cancelled_nonzero == 0 else '✗'} Cancelled orders with non-zero total: {cancelled_nonzero}"
    )
    assert cancelled_nonzero == 0, "Cancelled orders should have zero total"


def validate_price_variations(cursor):
    """Validate price variations are within expected range."""
    print("\n" + "=" * 60)
    print("PRICE VARIATION VALIDATION")
    print("=" * 60)

    cursor.execute(
        """
        SELECT p.product_id, 
               p.name,
               p.price as current_price,
               MIN(oi.price_per_unit) as min_historical,
               MAX(oi.price_per_unit) as max_historical,
               ROUND(ABS(MAX(oi.price_per_unit) - p.price) / p.price * 100, 1) as max_variance_pct
        FROM products p
        JOIN order_items oi ON p.product_id = oi.product_id
        GROUP BY p.product_id, p.name, p.price
        HAVING max_variance_pct > 5.5
    """
    )

    out_of_range = cursor.fetchall()
    print(
        f"{'✓' if len(out_of_range) == 0 else '✗'} Products with >5% price variance: {len(out_of_range)}"
    )

    if out_of_range:
        print("\nProducts with high variance:")
        for product_id, name, current, min_hist, max_hist, variance in out_of_range[:5]:
            print(
                f"  {product_id}: current=${current}, range=${min_hist}-${max_hist}, variance={variance}%"
            )

    assert len(out_of_range) == 0, "Found products with excessive price variance"


def validate_customer_segments(cursor):
    """Validate customer segment distribution."""
    print("\n" + "=" * 60)
    print("CUSTOMER SEGMENT VALIDATION")
    print("=" * 60)

    cursor.execute(
        """
        SELECT segment,
               COUNT(*) as count,
               ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM customers), 1) as percentage
        FROM customers
        GROUP BY segment
        ORDER BY count DESC
    """
    )

    print("\nSegment Distribution:")
    for segment, count, percentage in cursor.fetchall():
        print(f"  {segment}: {count} ({percentage}%)")


def test_query_performance(cursor):
    """Test query performance for key workshop scenarios."""
    print("\n" + "=" * 60)
    print("QUERY PERFORMANCE TEST")
    print("=" * 60)

    queries = [
        (
            "Customer lookup",
            "SELECT * FROM customers WHERE email = 'sarah.chen@gmail.com'",
        ),
        ("Order status", "SELECT * FROM orders WHERE customer_id = 'CUST-001'"),
        (
            "Order details",
            """
            SELECT o.*, oi.*, p.name 
            FROM orders o 
            JOIN order_items oi ON o.order_id = oi.order_id 
            JOIN products p ON oi.product_id = p.product_id 
            WHERE o.customer_id = 'CUST-001'
        """,
        ),
        (
            "Product availability",
            "SELECT * FROM products WHERE category = 'Laptops' AND in_stock = 1",
        ),
        (
            "Bundle analysis",
            """
            SELECT p1.name, p2.name, COUNT(*) as times
            FROM order_items oi1
            JOIN order_items oi2 ON oi1.order_id = oi2.order_id AND oi1.product_id < oi2.product_id
            JOIN products p1 ON oi1.product_id = p1.product_id
            JOIN products p2 ON oi2.product_id = p2.product_id
            GROUP BY p1.name, p2.name
            ORDER BY times DESC
            LIMIT 10
        """,
        ),
    ]

    print("\nQuery execution times:")
    all_under_100ms = True

    for name, query in queries:
        start = time.time()
        cursor.execute(query)
        cursor.fetchall()
        elapsed_ms = (time.time() - start) * 1000

        under_target = elapsed_ms < 100
        symbol = "✓" if under_target else "✗"
        print(f"  {symbol} {name}: {elapsed_ms:.2f}ms")

        if not under_target:
            all_under_100ms = False

    if all_under_100ms:
        print("\n✓ All queries executed in <100ms")
    else:
        print("\n⚠ Some queries exceeded 100ms target (acceptable for small dataset)")


def run_sample_queries(cursor):
    """Run a few sample workshop queries."""
    print("\n" + "=" * 60)
    print("SAMPLE QUERY RESULTS")
    print("=" * 60)

    # Customer verification
    print("\n1. Customer verification (HITL scenario):")
    cursor.execute(
        "SELECT customer_id, name, email FROM customers WHERE email = 'sarah.chen@gmail.com'"
    )
    result = cursor.fetchone()
    if result:
        print(f"   Found: {result[1]} ({result[0]}) - {result[2]}")

    # Recent orders
    print("\n2. Recent orders for CUST-001:")
    cursor.execute(
        """
        SELECT order_id, order_date, status, total_amount
        FROM orders 
        WHERE customer_id = 'CUST-001'
        ORDER BY order_date DESC
        LIMIT 3
    """
    )
    for order_id, date, status, total in cursor.fetchall():
        print(f"   {order_id}: {date} - {status} (${total})")

    # Top product bundles
    print("\n3. Top product combinations:")
    cursor.execute(
        """
        SELECT p1.name as product1, p2.name as product2, COUNT(*) as times
        FROM order_items oi1
        JOIN order_items oi2 ON oi1.order_id = oi2.order_id AND oi1.product_id < oi2.product_id
        JOIN products p1 ON oi1.product_id = p1.product_id
        JOIN products p2 ON oi2.product_id = p2.product_id
        GROUP BY p1.name, p2.name
        ORDER BY times DESC
        LIMIT 3
    """
    )
    for prod1, prod2, times in cursor.fetchall():
        print(f"   {times}x: {prod1} + {prod2}")


def main():
    """Main validation execution."""
    print("=" * 60)
    print("TechHub Database Validator")
    print("=" * 60)
    print(f"Database: {DB_PATH}")

    try:
        conn = connect_database()
        cursor = conn.cursor()

        # Run all validations
        validate_record_counts(cursor)
        validate_foreign_keys(cursor)
        validate_date_logic(cursor)
        validate_status_distribution(cursor)
        validate_order_totals(cursor)
        validate_cancelled_orders(cursor)
        validate_price_variations(cursor)
        validate_customer_segments(cursor)
        test_query_performance(cursor)
        run_sample_queries(cursor)

        print("\n" + "=" * 60)
        print("✓ ALL VALIDATIONS PASSED")
        print("=" * 60)
        print("\nDatabase is ready for workshop use!")
        print("Next steps:")
        print("  - Try queries from scripts/sample_queries.sql")
        print("  - Build multi-agent system using this database")
        print("  - Create RAG documentation for complete dataset")

    except AssertionError as e:
        print("\n" + "=" * 60)
        print(f"✗ VALIDATION FAILED: {e}")
        print("=" * 60)
        return 1
    except Exception as e:
        print("\n" + "=" * 60)
        print(f"✗ ERROR: {e}")
        print("=" * 60)
        return 1
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    exit(main())
