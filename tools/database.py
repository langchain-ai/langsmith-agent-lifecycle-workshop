"""
Database tools for querying the TechHub e-commerce database.

These tools provide a simple interface for customer support agents to:
- Look up customer order history
- Get detailed information about specific orders
- Query product pricing and availability

Design note: Database connections are configured at the module level rather than
as tool parameters. This follows LangChain best practices where infrastructure
concerns (database paths, API keys, etc.) are managed via static runtime context,
not exposed to the LLM as tool parameters.
"""

import sqlite3
from pathlib import Path

from langchain.tools import ToolRuntime, tool

# Database path - configured at module level (infrastructure concern)
DEFAULT_DB_PATH = Path(__file__).parent.parent / "data" / "structured" / "techhub.db"


@tool
def get_order_details(order_id: str) -> str:
    """Get complete details for a specific order including status, items, and tracking.

    Args:
        order_id: The order ID (e.g., "ORD-2024-0123")

    Returns:
        Formatted string with:
        - Order status (Processing, Shipped, Delivered, Cancelled)
        - Shipped date and tracking number (if applicable)
        - List of all items in the order with product names, quantities, and prices
    """
    conn = sqlite3.connect(DEFAULT_DB_PATH)
    cursor = conn.cursor()

    # Get order status and shipping info
    cursor.execute(
        "SELECT status, shipped_date, tracking_number FROM orders WHERE order_id = ?",
        (order_id,),
    )
    order_result = cursor.fetchone()

    if not order_result:
        conn.close()
        return f"No order found with ID: {order_id}"

    status, shipped_date, tracking = order_result

    # Get order items
    cursor.execute(
        """
        SELECT oi.product_id, p.name, oi.quantity, oi.price_per_unit
        FROM order_items oi
        JOIN products p ON oi.product_id = p.product_id
        WHERE oi.order_id = ?
        """,
        (order_id,),
    )
    items_results = cursor.fetchall()
    conn.close()

    # Format response
    response = f"Order {order_id}:\n"
    response += f"  Status: {status}\n"
    response += f"  Shipped: {shipped_date or 'Not yet shipped'}\n"
    response += f"  Tracking: {tracking or 'N/A'}\n"

    if items_results:
        response += "\nItems:\n"
        for product_id, name, quantity, price in items_results:
            response += (
                f"  • {name} (ID: {product_id}) - Qty: {quantity} @ ${price:.2f}\n"
            )

    return response.strip()


@tool
def get_product_price(product_name: str) -> str:
    """Get the current price and availability of a product by name.

    Args:
        product_name: Product name to search for (e.g., "MacBook Air", "Sony headphones")

    Returns:
        Formatted string with product name, current price, and stock status.

    Note: This is public information and works the same across all sections.
    No verification needed.
    """
    conn = sqlite3.connect(DEFAULT_DB_PATH)
    cursor = conn.cursor()

    query = "SELECT name, price, in_stock FROM products WHERE name LIKE ?"
    cursor.execute(query, (f"%{product_name}%",))
    result = cursor.fetchone()
    conn.close()

    if not result:
        return f"No product found matching: {product_name}"

    name, price, in_stock = result
    stock_status = "In Stock" if in_stock else "Out of Stock"
    return f"{name}: ${price:.2f} - {stock_status}"


@tool
def get_customer_orders(runtime: ToolRuntime) -> str:
    """Get recent orders for the verified customer (last 10 orders).

    Automatically injects the customer_id from the agent's state into
    the query so you don't need to ask the customer for their ID to use this tool.

    Returns:
        Formatted list of recent orders with order ID, date, status, and total amount.
        Orders are sorted by date (most recent first).

    """
    customer_id = runtime.state.get("customer_id")
    if not customer_id:
        return "Customer identity verification required. Please provide your email address to access order information."

    conn = sqlite3.connect(DEFAULT_DB_PATH)
    cursor = conn.cursor()

    query = """
        SELECT order_id, order_date, status, total_amount
        FROM orders
        WHERE customer_id = ?
        ORDER BY order_date DESC
        LIMIT 10
    """
    cursor.execute(query, (customer_id,))
    results = cursor.fetchall()
    conn.close()

    if not results:
        return f"No orders found for customer {customer_id}"

    # Format the results
    orders = []
    for order_id, order_date, status, total in results:
        orders.append(f"  • {order_id} ({order_date}): {status} - ${total:.2f}")

    return f"Recent orders for customer {customer_id}:\n" + "\n".join(orders)
