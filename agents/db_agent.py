"""Database Agent for TechHub customer support.

This agent specializes in querying structured data from the database,
including order status, product information, and customer orders.
"""

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langgraph.checkpoint.memory import MemorySaver

from tools import get_order_items, get_order_status, get_product_price


def create_db_agent():
    """Create database agent specialized in querying order and product data.

    Returns:
        Compiled agent graph that can query orders, products, and inventory.
    """
    llm = init_chat_model("anthropic:claude-haiku-4-5")

    system_prompt = """You are a database specialist for TechHub customer support.
    
Your role is to query:
- Order status and details
- Product prices and availability
- Items purchased in specific orders

Always provide specific, accurate information from the database.
If you cannot find information, say so clearly."""

    return create_agent(
        model=llm,
        tools=[get_order_status, get_product_price, get_order_items],
        system_prompt=system_prompt,
        checkpointer=MemorySaver(),
    )
