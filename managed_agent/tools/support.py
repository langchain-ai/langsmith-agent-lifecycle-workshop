"""TechHub support tools for the Managed Deep Agent.

These run in the agent server process (not the sandbox) against the TechHub
database shipped with the project. Customer data is reachable only through
these tools, so the customer-scope guard in `middleware/customer_scope.py`
can enforce who sees what. The sandbox holds public docs only.

Queries are parameterized; never interpolate model-supplied values into SQL.
"""

import sqlite3
from pathlib import Path

from langchain.tools import tool

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "techhub.db"


def _query(sql: str, params: tuple = ()) -> list[tuple]:
    with sqlite3.connect(DB_PATH) as conn:
        return conn.execute(sql, params).fetchall()


@tool(parse_docstring=True)
def get_order_status(order_id: str) -> str:
    """Get status, dates, and tracking information for a specific order.

    Args:
        order_id: The order ID (e.g., "ORD-2024-0123")
    """
    rows = _query(
        "SELECT order_id, order_date, status, shipped_date, tracking_number FROM orders WHERE order_id = ?",
        (order_id,),
    )
    if not rows:
        return f"Order {order_id} not found."
    order_id, order_date, status, shipped_date, tracking_number = rows[0]
    lines = [f"Order {order_id}:", f"- Status: {status}", f"- Order Date: {order_date}"]
    if shipped_date:
        lines.append(f"- Shipped Date: {shipped_date}")
    if tracking_number:
        lines.append(f"- Tracking Number: {tracking_number}")
    return "\n".join(lines)


@tool(parse_docstring=True)
def get_order_items(order_id: str) -> str:
    """Get the products, quantities, and prices paid in a specific order.

    Args:
        order_id: The order ID (e.g., "ORD-2024-0123")
    """
    rows = _query(
        """SELECT p.name, oi.product_id, oi.quantity, oi.price_per_unit
           FROM order_items oi JOIN products p ON p.product_id = oi.product_id
           WHERE oi.order_id = ?""",
        (order_id,),
    )
    if not rows:
        return f"No items found for order {order_id}."
    items = "\n".join(f"- {name} ({pid}) x{qty} at ${price:,.2f}" for name, pid, qty, price in rows)
    return f"Items in order {order_id}:\n{items}"


@tool(parse_docstring=True)
def get_customer_orders(customer_id: str) -> str:
    """Get the verified customer's recent orders (most recent first).

    Args:
        customer_id: The customer ID (e.g., "CUST-003")
    """
    rows = _query(
        "SELECT order_id, order_date, status FROM orders WHERE customer_id = ? ORDER BY order_date DESC LIMIT 10",
        (customer_id,),
    )
    if not rows:
        return f"No orders found for {customer_id}."
    return "Recent orders:\n" + "\n".join(f"- {oid}: {date}, {status}" for oid, date, status in rows)


@tool(parse_docstring=True)
def get_product_info(product_identifier: str) -> str:
    """Get product price, category, and stock by product ID or (partial) name.

    Args:
        product_identifier: A product ID (e.g., "TECH-LAP-001") or name fragment
    """
    rows = _query(
        """SELECT product_id, name, category, price, in_stock FROM products
           WHERE product_id = ? OR name LIKE ? LIMIT 5""",
        (product_identifier, f"%{product_identifier}%"),
    )
    if not rows:
        return f"No product found for '{product_identifier}'."
    return "\n".join(
        f"{name} ({pid})\n- Category: {cat}\n- Price: ${price:,.2f}\n- In stock: {'yes' if stock else 'no'}"
        for pid, name, cat, price, stock in rows
    )


@tool(parse_docstring=True)
def get_delayed_orders(min_days: int = 3) -> str:
    """Operations report: orders still Processing after `min_days` days. Ops role only.

    Args:
        min_days: Minimum days since the order date.
    """
    rows = _query(
        """SELECT order_id, order_date FROM orders
           WHERE status = 'Processing' AND julianday('now') - julianday(order_date) >= ?
           ORDER BY order_date""",
        (min_days,),
    )
    if not rows:
        return "No delayed orders."
    return f"{len(rows)} orders Processing for {min_days}+ days:\n" + "\n".join(f"- {oid} (ordered {d})" for oid, d in rows)


@tool(parse_docstring=True)
def request_refund(order_id: str, reason: str) -> str:
    """Submit a refund request for a delivered order. Requires human approval before it runs.

    Args:
        order_id: The order to refund (e.g. "ORD-2024-0001").
        reason: Short reason given by the customer.
    """
    # Mock action: a real implementation would create a ticket in the refunds system.
    return f"Refund request submitted for {order_id} (reason: {reason}). A support specialist will confirm the amount."
