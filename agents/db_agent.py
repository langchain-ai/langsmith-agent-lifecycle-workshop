"""Database Agent for TechHub customer support.

This agent specializes in querying structured data from the database,
including order status, product information, and customer orders.
"""

from langchain.agents import AgentState, create_agent
from langchain.chat_models import init_chat_model
from langgraph.checkpoint.memory import MemorySaver

from tools import get_order_details, get_product_price


def create_db_agent(state_schema=None, additional_tools=None):
    """Create database agent specialized in querying order and product data.

    Args:
        state_schema: Optional custom state schema (extends AgentState).
                     If provided, allows agent to access additional state keys.
        additional_tools: Optional list of additional tools to add (e.g., get_customer_orders).

    Returns:
        Compiled agent graph that can query orders, products, and inventory.
    """
    llm = init_chat_model("anthropic:claude-haiku-4-5")

    system_prompt = """You are a database specialist for TechHub customer support.
    
Your role is to query:
- Order status and details
- Product prices and availability
- Customer order history

Always provide specific, accurate information from the database.
If you cannot find information, say so clearly."""

    # Base tools (always available)
    tools = [get_order_details, get_product_price]

    # Add additional tools if provided (e.g., get_customer_orders in Section 4)
    if additional_tools:
        tools.extend(additional_tools)

    return create_agent(
        model=llm,
        tools=tools,
        system_prompt=system_prompt,
        checkpointer=MemorySaver(),
        state_schema=state_schema or AgentState,
    )
