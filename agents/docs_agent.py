"""Documents Agent for TechHub customer support.

This agent specializes in searching product documentation and store policies
using retrieval-augmented generation (RAG).
"""

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langgraph.checkpoint.memory import MemorySaver

from tools import search_policy_docs, search_product_docs


def create_docs_agent():
    """Create Documents agent specialized in product documentation and policies.

    Args:
        state_schema: Optional custom state schema (extends AgentState).
                     If provided, allows agent to access additional state keys.

    Returns:
        Compiled agent graph that can search product specs and policies.
    """
    llm = init_chat_model("anthropic:claude-haiku-4-5")

    system_prompt = """You are a company policy and product information specialist for TechHub customer support.

Your role is to answer questions about product specifications, features, compatibility,
policies (returns, warranties, shipping), and setup instructions.

Always search the documentation to provide accurate, detailed information.
If you cannot find information, say so clearly."""

    return create_agent(
        model=llm,
        tools=[search_product_docs, search_policy_docs],
        system_prompt=system_prompt,
        checkpointer=MemorySaver(),
    )
