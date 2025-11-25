"""
Workshop-wide configuration for the AI Engineering Lifecycle workshop.

All default settings can be customized via environment variables in .env file.
This makes it easy to adapt the workshop for different:
- Model providers (OpenAI, Anthropic, Azure, etc.)
- Model versions (GPT-4, Claude Sonnet, etc.)
- Performance profiles (fast models vs. high-quality models)
"""

import os
from pathlib import Path

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

# ============================================================================
# DATA PATHS CONFIGURATION
# ============================================================================

# Determine the base path (works in both local dev and LS deployment environments)
if Path("/deps/langsmith-agent-lifecycle-workshop").exists():
    # Running in LangSmith deployment (data files are at /deps, not /api)
    BASE_PATH = Path("/deps/langsmith-agent-lifecycle-workshop")
else:
    # Running locally
    BASE_PATH = Path(__file__).parent

DEFAULT_DB_PATH = BASE_PATH / "data" / "structured" / "techhub.db"
DEFAULT_VECTORSTORE_PATH = (
    BASE_PATH / "data" / "vector_stores" / "techhub_vectorstore.pkl"
)
