#!/usr/bin/env python3
"""
Create SQLite database for TechHub e-commerce dataset.

This script:
- Creates tables with full schema and constraints
- Loads data from JSON files
- Creates indexes for performance
- Validates the database structure
"""

import json
import sqlite3
from pathlib import Path

# Configuration
DATA_DIR = Path(__file__).parent.parent / "data" / "structured"
DB_PATH = DATA_DIR / "techhub.db"

# SQL Schema (from full_project_plan.md lines 1284-1336)
SCHEMA_SQL = """
-- Create customers table
CREATE TABLE customers (
    customer_id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    phone TEXT,
    city TEXT NOT NULL,
    state TEXT NOT NULL,
    segment TEXT NOT NULL CHECK(segment IN ('Consumer', 'Corporate', 'Home Office'))
);

-- Create products table
CREATE TABLE products (
    product_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL CHECK(category IN ('Laptops', 'Monitors', 'Keyboards', 'Audio', 'Accessories')),
    price REAL NOT NULL CHECK(price > 0),
    in_stock INTEGER NOT NULL CHECK(in_stock IN (0, 1))
);

-- Create orders table
CREATE TABLE orders (
    order_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    order_date DATE NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('Processing', 'Shipped', 'Delivered', 'Cancelled')),
    shipped_date DATE,
    tracking_number TEXT,
    total_amount REAL NOT NULL CHECK(total_amount >= 0),
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);

-- Create order_items table
CREATE TABLE order_items (
    order_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK(quantity > 0),
    price_per_unit REAL NOT NULL CHECK(price_per_unit > 0),
    FOREIGN KEY (order_id) REFERENCES orders(order_id),
    FOREIGN KEY (product_id) REFERENCES products(product_id)
);

-- Create indexes for performance
CREATE INDEX idx_orders_customer ON orders(customer_id);
CREATE INDEX idx_orders_date ON orders(order_date);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_order_items_order ON order_items(order_id);
CREATE INDEX idx_order_items_product ON order_items(product_id);
CREATE INDEX idx_products_category ON products(category);
CREATE INDEX idx_customers_email ON customers(email);
"""


def load_json_data():
    """Load all JSON data files."""
    print("Loading JSON data files...")

    with open(DATA_DIR / "customers.json", "r") as f:
        customers = json.load(f)
    print(f"  ✓ Loaded {len(customers)} customers")

    with open(DATA_DIR / "products.json", "r") as f:
        products = json.load(f)
    print(f"  ✓ Loaded {len(products)} products")

    with open(DATA_DIR / "orders.json", "r") as f:
        orders = json.load(f)
    print(f"  ✓ Loaded {len(orders)} orders")

    with open(DATA_DIR / "order_items.json", "r") as f:
        order_items = json.load(f)
    print(f"  ✓ Loaded {len(order_items)} order items")

    return customers, products, orders, order_items


def create_database():
    """Create database with schema."""
    # Delete existing database if it exists
    if DB_PATH.exists():
        print(f"\nRemoving existing database: {DB_PATH}")
        DB_PATH.unlink()

    print(f"\nCreating database: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Enable foreign keys
    cursor.execute("PRAGMA foreign_keys = ON")

    # Execute schema
    print("Creating tables and indexes...")
    cursor.executescript(SCHEMA_SQL)
    print("  ✓ Tables created")
    print("  ✓ Indexes created")

    conn.commit()
    return conn, cursor


def insert_customers(cursor, customers):
    """Insert customer data."""
    print("\nInserting customers...")
    for customer in customers:
        cursor.execute(
            """
            INSERT INTO customers (customer_id, email, name, phone, city, state, segment)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                customer["customer_id"],
                customer["email"],
                customer["name"],
                customer["phone"],
                customer["city"],
                customer["state"],
                customer["segment"],
            ),
        )
    print(f"  ✓ Inserted {len(customers)} customers")


def insert_products(cursor, products):
    """Insert product data."""
    print("Inserting products...")
    for product in products:
        cursor.execute(
            """
            INSERT INTO products (product_id, name, category, price, in_stock)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                product["product_id"],
                product["name"],
                product["category"],
                product["price"],
                product["in_stock"],
            ),
        )
    print(f"  ✓ Inserted {len(products)} products")


def insert_orders(cursor, orders):
    """Insert order data."""
    print("Inserting orders...")
    for order in orders:
        cursor.execute(
            """
            INSERT INTO orders (order_id, customer_id, order_date, status, shipped_date, tracking_number, total_amount)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order["order_id"],
                order["customer_id"],
                order["order_date"],
                order["status"],
                order["shipped_date"],
                order["tracking_number"],
                order["total_amount"],
            ),
        )
    print(f"  ✓ Inserted {len(orders)} orders")


def insert_order_items(cursor, order_items):
    """Insert order items data."""
    print("Inserting order items...")
    for item in order_items:
        # Note: order_item_id will be auto-generated by AUTOINCREMENT
        cursor.execute(
            """
            INSERT INTO order_items (order_id, product_id, quantity, price_per_unit)
            VALUES (?, ?, ?, ?)
            """,
            (
                item["order_id"],
                item["product_id"],
                item["quantity"],
                item["price_per_unit"],
            ),
        )
    print(f"  ✓ Inserted {len(order_items)} order items")


def verify_database(cursor):
    """Basic verification of database."""
    print("\nVerifying database...")

    # Check record counts
    cursor.execute("SELECT COUNT(*) FROM customers")
    customer_count = cursor.fetchone()[0]
    print(f"  ✓ Customers: {customer_count}")

    cursor.execute("SELECT COUNT(*) FROM products")
    product_count = cursor.fetchone()[0]
    print(f"  ✓ Products: {product_count}")

    cursor.execute("SELECT COUNT(*) FROM orders")
    order_count = cursor.fetchone()[0]
    print(f"  ✓ Orders: {order_count}")

    cursor.execute("SELECT COUNT(*) FROM order_items")
    item_count = cursor.fetchone()[0]
    print(f"  ✓ Order items: {item_count}")

    # Check indexes
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
    )
    indexes = cursor.fetchall()
    print(f"  ✓ Indexes: {len(indexes)}")

    # Check foreign keys are enabled
    cursor.execute("PRAGMA foreign_keys")
    fk_enabled = cursor.fetchone()[0]
    print(f"  ✓ Foreign keys: {'enabled' if fk_enabled else 'DISABLED'}")


def get_database_stats(cursor):
    """Get database statistics."""
    print("\n" + "=" * 60)
    print("DATABASE STATISTICS")
    print("=" * 60)

    # Table sizes
    print("\nTable Record Counts:")
    for table in ["customers", "products", "orders", "order_items"]:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]
        print(f"  {table}: {count}")

    # Order status distribution
    print("\nOrder Status Distribution:")
    cursor.execute(
        """
        SELECT status, COUNT(*) as count, 
               ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM orders), 1) as percentage
        FROM orders
        GROUP BY status
        ORDER BY count DESC
    """
    )
    for status, count, pct in cursor.fetchall():
        print(f"  {status}: {count} ({pct}%)")

    # Customer segment distribution
    print("\nCustomer Segment Distribution:")
    cursor.execute(
        """
        SELECT segment, COUNT(*) as count,
               ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM customers), 1) as percentage
        FROM customers
        GROUP BY segment
        ORDER BY count DESC
    """
    )
    for segment, count, pct in cursor.fetchall():
        print(f"  {segment}: {count} ({pct}%)")

    # Product category distribution
    print("\nProduct Category Distribution:")
    cursor.execute(
        """
        SELECT category, COUNT(*) as count
        FROM products
        GROUP BY category
        ORDER BY category
    """
    )
    for category, count in cursor.fetchall():
        print(f"  {category}: {count}")

    # Database file size
    import os

    db_size = os.path.getsize(DB_PATH)
    db_size_mb = db_size / (1024 * 1024)
    print(f"\nDatabase File Size: {db_size_mb:.2f} MB")


def main():
    """Main execution function."""
    print("=" * 60)
    print("TechHub SQLite Database Creator")
    print("=" * 60)

    # Load data
    customers, products, orders, order_items = load_json_data()

    # Create database
    conn, cursor = create_database()

    try:
        # Insert data in dependency order
        insert_customers(cursor, customers)
        insert_products(cursor, products)
        insert_orders(cursor, orders)
        insert_order_items(cursor, order_items)

        # Commit all changes
        conn.commit()
        print("\n✓ All data committed to database")

        # Verify
        verify_database(cursor)

        # Stats
        get_database_stats(cursor)

        print("\n" + "=" * 60)
        print("✓ DATABASE CREATION COMPLETE")
        print("=" * 60)
        print(f"\nDatabase location: {DB_PATH}")
        print("\nNext steps:")
        print("  - Run validate_database.py to verify data integrity")
        print("  - Try sample queries from sample_queries.sql")
        print("  - Use with SQLite browser tools for exploration")

    except Exception as e:
        conn.rollback()
        print(f"\n✗ Error: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
