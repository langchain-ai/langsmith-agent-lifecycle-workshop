"""Supervisor agent for TechHub customer support.

This supervisor coordinates between specialized sub-agents (Database and Documents)
to handle customer queries. It routes queries to the appropriate specialist(s) and
can orchestrate parallel or sequential coordination when needed.
"""

from langchain.agents import AgentState, create_agent
from langchain.chat_models import init_chat_model
from langchain.tools import ToolRuntime, tool
from langgraph.checkpoint.memory import MemorySaver

from config import DEFAULT_MODEL

# ============================================================================
# AGENT CONFIGURATION
# These constants define the supervisor agent's behavior and can be easily
# customized for different workshop scenarios or customer requirements.
# ============================================================================

SUPERVISOR_AGENT_SYSTEM_PROMPT = """You are a supervisor for TechHub customer support.

Your role is to route queries to the appropriate specialists:
- Use database_specialist for order status, product prices, and customer order history
- Use documentation_specialist for product specs, policies, and general information

Note: After a customer's identity is verified, their customer_id is available and automatically included in the state
when calling the database_specialist. For queries about "my orders", "my recent purchases", etc., 
simply call the database_specialist - you don't need to ask the customer for their ID.

You can use multiple tools if needed to fully answer the question.
Always provide helpful, complete responses to customers."""


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
        state_schema: Optional custom state schema (extends AgentState).
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
    llm = init_chat_model(model or DEFAULT_MODEL)
    prompt = system_prompt or SUPERVISOR_AGENT_SYSTEM_PROMPT

    # Wrap Database Agent as a tool
    @tool(
        "database_specialist",
        description="Query TechHub database for order status, product prices, and customer order history. After a customer's identity is verified, their customer_id is automatically provided in the state - just describe what information is needed.",
    )
    def call_database_specialist(runtime: ToolRuntime, query: str) -> str:
        """Call database specialist, forwarding customer_id from supervisor state."""
        # Extract customer_id from supervisor's state and pass to db_agent
        invocation_state = {"messages": [{"role": "user", "content": query}]}

        # Forward customer_id if it exists in supervisor's state
        if customer_id := runtime.state.get("customer_id"):
            invocation_state["customer_id"] = customer_id

        result = db_agent.invoke(invocation_state)
        return result["messages"][-1].content

    # Wrap Documents Agent as a tool
    @tool(
        "documentation_specialist",
        description="Search TechHub documentation for product specs, policies, warranties, and setup instructions",
    )
    def call_documentation_specialist(query: str) -> str:
        result = docs_agent.invoke({"messages": [{"role": "user", "content": query}]})
        return result["messages"][-1].content

    # Build agent kwargs
    agent_kwargs = {
        "model": llm,
        "tools": [call_database_specialist, call_documentation_specialist],
        "system_prompt": prompt,
        "state_schema": state_schema or AgentState,
    }

    # Add checkpointer for development (platform handles it for deployment)
    if use_checkpointer:
        agent_kwargs["checkpointer"] = MemorySaver()

    return create_agent(**agent_kwargs)
