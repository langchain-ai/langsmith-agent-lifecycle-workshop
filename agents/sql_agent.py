"""SQL Agent for TechHub customer support.

This agent specializes in generating and executing SQL queries against the TechHub database.
Unlike the rigid tool-based db_agent, this agent can generate custom queries with JOINs,
aggregations, and complex filtering to answer database questions efficiently.

This agent demonstrates eval-driven development: baseline evaluation revealed that rigid
tools couldn't handle complex queries, so we built a flexible SQL agent that generates
queries on-demand to handle any database question.
"""

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import MessagesState

from config import DEFAULT_MODEL, Context
from tools.database import execute_sql, get_database

# ============================================================================
# AGENT CONFIGURATION
# ============================================================================


def _create_sql_system_prompt() -> str:
    """Generate SQL agent system prompt with embedded table schema.

    We generate this dynamically to include the full database schema,
    which helps the agent write accurate SQL queries.
    """
    # Get database schema at agent creation time
    db = get_database()
    table_info = db.get_table_info()

    return f"""You are a database specialist for TechHub customer support.

Your role is to answer queries from a supervisor agent about orders or products using the TechHub database tools you have been provided.
You do NOT interact directly with customers, you only interact with the supervisor agent.

You have access to a SQLite database with the following schema:

{table_info}

Your capabilities:
- Write SQL SELECT queries to answer any database question
- Use JOINs, aggregations (SUM, COUNT, AVG), filtering (WHERE), GROUP BY, ORDER BY
- Handle complex queries with multiple conditions

Guidelines:
1. Only use SELECT queries (read-only access)
2. Use proper JOINs when querying related tables
3. Format currency as $X.XX in your final answer
4. Provide context, not just raw numbers
5. Pay attention to the distinction between orders and order items when answering questions.
6. If a query returns no results, explain why
7. Be accurate, concise, and specific in your replies.

Critical: `orders` -> `order_items` is an OPTIONAL relationship. An order may have zero
`order_items` rows (cancelled orders and zero-total orders always do), so an INNER JOIN
from `orders` to `order_items` SILENTLY DROPS those orders from the result.
- When asked to list, count, or check the status of a customer's orders, query the
  `orders` table alone (it already carries status, shipped_date, tracking_number and
  total_amount). Do NOT join to `order_items` or `products` for these questions.
- If you also need line-item or product detail alongside the order rows, use
  `LEFT JOIN order_items` and `LEFT JOIN products` so orders without items still appear.
- Never describe a result set produced by joining to `order_items` as the customer's
  complete order history, and never state that an order or a status (e.g. "Cancelled")
  does not exist based on such a result. Before reporting that a customer has no order
  of some status, re-verify with a query against `orders` alone.

Important: Read-only access - no INSERT/UPDATE/DELETE operations.
"""


SQL_AGENT_BASE_TOOLS = [execute_sql]


# ============================================================================
# FACTORY FUNCTION
# ============================================================================


def create_sql_agent(
    state_schema=None,
    additional_tools=None,
    use_checkpointer=True,
    model=None,
    system_prompt=None,
):
    """Create SQL agent with sensible defaults.

    This factory encodes what makes a "SQL agent":
    - Generates custom SQL queries on-demand
    - Uses JOINs, aggregations, and complex filtering
    - Provides flexible database access vs rigid tool-based approach

    Args:
        state_schema: Optional custom state schema (extends MessagesState).
        additional_tools: Additional tools beyond base SQL execution tool.
        use_checkpointer: Whether to include checkpointer (True for dev, False for deployment).
        model: Model to use (defaults to WORKSHOP_MODEL from .env or claude-haiku-4-5).
        system_prompt: Custom system prompt (defaults to auto-generated with schema).

    Returns:
        Compiled agent graph that can generate and execute SQL queries.

    Examples:
        >>> # Simple usage with defaults
        >>> sql_agent = create_sql_agent()

        >>> # Customize for specific needs
        >>> sql_agent = create_sql_agent(
        ...     state_schema=CustomState,
        ...     model="openai:gpt-4o-mini"
        ... )
    """
    # Use provided values or fall back to module defaults
    llm = init_chat_model(model or DEFAULT_MODEL, configurable_fields=["model"])
    prompt = system_prompt or _create_sql_system_prompt()
    tools = SQL_AGENT_BASE_TOOLS.copy()

    # Extend with additional tools if provided
    if additional_tools:
        tools.extend(additional_tools)

    # Build agent kwargs
    agent_kwargs = {
        "model": llm,
        "tools": tools,
        "name": "sql_agent",
        "system_prompt": prompt,
        "state_schema": state_schema or MessagesState,
        "context_schema": Context,
    }

    # Add checkpointer for development (platform handles it for deployment)
    if use_checkpointer:
        agent_kwargs["checkpointer"] = MemorySaver()

    return create_agent(**agent_kwargs)
