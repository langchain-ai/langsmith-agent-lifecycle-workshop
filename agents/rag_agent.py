"""RAG Agent for TechHub customer support.

This agent specializes in searching product documentation and store policies
using retrieval-augmented generation (RAG).
"""

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langgraph.checkpoint.memory import MemorySaver

from tools import search_policy_docs, search_product_docs


def create_rag_agent():
    """Create RAG agent specialized in product documentation and policies.

    Returns:
        Compiled agent graph that can search product specs and policies.
    """
    llm = init_chat_model("anthropic:claude-haiku-4-5")

    system_prompt = """You are a product information specialist for TechHub customer support.

Your role is to answer questions about:
- Product specifications, features, and technical details
- Store policies (returns, warranties, shipping)
- Product compatibility and setup instructions

Always search the documentation to provide accurate, detailed information.
If you cannot find specific information, say so clearly."""

    return create_agent(
        model=llm,
        tools=[search_product_docs, search_policy_docs],
        system_prompt=system_prompt,
        checkpointer=MemorySaver(),
    )
