"""
RAG tools for searching TechHub product documentation and policies.

These tools provide semantic search over:
- Product documentation (specs, features, setup guides)
- Store policies (returns, warranties, shipping)

The vectorstore is pre-built from markdown documents and uses:
- HuggingFace embeddings (local, no API key needed)
- InMemoryVectorStore for fast retrieval
- Metadata filtering to separate products from policies
"""

import pickle
from pathlib import Path

from langchain_core.tools import tool

# Load vectorstore once at module level
VECTORSTORE_PATH = (
    Path(__file__).parent.parent / "data" / "vector_stores" / "techhub_vectorstore.pkl"
)

# Will be loaded on first use
_vectorstore = None


def _get_vectorstore():
    """Lazy load the vectorstore."""
    global _vectorstore
    if _vectorstore is None:
        if not VECTORSTORE_PATH.exists():
            raise FileNotFoundError(
                f"Vectorstore not found at {VECTORSTORE_PATH}. "
                "Please run: python utils/build_vectorstore.py"
            )
        with open(VECTORSTORE_PATH, "rb") as f:
            _vectorstore = pickle.load(f)
    return _vectorstore


@tool
def search_product_docs(query: str) -> str:
    """Search product documentation for specifications, features, and details.

    Use this tool when users ask about:
    - Product specifications (CPU, RAM, storage, ports, etc.)
    - Features and capabilities
    - Setup and usage instructions
    - Technical details
    - Product comparisons

    Args:
        query: What to search for (e.g., "USB-C ports on MacBook", "Sony headphone battery life")

    Returns:
        Relevant product documentation content.
    """
    vectorstore = _get_vectorstore()

    # Filter function for product documents
    results = vectorstore.similarity_search(
        query, k=3, filter=lambda doc: doc.metadata.get("doc_type") == "product"
    )

    if not results:
        return "No relevant product documentation found."

    # Format results with sources
    formatted_results = []
    for doc in results:
        product_name = doc.metadata.get("product_name", "Unknown Product")
        product_id = doc.metadata.get("product_id", "")
        formatted_results.append(f"[{product_name} ({product_id})]\n{doc.page_content}")

    return "\n\n---\n\n".join(formatted_results)


@tool
def search_policy_docs(query: str) -> str:
    """Search store policies including returns, warranties, and shipping information.

    Use this tool when users ask about:
    - Return and refund policies
    - Warranty coverage and terms
    - Shipping information and timelines
    - Customer support policies
    - General store policies

    Args:
        query: What policy information to find (e.g., "return policy", "warranty coverage", "shipping times")

    Returns:
        Relevant policy information.
    """
    vectorstore = _get_vectorstore()

    # Filter function for policy documents
    results = vectorstore.similarity_search(
        query, k=2, filter=lambda doc: doc.metadata.get("doc_type") == "policy"
    )

    if not results:
        return "No relevant policy information found."

    # Format results with sources
    formatted_results = []
    for doc in results:
        policy_name = doc.metadata.get("policy_name", "Unknown Policy")
        formatted_results.append(f"[{policy_name}]\n{doc.page_content}")

    return "\n\n---\n\n".join(formatted_results)
