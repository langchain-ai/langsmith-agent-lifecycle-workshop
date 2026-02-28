"""
Build the InMemoryVectorStore from TechHub markdown documents.

This script:
1. Loads product and policy markdown documents
2. Splits them into chunks with metadata
3. Creates embeddings using configured provider (HuggingFace or OpenAI)
4. Builds an InMemoryVectorStore
5. Saves it to a pickle file for quick loading

Embedding providers:
- HuggingFace (default): Local model, no API key needed
- OpenAI: Requires OPENAI_API_KEY, uses text-embedding-3-small

Configure via EMBEDDING_PROVIDER env var in .env:
    EMBEDDING_PROVIDER=huggingface  # default
    EMBEDDING_PROVIDER=openai       # requires OPENAI_API_KEY

Run this script once to build the vectorstore:
    python data/data_generation/build_vectorstore.py
"""

import pickle
from pathlib import Path

from langchain_community.document_loaders import TextLoader
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import BASE_PATH, DEFAULT_EMBEDDING_PROVIDER, DEFAULT_VECTORSTORE_PATH


def get_embeddings(provider: str = "huggingface"):
    """Get embeddings based on the configured provider.

    Args:
        provider: Either "huggingface" (local, no API key) or "openai" (requires OPENAI_API_KEY)

    Returns:
        Embeddings instance for the specified provider
    """
    if provider == "openai":
        return OpenAIEmbeddings(model="text-embedding-3-small")
    else:
        return HuggingFaceEmbeddings(model_name="sentence-transformers/all-mpnet-base-v2")


def build_vectorstore():
    """Build and save the TechHub vectorstore."""

    print("🔧 Building TechHub VectorStore...")
    print("=" * 60)

    # Use centralized BASE_PATH from config (handles local vs deployment)
    project_root = BASE_PATH
    print(f"   Using project root: {project_root}")

    # Initialize embeddings based on configured provider
    print(f"\n1. Loading embedding model (provider: {DEFAULT_EMBEDDING_PROVIDER})...")
    embeddings = get_embeddings(DEFAULT_EMBEDDING_PROVIDER)
    if DEFAULT_EMBEDDING_PROVIDER == "openai":
        print("   ✓ OpenAI embeddings loaded (text-embedding-3-small)")
    else:
        print("   ✓ HuggingFace embeddings loaded (sentence-transformers/all-mpnet-base-v2)")

    # Load product documents
    print("\n2. Loading product documents...")
    product_docs = []
    products_dir = project_root / "data/documents/products"
    for md_file in sorted(products_dir.glob("*.md")):
        loader = TextLoader(str(md_file), encoding="utf-8")
        product_docs.extend(loader.load())

    # Add metadata to product docs
    for doc in product_docs:
        doc.metadata["doc_type"] = "product"
        # Extract product_id from filename (e.g., TECH-LAP-001.md)
        product_id = Path(doc.metadata["source"]).stem
        doc.metadata["product_id"] = product_id

        # Extract product name from first line (usually "# Product Name")
        first_line = doc.page_content.split("\n")[0]
        if first_line.startswith("# "):
            doc.metadata["product_name"] = first_line[2:].strip()

    print(f"   ✓ Loaded {len(product_docs)} product documents")

    # Load policy documents
    print("\n3. Loading policy documents...")
    policy_docs = []
    policies_dir = project_root / "data/documents/policies"
    for md_file in sorted(policies_dir.glob("*.md")):
        loader = TextLoader(str(md_file), encoding="utf-8")
        policy_docs.extend(loader.load())

    # Add metadata to policy docs
    for doc in policy_docs:
        doc.metadata["doc_type"] = "policy"
        policy_name = Path(doc.metadata["source"]).stem
        doc.metadata["policy_name"] = policy_name

    print(f"   ✓ Loaded {len(policy_docs)} policy documents")

    # Combine all documents
    all_docs = product_docs + policy_docs
    print(f"\n4. Total documents: {len(all_docs)}")

    # Split documents into chunks
    print("\n5. Splitting documents into chunks...")
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        add_start_index=True,  # Track position in original document
    )
    splits = text_splitter.split_documents(all_docs)

    product_chunks = [s for s in splits if s.metadata["doc_type"] == "product"]
    policy_chunks = [s for s in splits if s.metadata["doc_type"] == "policy"]

    print(f"   ✓ Created {len(splits)} total chunks")
    print(f"     - Products: {len(product_chunks)} chunks")
    print(f"     - Policies: {len(policy_chunks)} chunks")

    # Create vectorstore with embeddings
    print("\n6. Creating vectorstore (this may take a minute)...")
    vectorstore = InMemoryVectorStore.from_documents(
        documents=splits, embedding=embeddings
    )
    print("   ✓ Vectorstore created")

    # Save to file
    print("\n7. Saving vectorstore...")
    output_path = DEFAULT_VECTORSTORE_PATH
    output_path.parent.mkdir(exist_ok=True)

    # Store vectorstore data and provider info
    # Note: We clear embeddings before pickling to avoid serialization issues with OpenAI
    # The embeddings will be reconstructed on load based on the provider
    vectorstore_data = {
        "store": vectorstore.store,  # The actual vector data
        "provider": DEFAULT_EMBEDDING_PROVIDER,  # Provider used for embeddings
    }

    with open(output_path, "wb") as f:
        pickle.dump(vectorstore_data, f)

    print(f"   ✓ Saved to {output_path}")

    print("\n" + "=" * 60)
    print("✅ VectorStore built successfully!")
    print(f"📊 Summary:")
    print(f"   - {len(product_docs)} product documents → {len(product_chunks)} chunks")
    print(f"   - {len(policy_docs)} policy documents → {len(policy_chunks)} chunks")
    print(f"   - Total: {len(splits)} chunks in vectorstore")
    print(f"   - Saved to: {output_path}")


if __name__ == "__main__":
    build_vectorstore()
