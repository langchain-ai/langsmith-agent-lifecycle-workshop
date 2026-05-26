"""Supervisor agent for TechHub customer support.

This supervisor coordinates between specialized sub-agents (Database and Documents)
to handle customer queries. It routes queries to the appropriate specialist(s) and
can orchestrate parallel or sequential coordination when needed.
"""

from langchain.agents import create_agent
from langchain.agents.middleware import ModelRequest, dynamic_prompt
from langchain.chat_models import init_chat_model
from langchain.tools import tool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import MessagesState

from config import DEFAULT_MODEL, Context

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
- Never invent shipping, processing, escalation, or payment timeframes. Do not say things like "orders typically ship within 3-5 business days", "escalations take 7-10 business days", or "refunds take 3-7 business days for card transactions" unless that exact day-count appears verbatim in a documentation_specialist tool result from the current conversation. Any concrete day-count timeframe you quote MUST be grounded in a documentation_specialist result you have already received in this conversation — not in prior knowledge, not in assumptions about the "Processing" order stage, not in generic e-commerce norms. If the customer asks how long until their order ships (or any similar timeframe question) and the documentation does not give a grounded answer for that stage, explicitly tell the customer that the timeframe is not specified in published policy and suggest they contact TechHub support for an update. Grounded answers using the actual published Standard (5-7 business days) or Express (2-3 business days) delivery windows from documentation_specialist are fine — this rule only forbids fabricating numbers that did not come from a tool result.

You can use multiple tools if needed to fully answer the question.
Always provide helpful, accurate, concise, and specific responses to customer questions."""


# ============================================================================
# FACTORY FUNCTION
# ============================================================================


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
    def call_database_specialist(query: str) -> str:
        result = db_agent.invoke({"messages": [{"role": "user", "content": query}]})
        return result["messages"][-1].content

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
