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

    Note: For order total, calculate from items using get_order_item_price().

    Args:
        order_id: The order ID (e.g., "ORD-2024-0123")

    Returns:
        Formatted string with order status, dates, and tracking number.
    """
    db = get_database()
    result = db._execute(
        f"""
        SELECT order_id, order_date, status, shipped_date, tracking_number
        FROM orders
        WHERE order_id = '{order_id}'
    """
    )
    result = extract_values(result)

    if not result:
        return f"Order {order_id} not found."

    order_id, order_date, status, shipped_date, tracking_number = result[0]

    response = f"Order {order_id}:\n"
    response += f"- Status: {status}\n"
    response += f"- Order Date: {order_date}\n"

    if shipped_date:
        response += f"- Shipped Date: {shipped_date}\n"
    if tracking_number:
        response += f"- Tracking Number: {tracking_number}\n"

    return response


@tool
def get_order_items(order_id: str) -> str:
    """Get list of items in a specific order with product IDs and quantities.

    Note: For pricing, use get_order_item_price() for historical price paid, or get_product_info() for current price.

    Args:
        order_id: The order ID (e.g., "ORD-2024-0123")

    Returns:
        Formatted string with product IDs and quantities (no prices).
    """
    db = get_database()
    result = db._execute(
        f"""
        SELECT product_id, quantity
        FROM order_items
        WHERE order_id = '{order_id}'
    """
    )
    result = extract_values(result)

    if not result:
        return f"No items found for order {order_id}."

    response = f"Items in order {order_id}:\n"
    for product_id, quantity in result:
        response += f"- Product ID: {product_id}, Quantity: {quantity}\n"

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
def get_order_item_price(order_id: str, product_id: str) -> str:
    """Get the historical price paid for a specific item in an order.

    Use this to get the actual price the customer paid at time of purchase,
    which may differ from the current retail price from get_product_info().

    Args:
        order_id: The order ID (e.g., "ORD-2024-0123")
        product_id: The product ID (e.g., "TECH-LAP-001")

    Returns:
        Formatted string with historical price per unit.
    """
    db = get_database()
    result = db._execute(
        f"""
        SELECT price_per_unit, quantity
        FROM order_items
        WHERE order_id = '{order_id}' AND product_id = '{product_id}'
        """
    )
    result = extract_values(result)

    if not result:
        return f"Item {product_id} not found in order {order_id}."

    price, quantity = result[0]
    return f"Historical price for {product_id} in {order_id}: ${price:.2f} per unit (quantity: {quantity})"


@tool
def get_customer_orders(customer_id: str) -> str:
    """Get recent orders for a customer.

    Note: For order totals, calculate from items using get_order_item_price().

    Args:
        customer_id: The customer ID (e.g., "CUST-XYZ")

    Returns:
        Formatted list of recent orders with order ID, date, and status.
    """

    db = get_database()
    result = db._execute(
        f"""
        SELECT order_id, order_date, status
        FROM orders
        WHERE customer_id = '{customer_id}'
        ORDER BY order_date DESC
    """
    )
    result = extract_values(result)

    if not result:
        return f"No orders found for customer {customer_id}."

    response = "Recent orders:\n"
    for order_id, order_date, status in result:
        response += f"- {order_id}: {order_date}, {status}\n"

    return response


# Base SQL execution tool
@tool
def execute_sql(query: str) -> str:
    """Execute a SELECT query against the TechHub database.

    Safety: Only SELECT queries allowed - no INSERT/UPDATE/DELETE/etc.
    """
    # Safety check: Only allow SELECT queries
    if not query.strip().upper().startswith("SELECT"):
        return "Error: Only SELECT queries are allowed."

    # Block dangerous keywords
    FORBIDDEN = [
        "INSERT",
        "UPDATE",
        "DELETE",
        "ALTER",
        "DROP",
        "CREATE",
        "REPLACE",
        "TRUNCATE",
    ]
    if any(keyword in query.upper() for keyword in FORBIDDEN):
        return "Error: Query contains forbidden keyword."

    # Execute query
    db = get_database()
    try:
        result = db._execute(query)
        result = [tuple(row.values()) for row in result]  # extract values
        return result
    except Exception as e:
        return f"SQL Error: {str(e)}"
