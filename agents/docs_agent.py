"""Documents Agent for TechHub customer support.

This agent specializes in searching product documentation and store policies
using retrieval-augmented generation (RAG).
"""

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import MessagesState

from config import DEFAULT_MODEL
from tools import search_policy_docs, search_product_docs

# ============================================================================
# AGENT CONFIGURATION
# These constants define the documents agent's behavior and can be easily
# customized for different workshop scenarios or customer requirements.
# ============================================================================

DOCS_AGENT_SYSTEM_PROMPT = """You are the company policy and product information specialist for TechHub customer support.

Your role is to answer queries from a supervisor agent about product specifications, features, compatibility, 
policies (returns, warranties, shipping), and setup instructions given the tools you have been provided.
You do NOT interact directly with customers, you only interact with the supervisor agent.

Capabilities: Search product documentation and company policies.

Instructions:
- Always search the documentation to provide accurate, detailed information.
- If information is missing or not found, say so clearly.
- Do NOT make assumptions or provide information not explicitly present in the documentation.

Be accurate, concise, and specific in your replies."""

# Base tools that every documents agent needs
DOCS_AGENT_BASE_TOOLS = [
    search_product_docs,
    search_policy_docs,
]


# ============================================================================
# FACTORY FUNCTION
# ============================================================================


def create_docs_agent(
    state_schema=None,
    use_checkpointer=True,
    model=None,
    system_prompt=None,
):
    """Create documents agent with sensible defaults.

    This factory encodes what makes a "documents agent":
    - Specializes in searching documentation and policies via RAG
    - Uses document search tools (products, policies)
    - Has appropriate system prompt for documentation queries

    Args:
        state_schema: Optional custom state schema (extends MessagesState).
        use_checkpointer: Whether to include checkpointer (True for dev, False for deployment).
        model: Model to use (defaults to WORKSHOP_MODEL from .env or claude-haiku-4-5).
        system_prompt: Custom system prompt (defaults to DOCS_AGENT_SYSTEM_PROMPT).

    Returns:
        Compiled agent graph that can search product specs and policies.

    Examples:
        >>> # Simple usage with defaults
        >>> docs_agent = create_docs_agent()

        >>> # Customize for specific needs
        >>> docs_agent = create_docs_agent(
        ...     state_schema=CustomState,
        ...     model="openai:gpt-4o-mini"
        ... )
    """
    # Use provided values or fall back to module defaults
    llm = init_chat_model(model or DEFAULT_MODEL)
    prompt = system_prompt or DOCS_AGENT_SYSTEM_PROMPT
    tools = DOCS_AGENT_BASE_TOOLS.copy()

    # Build agent kwargs
    agent_kwargs = {
        "model": llm,
        "tools": tools,
        "name": "docs_agent",
        "system_prompt": prompt,
        "state_schema": state_schema or MessagesState,
    }

    # Add checkpointer for development (platform handles it for deployment)
    if use_checkpointer:
        agent_kwargs["checkpointer"] = MemorySaver()

    return create_agent(**agent_kwargs)
