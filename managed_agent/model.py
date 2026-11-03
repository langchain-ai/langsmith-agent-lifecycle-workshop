"""Pick the agent's model strings from whatever credentials this environment has.

Clone the repo and set ONE of these in managed_agent/.env; no code changes:

1. DEEP_AGENT_MODEL (explicit override), e.g. "anthropic:claude-sonnet-5-5"
   or "langsmith:anthropic/claude-sonnet-5-5".
2. OPENAI_API_KEY -> "openai:gpt-5.4" (direct provider call; OPENAI_BASE_URL
   is honoured if you route through a proxy).
3. ANTHROPIC_API_KEY only -> "anthropic:claude-sonnet-5-5".
4. Neither -> "langsmith:openai/gpt-5.4": the LangSmith LLM Gateway. The
   `langsmith:` provider authenticates with LANGSMITH_GATEWAY_API_KEY, falling back
   to LANGSMITH_API_KEY. LANGSMITH_API_KEY is reserved and never reaches a hosted
   deployment, so set LANGSMITH_GATEWAY_API_KEY in .env for `mda deploy`: a
   workspace-scoped LangSmith key whose workspace has the provider secrets.
   LANGSMITH_API_KEY_GATEWAY and LC_GATEWAY_KEY are accepted as aliases (copied
   into LANGSMITH_GATEWAY_API_KEY at import, here and in the deployment).
"""

import os

GATEWAY_KEY_ALIASES = ("LANGSMITH_API_KEY_GATEWAY", "LC_GATEWAY_KEY")
if not os.getenv("LANGSMITH_GATEWAY_API_KEY"):
    if alias := next((a for a in GATEWAY_KEY_ALIASES if os.getenv(a)), None):
        os.environ["LANGSMITH_GATEWAY_API_KEY"] = os.environ[alias]

DEFAULT_MODELS = {"openai": "gpt-5.4", "anthropic": "claude-sonnet-5-5"}


def resolve_model() -> str:
    if explicit := os.getenv("DEEP_AGENT_MODEL"):
        return explicit
    if os.getenv("OPENAI_API_KEY"):
        return f"openai:{DEFAULT_MODELS['openai']}"
    if os.getenv("ANTHROPIC_API_KEY"):
        return f"anthropic:{DEFAULT_MODELS['anthropic']}"
    return f"langsmith:openai/{DEFAULT_MODELS['openai']}"


# Smaller model on the same route (same credentials). Used for the specialists
# (multi-model harness) and as the last ModelFallbackMiddleware backup.
SMALL_MODELS = {"openai": "gpt-5.4-mini", "anthropic": "claude-haiku-4-5"}


def resolve_small_model() -> str:
    if explicit := os.getenv("DEEP_AGENT_SMALL_MODEL"):
        return explicit
    main = resolve_model()
    route, _, rest = main.partition(":")
    if route == "langsmith":  # "langsmith:openai/gpt-5.4"
        provider = rest.split("/", 1)[0]
        return f"langsmith:{provider}/{SMALL_MODELS[provider]}" if provider in SMALL_MODELS else main
    return f"{route}:{SMALL_MODELS[route]}" if route in SMALL_MODELS else main


# ModelFallbackMiddleware chain: the other provider first (covers an OpenAI outage),
# then the small model. DEEP_AGENT_FALLBACK_MODEL overrides the first entry.
CROSS_PROVIDER = {"openai": ("anthropic", "claude-sonnet-5-5"), "anthropic": ("openai", "gpt-5.4")}


def resolve_fallback_models() -> list[str]:
    main = resolve_model()
    route, _, rest = main.partition(":")
    provider = rest.split("/", 1)[0] if route == "langsmith" else route
    chain = []
    if explicit := os.getenv("DEEP_AGENT_FALLBACK_MODEL"):
        chain.append(explicit)
    elif provider in CROSS_PROVIDER:
        other, name = CROSS_PROVIDER[provider]
        if os.getenv(f"{other.upper()}_API_KEY"):
            chain.append(f"{other}:{name}")
        elif route == "langsmith" or os.getenv("LANGSMITH_GATEWAY_API_KEY"):
            # Gateway in use: the other provider through it. If the workspace lacks that
            # provider's secret the call fails (424) and the chain moves on.
            chain.append(f"langsmith:{other}/{name}")
        # Direct key for one provider only: no cross-provider fallback.
    small = resolve_small_model()
    if small != main:
        chain.append(small)
    return chain
