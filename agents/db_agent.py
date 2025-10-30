"""Database Agent for TechHub customer support.

This agent specializes in querying structured data from the database,
including order status, product information, and customer orders.
"""

from langchain.agents import AgentState, create_agent
from langchain.chat_models import init_chat_model
from langgraph.checkpoint.memory import MemorySaver

from config import DEFAULT_MODEL
from tools import get_order_details, get_product_price

# ============================================================================
# AGENT CONFIGURATION
# These constants define the database agent's behavior and can be easily
# customized for different workshop scenarios or customer requirements.
# ============================================================================

DB_AGENT_SYSTEM_PROMPT = """You are a database specialist for TechHub customer support.

Your role is to query the TechHub database for:
- Order status and details
- Product prices and availability

Always provide specific, accurate information from the database.
If you cannot find information, say so clearly.

Note: For tools that need the customer_id (e.g., get_customer_orders), it will be automatically provided in the state after a customer's identity is verified.
This means you don't need to ask the customer for their ID - you can just use the tool."""

# Base tools that every database agent needs
DB_AGENT_BASE_TOOLS = [
    get_order_details,
    get_product_price,
]


# ============================================================================
# FACTORY FUNCTION
# ============================================================================


def create_db_agent(
    state_schema=None,
    additional_tools=None,
    use_checkpointer=True,
    model=None,
    system_prompt=None,
):
    """Create database agent with sensible defaults.

    This factory encodes what makes a "database agent":
    - Specializes in querying structured database data
    - Uses database-specific tools (orders, products)
    - Has appropriate system prompt for DB queries

    Args:
        state_schema: Optional custom state schema (extends AgentState).
        additional_tools: Additional tools beyond base DB tools (e.g., get_customer_orders).
        use_checkpointer: Whether to include checkpointer (True for dev, False for deployment).
        model: Model to use (defaults to WORKSHOP_MODEL from .env or claude-haiku-4-5).
        system_prompt: Custom system prompt (defaults to DB_AGENT_SYSTEM_PROMPT).

    Returns:
        Compiled agent graph that can query orders, products, and inventory.

    Examples:
        >>> # Simple usage with defaults
        >>> db_agent = create_db_agent()

        >>> # Customize for specific needs
        >>> db_agent = create_db_agent(
        ...     state_schema=CustomState,
        ...     additional_tools=[get_customer_orders],
        ...     model="openai:gpt-4o-mini"
        ... )
    """
    # Use provided values or fall back to module defaults
    llm = init_chat_model(model or DEFAULT_MODEL)
    prompt = system_prompt or DB_AGENT_SYSTEM_PROMPT
    tools = DB_AGENT_BASE_TOOLS.copy()

    # Extend with additional tools if provided
    if additional_tools:
        tools.extend(additional_tools)

    # Build agent kwargs
    agent_kwargs = {
        "model": llm,
        "tools": tools,
        "system_prompt": prompt,
        "state_schema": state_schema or AgentState,
    }

    # Add checkpointer for development (platform handles it for deployment)
    if use_checkpointer:
        agent_kwargs["checkpointer"] = MemorySaver()

    return create_agent(**agent_kwargs)
