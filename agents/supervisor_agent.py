"""Supervisor agent for TechHub customer support.

This supervisor coordinates between specialized sub-agents (Database and Documents)
to handle customer queries. It routes queries to the appropriate specialist(s) and
can orchestrate parallel or sequential coordination when needed.
"""

from langchain.agents import AgentState, create_agent
from langchain.chat_models import init_chat_model
from langchain.tools import ToolRuntime, tool
from langgraph.checkpoint.memory import MemorySaver


def create_supervisor_agent(db_agent, docs_agent, state_schema=None):
    """Create supervisor agent that routes between database and documents agents.

    Args:
        db_agent: Compiled database agent graph
        docs_agent: Compiled documents agent graph
        state_schema: Optional custom state schema (extends AgentState).
                     If provided, allows agent to access additional state keys.

    Returns:
        Compiled supervisor agent graph that can route to specialists.
    """

    # Wrap Database Agent as a tool
    @tool(
        "database_specialist",
        description="Query TechHub database for order status, product prices, and customer order history. Be sure to specify the customer_id or order_id rather than customers email address",
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

    # Create supervisor agent
    llm = init_chat_model("anthropic:claude-haiku-4-5")

    return create_agent(
        model=llm,
        tools=[call_database_specialist, call_documentation_specialist],
        system_prompt="""You are a supervisor for TechHub customer support.

Your role is to interact with the customer to understand their questions and route them to the appropriate specialists with additional context as needed:
- Use database_specialist for order status, product prices, and customer order history
- Use documentation_specialist for product specs, policies, and general information

You can use multiple tools if needed to fully answer the question.
Always provide helpful, complete responses to customers.""",
        checkpointer=MemorySaver(),
        state_schema=state_schema or AgentState,
    )
