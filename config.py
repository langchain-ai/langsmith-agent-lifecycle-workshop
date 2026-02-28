"""
Workshop-wide configuration for the AI Engineering Lifecycle workshop.

All default settings can be customized via environment variables in .env file.
This makes it easy to adapt the workshop for different:
- Model providers (OpenAI, Anthropic, Azure, etc.)
- Model versions (GPT-4, Claude Sonnet, etc.)
- Performance profiles (fast models vs. high-quality models)
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

# ============================================================================
# MODEL CONFIGURATION
# ============================================================================

# Primary model used by all agents throughout the workshop
# Set WORKSHOP_MODEL in .env to change the model for all sections
# Examples:
#   - "anthropic:claude-haiku-4-5" (fast, cost-effective)
#   - "anthropic:claude-sonnet-4" (balanced)
#   - "openai:gpt-5-mini" (fast, OpenAI)
#   - "openai:gpt-5-nano" (lightweight, OpenAI)
DEFAULT_MODEL = os.getenv("WORKSHOP_MODEL", "anthropic:claude-haiku-4-5")

# ============================================================================
# EMBEDDING CONFIGURATION
# ============================================================================

# Embedding provider for document vectorstore
# Options: "huggingface" (local, no API key) or "openai" (requires OPENAI_API_KEY)
# Default is HuggingFace for backwards compatibility and no external dependencies
DEFAULT_EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "huggingface")

# ============================================================================
# RUNTIME CONFIGURATION
# ============================================================================


@dataclass
class Context:
    """Runtime configuration for all agents.

    This enables model selection in LangSmith Studio's configurable Assistants UI.
    When deployed, users can choose from these models via a dropdown.

    The model options are constrained to ensure compatibility and provide
    a curated experience in the workshop.
    """

    model: Literal[
        "anthropic:claude-haiku-4-5",
        "anthropic:claude-sonnet-4-5",
        "openai:gpt-5-mini",
        "openai:gpt-5-nano",
    ] = DEFAULT_MODEL


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
    BASE_PATH / "data" / "vector_stores" / f"techhub_vectorstore_{DEFAULT_EMBEDDING_PROVIDER}.pkl"
)

# ============================================================================
# DEPLOYMENT CONFIGURATION
# ============================================================================

# LangGraph deployment URL (optional, used by simulation system)
# Set LANGRAPH_DEPLOYMENT_URL in .env when running simulations against deployed graphs
DEFAULT_DEPLOYMENT_URL = os.getenv("LANGRAPH_DEPLOYMENT_URL")
