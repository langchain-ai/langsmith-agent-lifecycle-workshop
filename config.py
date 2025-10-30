"""
Workshop-wide configuration for the AI Engineering Lifecycle workshop.

All default settings can be customized via environment variables in .env file.
This makes it easy to adapt the workshop for different:
- Model providers (OpenAI, Anthropic, Azure, etc.)
- Model versions (GPT-4, Claude Sonnet, etc.)
- Performance profiles (fast models vs. high-quality models)
"""

import os

# ============================================================================
# MODEL CONFIGURATION
# ============================================================================

# Primary model used by all agents throughout the workshop
# Set WORKSHOP_MODEL in .env to change the model for all sections
# Examples:
#   - "anthropic:claude-haiku-4-5" (fast, cost-effective)
#   - "anthropic:claude-sonnet-4" (balanced)
#   - "openai:gpt-4o-mini" (fast, OpenAI)
#   - "openai:gpt-4o" (high-quality, OpenAI)
DEFAULT_MODEL = os.getenv("WORKSHOP_MODEL", "anthropic:claude-haiku-4-5")

# Temperature for model responses (0.0 = deterministic, 1.0 = creative)
# Lower values recommended for structured tasks like customer support
DEFAULT_TEMPERATURE = float(os.getenv("WORKSHOP_TEMPERATURE", "0.0"))


# ============================================================================
# FUTURE CONFIGURATION
# ============================================================================
# As the workshop grows, additional settings can be added here:
#
# Embedding model for RAG:
# DEFAULT_EMBEDDING_MODEL = os.getenv(
#     "EMBEDDING_MODEL",
#     "sentence-transformers/all-MiniLM-L6-v2"
# )
#
# Data paths:
# DATABASE_PATH = os.getenv(
#     "DATABASE_PATH",
#     "./data/structured/techhub.db"
# )
#
# VECTOR_STORE_PATH = os.getenv(
#     "VECTOR_STORE_PATH",
#     "./data/vector_stores/techhub_vectorstore.pkl"
# )
