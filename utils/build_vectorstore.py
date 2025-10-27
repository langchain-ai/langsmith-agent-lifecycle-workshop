"""
Build the InMemoryVectorStore from TechHub markdown documents.

This script:
1. Loads product and policy markdown documents
2. Splits them into chunks with metadata
3. Creates embeddings using small, local HuggingFace model (no API key needed)
4. Builds an InMemoryVectorStore
5. Saves it to a pickle file for quick loading

Run this script once to build the vectorstore:
    python utils/build_vectorstore.py
"""

import pickle
from pathlib import Path

from langchain_community.document_loaders import TextLoader
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter


def build_vectorstore():
    """Build and save the TechHub vectorstore."""

    print("🔧 Building TechHub VectorStore...")
    print("=" * 60)

    # Initialize embeddings (local model, no API key needed)
    print("\n1. Loading embedding model (sentence-transformers/all-mpnet-base-v2)...")
    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-mpnet-base-v2"
    )
    print("   ✓ Embedding model loaded")

    # Load product documents
    print("\n2. Loading product documents...")
    product_docs = []
    products_dir = Path("data/documents/products")
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
    policies_dir = Path("data/documents/policies")
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
    output_dir = Path("data/vector_stores")
    output_dir.mkdir(exist_ok=True)

    output_path = output_dir / "techhub_vectorstore.pkl"
    with open(output_path, "wb") as f:
        pickle.dump(vectorstore, f)

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
