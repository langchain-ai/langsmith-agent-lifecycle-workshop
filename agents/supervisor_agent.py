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
- If the customer reports that information you provided is incomplete, missing, cut off, or truncated, treat that as a valid signal. Do NOT insist the data is complete on your end. Acknowledge the report, offer to re-send the data in a more compact format (for example, a one-line-per-order summary), and ask which specific records they cannot see. If they still cannot consume the data, escalate to a human channel.
- Do NOT attribute output-visibility problems to the customer's device, browser, screen, app, or rendering, and do NOT recommend browser refresh, switching browsers, clearing cache, or contacting IT support — those are outside our read-only support scope to diagnose.

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
