"""TypeSafe's Jev decision model through the LangSmith LLM Gateway (Module 4).

Jev answers typed questions about a piece of state with probabilities instead of
generated text. `langchain-typesafe` wraps it as `TypeSafeClassifier`, a LangChain
Runnable, so every call is traced in LangSmith like any other model run:

- Noul:   yes/no, answered as the probability of "yes"
- Choice: one option from a fixed set, with per-option probabilities and a confidence
- Score:  a position on an ordered scale. The score runs from 0 to (levels - 1) and is an
          expected value, so compare it against bands, never with ==

Credentials: the Gateway holds the TypeSafe key and callers authenticate with a
LangSmith key (model ids take the `typesafe/` prefix). The Gateway reads provider
secrets from the workspace the key belongs to, so that workspace needs a
TYPESAFE_API_KEY provider secret (otherwise every call returns 424 Failed Dependency).

- JEV_WORKSPACE_ID: set it when your key's default workspace isn't the one holding the
  TYPESAFE_API_KEY secret (for example a personal access token with access to several
  workspaces). It is sent as the X-Tenant-Id header, together with LANGSMITH_API_KEY.
- Without it, the Gateway key is used: LANGSMITH_GATEWAY_API_KEY (or its aliases
  LANGSMITH_API_KEY_GATEWAY / LC_GATEWAY_KEY), then LANGSMITH_API_KEY.
- Region: LANGSMITH_GATEWAY set to a URL is used as the Gateway; otherwise an EU
  LANGSMITH_ENDPOINT selects the EU Gateway, and anything else the US one.

Data: TypeSafe offers zero data retention per org on request and no BAA. Use synthetic
or test data (TechHub is synthetic), not customer data, until your security team has
reviewed it.
"""

import os
from functools import lru_cache

import httpx2
from langchain_typesafe import TypeSafeClassifier

_US_GATEWAY, _EU_GATEWAY = "https://gateway.smith.langchain.com", "https://eu.gateway.smith.langchain.com"
_KEY_VARS = ("LANGSMITH_GATEWAY_API_KEY", "LANGSMITH_API_KEY_GATEWAY", "LC_GATEWAY_KEY", "LANGSMITH_API_KEY")


def _gateway_url() -> str:
    """The Gateway base URL: LANGSMITH_GATEWAY when it is a URL, else by LangSmith region."""
    configured = os.getenv("LANGSMITH_GATEWAY", "").strip()
    if configured.startswith("https://"):
        return configured.rstrip("/")
    return _EU_GATEWAY if "://eu." in os.getenv("LANGSMITH_ENDPOINT", "") else _US_GATEWAY


def _api_key() -> str:
    """LANGSMITH_API_KEY with JEV_WORKSPACE_ID (it picks the workspace), else the Gateway key."""
    names = ("LANGSMITH_API_KEY",) if os.getenv("JEV_WORKSPACE_ID") else _KEY_VARS
    if key := next((os.environ[n] for n in names if os.getenv(n)), None):
        return key
    raise RuntimeError("Jev needs LANGSMITH_GATEWAY_API_KEY or LANGSMITH_API_KEY (a workspace-scoped key).")


GATEWAY_URL = _gateway_url()
# Pinned: probability thresholds (like the 0.7 cascade in Module 4 S3) don't transfer
# between Jev versions. Re-check thresholds before bumping, or use "typesafe/jev-latest".
JEV_MODEL = os.getenv("JEV_MODEL", "typesafe/jev-1.14.0")
_TIMEOUT = 30.0  # seconds, the classifier's own default


@lru_cache(maxsize=4)
def jev_classifier(model: str = JEV_MODEL) -> TypeSafeClassifier:
    """A Jev classifier routed through the LangSmith Gateway, built on first use.

    Examples:
        >>> from langchain_typesafe import Noul
        >>> r = jev_classifier().invoke({"state": "my screen arrived cracked",
        ...                              "questions": {"damaged": Noul(instructions="Is an item damaged?")}})
        >>> r.nouls["damaged"].noul
        0.99
    """
    clients = {}
    if workspace := os.getenv("JEV_WORKSPACE_ID"):
        headers = {"X-Tenant-Id": workspace}
        clients = {
            "client": httpx2.Client(headers=headers, timeout=_TIMEOUT),
            "async_client": httpx2.AsyncClient(headers=headers, timeout=_TIMEOUT),
        }
    return TypeSafeClassifier(model=model, api_key=_api_key(), base_url=_gateway_url(), **clients)
