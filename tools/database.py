"""
Database tools for querying the TechHub e-commerce database.

These tools provide a simple interface for customer support agents to:
- Look up order status and shipping information
- Query product pricing and availability

Design note: Database connections are configured at the module level rather than
as tool parameters. This follows LangChain best practices where infrastructure
concerns (database paths, API keys, etc.) are managed via static runtime context,
not exposed to the LLM as tool parameters.
"""

import sqlite3
from pathlib import Path

from langchain_core.tools import tool

# Database path - configured at module level (infrastructure concern)
DEFAULT_DB_PATH = Path(__file__).parent.parent / "data" / "structured" / "techhub.db"


@tool
def get_order_status(order_id: str) -> str:
    """Look up the status of an order by order ID.

    Args:
        order_id: The order ID (e.g., "ORD-2024-0123")

    Returns:
        Formatted string with order status, shipped date, and tracking number.
    """
    conn = sqlite3.connect(DEFAULT_DB_PATH)
    cursor = conn.cursor()

    query = f"SELECT status, shipped_date, tracking_number FROM orders WHERE order_id = '{order_id}'"
    cursor.execute(query)
    result = cursor.fetchone()
    conn.close()

    if not result:
        return f"No order found with ID: {order_id}"

    status, shipped_date, tracking = result
    return f"Order {order_id}: Status={status}, Shipped={shipped_date or 'Not yet shipped'}, Tracking={tracking or 'N/A'}"


@tool
def get_product_price(product_name: str) -> str:
    """Get the current price of a product by name.

    Args:
        product_name: Product name to search for (e.g., "MacBook Air")

    Returns:
        Formatted string with product name, price, and stock status.
    """
    conn = sqlite3.connect(DEFAULT_DB_PATH)
    cursor = conn.cursor()

    query = (
        f"SELECT name, price, in_stock FROM products WHERE name LIKE '%{product_name}%'"
    )
    cursor.execute(query)
    result = cursor.fetchone()
    conn.close()

    if not result:
        return f"No product found matching: {product_name}"

    name, price, in_stock = result
    stock_status = "In Stock" if in_stock else "Out of Stock"
    return f"{name}: ${price:.2f} - {stock_status}"


@tool
def get_order_items(order_id: str) -> str:
    """Get all items (products) that were purchased in a specific order.

    Args:
        order_id: The order ID (e.g., "ORD-2024-0063")

    Returns:
        Formatted list of products in the order with product IDs, names, and quantities.
    """
    conn = sqlite3.connect(DEFAULT_DB_PATH)
    cursor = conn.cursor()

    query = f"""
        SELECT oi.product_id, p.name, oi.quantity, oi.price_per_unit
        FROM order_items oi
        JOIN products p ON oi.product_id = p.product_id
        WHERE oi.order_id = '{order_id}'
    """
    cursor.execute(query)
    results = cursor.fetchall()
    conn.close()

    if not results:
        return f"No items found for order: {order_id}"

    items = []
    for product_id, name, quantity, price in results:
        items.append(f"  • {name} (ID: {product_id}) - Qty: {quantity} @ ${price:.2f}")

    return f"Items in order {order_id}:\n" + "\n".join(items)
