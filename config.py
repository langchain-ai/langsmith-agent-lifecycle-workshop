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
# MODEL CREDENTIALS (LangSmith LLM Gateway fallback)
# ============================================================================
#
# Some machines keep LLM credentials in a dotenv-style file that only interactive
# shells load, so a Jupyter kernel started by an IDE never sees them. Point
# GATEWAY_ENV_FILE at that file and, if no provider credential is set yet, its
# chat-model variables are loaded. Only those are taken -- never LangSmith
# project/tracing vars, which would redirect this workshop's traces.
#
# Precedence (first match wins, nothing is ever overwritten):
#   1. OPENAI_API_KEY / ANTHROPIC_API_KEY already in the environment or .env
#   2. LANGSMITH_GATEWAY=true  (the documented gateway path -- see .env.example)
#   3. the file named by GATEWAY_ENV_FILE, if set and readable
#
# Set LANGCHAIN_DISABLE_GATEWAY=1 to skip step 3.

_GATEWAY_ENV_FILE = Path(os.getenv("GATEWAY_ENV_FILE", "")) if os.getenv("GATEWAY_ENV_FILE") else None

# Only chat-model credentials.
_GATEWAY_VARS = (
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_CUSTOM_HEADERS",
)


def _gateway_enabled() -> bool:
    """LANGSMITH_GATEWAY is on for "true"/"1"/"yes" or a gateway URL (same rule as langchain-core)."""
    return os.getenv("LANGSMITH_GATEWAY", "").strip().lower() not in ("", "0", "false", "no", "off")


def _resolve_model_credentials() -> str:
    """Ensure a provider credential is available. Returns the source used."""
    if os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY"):
        return "environment"

    if _gateway_enabled():
        return "langsmith-gateway"

    if os.getenv("LANGCHAIN_DISABLE_GATEWAY") == "1":
        return "none (gateway disabled)"

    if _GATEWAY_ENV_FILE is None or not _GATEWAY_ENV_FILE.is_file():
        return "none"

    try:
        from dotenv import dotenv_values

        values = dotenv_values(_GATEWAY_ENV_FILE)
    except Exception:  # noqa: BLE001 - never block import on this
        return "none (gateway unreadable)"

    applied = False
    for name in _GATEWAY_VARS:
        value = values.get(name)
        if value and not os.getenv(name):
            os.environ[name] = value
            applied = True

    return "gateway-env-file" if applied else "none"


# Which credential source is in play. Never contains a secret -- safe to print.
MODEL_CREDENTIAL_SOURCE = _resolve_model_credentials()

# ============================================================================
# MODEL CONFIGURATION
# ============================================================================

# Primary model used by all agents throughout the workshop
# Set WORKSHOP_MODEL in .env to change the model for all sections
# Examples:
#   - "anthropic:claude-haiku-4-5" (fast, cost-effective)
#   - "anthropic:claude-sonnet-4" (balanced)
#   - "openai:gpt-5.4" (balanced, OpenAI — also serves as the LLM-as-judge model
#     in evaluators.py, so avoid dropping below this tier for Module 2 evals)
#   - "openai:gpt-5.4-mini" (fast/cheap, OpenAI)
DEFAULT_MODEL = os.getenv("WORKSHOP_MODEL", "anthropic:claude-haiku-4-5")

# Model for the advanced modules (Module 4 Deep Agents 201, Module 6 deployment).
# Deep agents plan, delegate, and write orchestration code, so they default to a
# stronger model than the intro modules. Set DEEP_AGENT_MODEL in .env to override,
# e.g. "anthropic:claude-sonnet-5-5". Without an override, the default follows the
# credentials you set: gpt-5.4 with an OpenAI key or the LLM Gateway (direct
# keys or LANGSMITH_GATEWAY both work with these model strings), Claude Sonnet 5.5
# with only an Anthropic key.
LLM_GATEWAY_ENABLED = _gateway_enabled()


def _default_deep_agent_model() -> str:
    if os.getenv("ANTHROPIC_API_KEY") and not os.getenv("OPENAI_API_KEY") and not LLM_GATEWAY_ENABLED:
        return "anthropic:claude-sonnet-5-5"
    return "openai:gpt-5.4"


DEEP_AGENT_MODEL = os.getenv("DEEP_AGENT_MODEL", _default_deep_agent_model())

# Smaller model from the same provider (so the same credentials work). Deep
# agents use it twice:
#   - Multi-model harness: focused subagents (lookups, single-product research)
#     run on it while the main agent plans and synthesizes on DEEP_AGENT_MODEL.
#   - Fault tolerance: the last fallback model (see DEEP_AGENT_FALLBACK_MODELS).
# Override with DEEP_AGENT_SMALL_MODEL in .env.
_SMALL_MODELS = {"openai": "openai:gpt-5.4-mini", "anthropic": "anthropic:claude-haiku-4-5"}
DEEP_AGENT_SMALL_MODEL = os.getenv(
    "DEEP_AGENT_SMALL_MODEL",
    _SMALL_MODELS.get(DEEP_AGENT_MODEL.split(":", 1)[0], DEEP_AGENT_MODEL),
)

# Fallback models for ModelFallbackMiddleware, tried in order once the main model
# has exhausted its retries. A model from the other provider comes first so an
# OpenAI outage doesn't take the agent down (gpt-5.4 -> Claude Sonnet 5.5), then
# the small model. The other provider is only used if its credentials are set:
# an API key, a GATEWAY_ENV_FILE loaded above, or LANGSMITH_GATEWAY (the
# workspace then needs that provider's secret; without it the call fails and the
# chain moves on). Override the first entry with DEEP_AGENT_FALLBACK_MODEL in .env.
_CROSS_PROVIDER_FALLBACKS = {"openai": "anthropic:claude-sonnet-5-5", "anthropic": "openai:gpt-5.4"}


def _has_credentials(model: str) -> bool:
    provider = model.split(":", 1)[0]
    return LLM_GATEWAY_ENABLED or bool(os.getenv(f"{provider.upper()}_API_KEY"))


DEEP_AGENT_FALLBACK_MODEL = os.getenv(
    "DEEP_AGENT_FALLBACK_MODEL",
    _CROSS_PROVIDER_FALLBACKS.get(DEEP_AGENT_MODEL.split(":", 1)[0], ""),
)
DEEP_AGENT_FALLBACK_MODELS = [
    m
    for m in (DEEP_AGENT_FALLBACK_MODEL, DEEP_AGENT_SMALL_MODEL)
    if m and m != DEEP_AGENT_MODEL and _has_credentials(m)
]

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
        "openai:gpt-5.4",
        "openai:gpt-5.4-mini",
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
    BASE_PATH
    / "data"
    / "vector_stores"
    / f"techhub_vectorstore_{DEFAULT_EMBEDDING_PROVIDER}.pkl"
)

# ============================================================================
# DEPLOYMENT CONFIGURATION
# ============================================================================

# LangGraph deployment URL (optional, used by simulation system)
# Set LANGGRAPH_DEPLOYMENT_URL in .env when running simulations against deployed graphs
DEFAULT_DEPLOYMENT_URL = os.getenv("LANGGRAPH_DEPLOYMENT_URL")
