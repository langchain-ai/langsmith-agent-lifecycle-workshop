"""
Database tools for querying the TechHub e-commerce database.

These tools provide a simple interface for customer support agents to:
- Look up customer order history
- Get detailed information about specific orders
- Query product pricing and availability

Design note: Database connections are initialized at the module level using lazy loading.
The connection is created on first use and then cached for subsequent calls.
"""

from langchain.tools import ToolRuntime, tool
from langchain_community.utilities import SQLDatabase

from config import DEFAULT_DB_PATH

# Module-level database connection (lazy loaded)
_db = None


def get_database():
    """Lazy load database connection.

    Creates the database connection on first call, then returns the cached instance
    for all subsequent calls.

    Returns:
        SQLDatabase: Cached database connection instance.
    """
    global _db
    if _db is None:
        _db = SQLDatabase.from_uri(f"sqlite:///{DEFAULT_DB_PATH}")
    return _db


def extract_values(result):
    """Convert SQLDatabase query results (list of dicts) to list of tuples (values only)."""
    return [tuple(row.values()) for row in result]


@tool
def get_order_status(order_id: str) -> str:
    """Get status, dates, and tracking information for a specific order.

    Args:
        order_id: The order ID (e.g., "ORD-2024-0123")

    Returns:
        Formatted string with order status, dates, tracking number, and total amount.
    """
    db = get_database()
    result = db._execute(
        f"""
        SELECT order_id, order_date, status, shipped_date, tracking_number, total_amount
        FROM orders
        WHERE order_id = '{order_id}'
    """
    )
    result = extract_values(result)

    if not result:
        return f"Order {order_id} not found."

    order_id, order_date, status, shipped_date, tracking_number, total = result[0]

    response = f"Order {order_id}:\n"
    response += f"- Status: {status}\n"
    response += f"- Order Date: {order_date}\n"
    response += f"- Total Amount: ${total:.2f}\n"

    if shipped_date:
        response += f"- Shipped Date: {shipped_date}\n"
    if tracking_number:
        response += f"- Tracking Number: {tracking_number}\n"

    return response


@tool
def get_order_items(order_id: str) -> str:
    """Get list of items in a specific order with product IDs, quantities, and prices.

    Args:
        order_id: The order ID (e.g., "ORD-2024-0123")

    Returns:
        Formatted string with product IDs, quantities, and prices for each item.
        Note: Returns product IDs only - use get_product_info() to get product names.
    """
    db = get_database()
    result = db._execute(
        f"""
        SELECT product_id, quantity, price_per_unit
        FROM order_items
        WHERE order_id = '{order_id}'
    """
    )
    result = extract_values(result)

    if not result:
        return f"No items found for order {order_id}."

    response = f"Items in order {order_id}:\n"
    for product_id, quantity, price in result:
        response += (
            f"- Product ID: {product_id}, Quantity: {quantity}, Price: ${price:.2f}\n"
        )

    return response


@tool
def get_product_info(product_identifier: str) -> str:
    """Get product details by product name or product ID.

    Args:
        product_identifier: Product name (e.g., "MacBook Air") or product ID (e.g., "TECH-LAP-001")

    Returns:
        Formatted string with product name, category, price, and stock status.
    """
    db = get_database()
    # Try exact ID match first
    result = db._execute(
        f"""
        SELECT product_id, name, category, price, in_stock
        FROM products
        WHERE product_id = '{product_identifier}'
    """
    )
    result = extract_values(result)

    # If no exact match, try fuzzy name search
    if not result:
        result = db._execute(
            f"""
            SELECT product_id, name, category, price, in_stock
            FROM products
            WHERE name LIKE '%{product_identifier}%'
            LIMIT 1
        """
        )
        result = extract_values(result)

    if not result:
        return f"Product '{product_identifier}' not found."

    product_id, name, category, price, in_stock = result[0]
    stock_status = "In Stock" if in_stock else "Out of Stock"

    return f"{name} ({product_id})\n- Category: {category}\n- Price: ${price:.2f}\n- Status: {stock_status}"


@tool
def get_customer_orders(runtime: ToolRuntime) -> str:
    """Get recent orders for a verified customer.

    Automatically injects the customer_id from the agent's state into the query
    so you don't need to ask the customer for their ID or email address to use this tool.

    Args:
        runtime: Runtime context (provides access to state)

    Returns:
        Formatted list of recent orders with order ID, date, status, and total.
    """
    # Get customer_id from state (populated by HITL verification in Section 4)
    state_customer_id = runtime.state.get("customer_id")
    if not state_customer_id:
        return "Customer verification required. Please provide your email."

    db = get_database()
    result = db._execute(
        f"""
        SELECT order_id, order_date, status, total_amount
        FROM orders
        WHERE customer_id = '{state_customer_id}'
        ORDER BY order_date DESC
    """
    )
    result = extract_values(result)

    if not result:
        return f"No orders found for customer {state_customer_id}."

    response = "Recent orders:\n"
    for order_id, order_date, status, total in result:
        response += f"- {order_id}: {order_date}, {status}, ${total:.2f}\n"

    return response
