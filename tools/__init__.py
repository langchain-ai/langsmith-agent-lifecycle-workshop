"""
Shared tools for the AI Engineering Lifecycle workshop.

This module contains reusable tools that can be imported across multiple workshop modules.
Tools are typically introduced in the notebooks first for pedagogical purposes,
then refactored here for reuse in later sections.
"""

from tools.database import get_customer_orders, get_order_details, get_product_price
from tools.documents import search_policy_docs, search_product_docs

__all__ = [
    # Database tools - Sections 1-3 (2 tools)
    "get_order_details",
    "get_product_price",
    # Database tools - Section 4 (introduces ToolRuntime pattern)
    "get_customer_orders",
    # Documents tools (2 tools - introduced in Section 3)
    "search_product_docs",
    "search_policy_docs",
]
