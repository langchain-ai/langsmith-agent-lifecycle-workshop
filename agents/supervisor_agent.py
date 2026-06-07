"""Supervisor agent for TechHub customer support.

This supervisor coordinates between specialized sub-agents (Database and Documents)
to handle customer queries. It routes queries to the appropriate specialist(s) and
can orchestrate parallel or sequential coordination when needed.
"""

import re
from typing import Annotated

from langchain.agents import create_agent
from langchain.agents.middleware import ModelRequest, dynamic_prompt
from langchain.chat_models import init_chat_model
from langchain.tools import tool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import MessagesState
from langgraph.prebuilt import InjectedState

from config import DEFAULT_MODEL, Context

_CUSTOMER_ID_PATTERN = re.compile(r"CUST-\d+")

# ============================================================================
# AGENT CONFIGURATION
# These constants define the supervisor agent's behavior and can be easily
# customized for different workshop scenarios or customer requirements.
# ============================================================================


SUPERVISOR_AGENT_SYSTEM_PROMPT = """You are a supervisor agent for TechHub customer support.

Your role is to interact with customers to understand their questions, use the sub-agent tools provided to 
gather information needed to answer their questions, and then provide helpful responses to the customer.

Capabilities:
- Interact with customers to understand their questions
- Formulate queries to the database_specialist to help answer questions about orders (status, details), products (prices, availability), and customer accounts.
- Formulate queries to the documentation_specialist to help answer questions about product specs, policies, warranties, and setup instructions

IMPORTANT:
- For the database_specialist, if the question requires finding information about a specific customer, you will need to include the customer's email OR customer_id in your query!
- Do not answer questions about the database or documentation by yourself, always use the tools provided to you to get the information you need.
- Be sure to phrase your queries to the sub-agents from your perspective as the supervisor agent, not the customer's perspective.
- If the customer asks to cancel an order, check that the order is eligible for cancellation, and then let the customer know you will cancel the order.

You can use multiple tools if needed to fully answer the question.
Always provide helpful, accurate, concise, and specific responses to customer questions."""


# ============================================================================
# FACTORY FUNCTION
# ============================================================================


def _redact_other_customer_ids(text: str, authorized_customer_id: str | None) -> str:
    """Redact rows that leak another customer's CUST-XXX identifier."""
    if not authorized_customer_id or not isinstance(text, str):
        return text
    leaked = {
        cid
        for cid in _CUSTOMER_ID_PATTERN.findall(text)
        if cid != authorized_customer_id
    }
    if not leaked:
        return text
    safe_lines = [
        line
        for line in text.splitlines()
        if not any(cid in line for cid in leaked)
    ]
    refusal = "The requested record is not associated with your account."
    return "\n".join(safe_lines).strip() or refusal


def create_supervisor_agent(
    db_agent,
    docs_agent,
    state_schema=None,
    use_checkpointer=True,
    model=None,
    system_prompt=None,
):
    """Create supervisor agent with sensible defaults.

    This factory encodes what makes a "supervisor agent":
    - Coordinates between specialized sub-agents
    - Routes queries to appropriate specialists
    - Can orchestrate parallel or sequential coordination

    Args:
        db_agent: Compiled database agent graph (required).
        docs_agent: Compiled documents agent graph (required).
        state_schema: Optional custom state schema (extends MessagesState).
        use_checkpointer: Whether to include checkpointer (True for dev, False for deployment).
        model: Model to use (defaults to WORKSHOP_MODEL from .env or claude-haiku-4-5).
        system_prompt: Custom system prompt (defaults to SUPERVISOR_AGENT_SYSTEM_PROMPT).

    Returns:
        Compiled supervisor agent graph that can route to specialists.

    Examples:
        >>> # Simple usage with defaults
        >>> from agents import create_db_agent, create_docs_agent, create_supervisor_agent
        >>> db_agent = create_db_agent()
        >>> docs_agent = create_docs_agent()
        >>> supervisor = create_supervisor_agent(db_agent, docs_agent)

        >>> # Customize for specific needs
        >>> supervisor = create_supervisor_agent(
        ...     db_agent,
        ...     docs_agent,
        ...     state_schema=CustomState,
        ...     model="openai:gpt-4o"
        ... )
    """
    # Use provided values or fall back to module defaults
    llm = init_chat_model(model or DEFAULT_MODEL, configurable_fields=["model"])
    prompt = system_prompt or SUPERVISOR_AGENT_SYSTEM_PROMPT

    # Dynamic prompt middleware to inject customer_id if it exists in state
    @dynamic_prompt
    def supervisor_prompt(request: ModelRequest) -> str:
        customer_id = request.state.get("customer_id", None)

        if customer_id:
            return f"""{prompt}
            \n\n The customer's ID in this conversation is: {customer_id}
            """
        else:
            return prompt

    # Wrap Database Agent as a tool
    @tool(
        "database_specialist",
        description="Query TechHub database specialist for order status, order details, product prices, product availability, and customer accounts.",
    )
    def call_database_specialist(
        query: str,
        state: Annotated[dict, InjectedState],
    ) -> str:
        customer_id = state.get("customer_id") if state else None
        if customer_id:
            scoped_query = (
                f"AUTHORIZATION: You may only return rows whose customer_id == '{customer_id}'.\n"
                f"Every SELECT must include `WHERE customer_id = '{customer_id}'`.\n"
                f"Do NOT JOIN the `customers` table to return any other customer's name, "
                f"customer_id, email, phone, or address.\n"
                f"If the requested order_id (or other record) does not belong to "
                f"'{customer_id}', respond with exactly:\n"
                f"  'Order <id> is not associated with your account.'\n"
                f"and do NOT name, describe, or hint at the actual owner.\n\n"
                f"Supervisor's question: {query}"
            )
        else:
            scoped_query = query
        result = db_agent.invoke(
            {"messages": [{"role": "user", "content": scoped_query}]}
        )
        response = result["messages"][-1].content
        return _redact_other_customer_ids(response, customer_id)

    # Wrap Documents Agent as a tool
    @tool(
        "documentation_specialist",
        description="Query TechHub documentation specialist to search for product specs, policies, warranties, and setup instructions",
    )
    def call_documentation_specialist(query: str) -> str:
        result = docs_agent.invoke({"messages": [{"role": "user", "content": query}]})
        return result["messages"][-1].content

    # Build agent kwargs
    agent_kwargs = {
        "model": llm,
        "tools": [call_database_specialist, call_documentation_specialist],
        "name": "supervisor_agent",
        "state_schema": state_schema or MessagesState,
        "middleware": [supervisor_prompt],
        "context_schema": Context,
    }

    # Add checkpointer for development (platform handles it for deployment)
    if use_checkpointer:
        agent_kwargs["checkpointer"] = MemorySaver()

    return create_agent(**agent_kwargs)
