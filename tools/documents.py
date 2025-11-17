"""
Documents tools for searching TechHub product documentation and policies.

These tools provide semantic search over:
- Product documentation (specs, features, setup guides)
- Store policies (returns, warranties, shipping)

The vectorstore is pre-built from markdown documents and uses:
- HuggingFace embeddings (local, no API key needed)
- InMemoryVectorStore for fast retrieval
- VectorStoreRetriever for proper tracing and Runnable interface
- Metadata filtering to separate products from policies

Tools use response_format="content_and_artifact" to return both:
- Formatted content string for the LLM
- Raw Document objects as artifacts for downstream processing and LangSmith tracing
"""

import pickle

from langchain_core.documents import Document
from langchain_core.tools import tool

from config import DEFAULT_VECTORSTORE_PATH

# Module-level vectorstore and retrievers (lazy loaded)
_vectorstore = None
_product_retriever = None
_policy_retriever = None


def get_vectorstore():
    """Lazy load the vectorstore.

    Creates the vectorstore on first call, then returns the cached instance
    for all subsequent calls. If the vectorstore doesn't exist, builds it automatically.

    Returns:
        InMemoryVectorStore: Cached vectorstore instance.
    """
    global _vectorstore
    if _vectorstore is None:
        if not DEFAULT_VECTORSTORE_PATH.exists():
            # Auto-build vectorstore if it doesn't exist
            print(
                f"Vectorstore not found at {DEFAULT_VECTORSTORE_PATH}. Building now..."
            )
            from data.data_generation.build_vectorstore import build_vectorstore

            build_vectorstore()
        with open(DEFAULT_VECTORSTORE_PATH, "rb") as f:
            _vectorstore = pickle.load(f)
    return _vectorstore


def get_product_retriever():
    """Lazy load the product documents retriever.

    Creates the retriever on first call, then returns the cached instance
    for all subsequent calls.

    Returns:
        VectorStoreRetriever: Cached retriever for product documents.
    """
    global _product_retriever
    if _product_retriever is None:
        vectorstore = get_vectorstore()
        _product_retriever = vectorstore.as_retriever(
            search_type="similarity",
            search_kwargs={
                "k": 3,
                "filter": lambda doc: doc.metadata.get("doc_type") == "product",
            },
        )
    return _product_retriever


def get_policy_retriever():
    """Lazy load the policy documents retriever.

    Creates the retriever on first call, then returns the cached instance
    for all subsequent calls.

    Returns:
        VectorStoreRetriever: Cached retriever for policy documents.
    """
    global _policy_retriever
    if _policy_retriever is None:
        vectorstore = get_vectorstore()
        _policy_retriever = vectorstore.as_retriever(
            search_type="similarity",
            search_kwargs={
                "k": 2,
                "filter": lambda doc: doc.metadata.get("doc_type") == "policy",
            },
        )
    return _policy_retriever


@tool(response_format="content_and_artifact")
def search_product_docs(query: str) -> tuple[str, list[Document]]:
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
        Tuple of (formatted_content, documents) where:
        - formatted_content: Clean string for the LLM with product info
        - documents: List of raw Document objects for downstream use and tracing
    """
    retriever = get_product_retriever()

    # Use retriever to get documents (better tracing in LangSmith)
    results = retriever.invoke(query)

    if not results:
        return "No relevant product documentation found.", []

    # Format results with sources for the LLM
    formatted_results = []
    for doc in results:
        product_name = doc.metadata.get("product_name", "Unknown Product")
        product_id = doc.metadata.get("product_id", "")
        formatted_results.append(f"[{product_name} ({product_id})]\n{doc.page_content}")

    # Return tuple: (content for LLM, raw docs as artifact)
    return "\n\n---\n\n".join(formatted_results), results


@tool(response_format="content_and_artifact")
def search_policy_docs(query: str) -> tuple[str, list[Document]]:
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
        Tuple of (formatted_content, documents) where:
        - formatted_content: Clean string for the LLM with policy info
        - documents: List of raw Document objects for downstream use and tracing
    """
    retriever = get_policy_retriever()

    # Use retriever to get documents (better tracing in LangSmith)
    results = retriever.invoke(query)

    if not results:
        return "No relevant policy information found.", []

    # Format results with sources for the LLM
    formatted_results = []
    for doc in results:
        policy_name = doc.metadata.get("policy_name", "Unknown Policy")
        formatted_results.append(f"[{policy_name}]\n{doc.page_content}")

    # Return tuple: (content for LLM, raw docs as artifact)
    return "\n\n---\n\n".join(formatted_results), results
