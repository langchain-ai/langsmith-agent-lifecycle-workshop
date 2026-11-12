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

Which key Jev uses, first match wins (used for Jev only; model calls keep their own key):

1. JEV_API_KEY: a key from a workspace that has Jev, e.g. a workshop key allowlisted to
   TypeSafe. Separate on purpose: an allowlisted key would break other model calls.
2. JEV_WORKSPACE_ID: LANGSMITH_API_KEY, sent with X-Tenant-Id set to this workspace, for
   keys whose default workspace isn't the one holding the TYPESAFE_API_KEY secret.
3. LC_GATEWAY_KEY: the IT-provisioned Gateway key on LangChain-managed Macs, which has Jev.
   Read from the environment, else from the file named by GATEWAY_ENV_FILE
   (/etc/lc_internal/gateway_env), since a Jupyter started from a terminal doesn't see it.
4. LANGSMITH_GATEWAY_API_KEY (or LANGSMITH_API_KEY_GATEWAY), then LANGSMITH_API_KEY.
- Region: LANGSMITH_GATEWAY set to a URL is used as the Gateway; otherwise an EU
  LANGSMITH_ENDPOINT selects the EU Gateway, and anything else the US one.

Data: TypeSafe offers zero data retention per org on request and no BAA. Use synthetic
or test data (TechHub is synthetic), not customer data, until your security team has
reviewed it.
"""

import os
from functools import lru_cache
from pathlib import Path

import httpx2
from dotenv import dotenv_values
from langchain_typesafe import TypeSafeClassifier

_US_GATEWAY, _EU_GATEWAY = "https://gateway.smith.langchain.com", "https://eu.gateway.smith.langchain.com"
_FALLBACK_KEY_VARS = ("LANGSMITH_GATEWAY_API_KEY", "LANGSMITH_API_KEY_GATEWAY", "LANGSMITH_API_KEY")


def _gateway_url() -> str:
    """The Gateway base URL: LANGSMITH_GATEWAY when it is a URL, else by LangSmith region."""
    configured = os.getenv("LANGSMITH_GATEWAY", "").strip()
    if configured.startswith("https://"):
        return configured.rstrip("/")
    return _EU_GATEWAY if "://eu." in os.getenv("LANGSMITH_ENDPOINT", "") else _US_GATEWAY


def _gateway_file_key() -> str | None:
    """LC_GATEWAY_KEY from the IT gateway file named by GATEWAY_ENV_FILE, if there is one."""
    path = os.getenv("GATEWAY_ENV_FILE")
    if not path or not Path(path).is_file():
        return None
    return dotenv_values(path).get("LC_GATEWAY_KEY") or None


def jev_key_source() -> tuple[str, str] | None:
    """(where the key comes from, the key) in the order in the module docstring. Print only the first."""
    if key := os.getenv("JEV_API_KEY"):
        return "JEV_API_KEY", key
    if os.getenv("JEV_WORKSPACE_ID") and (key := os.getenv("LANGSMITH_API_KEY")):
        return "LANGSMITH_API_KEY + JEV_WORKSPACE_ID", key
    if key := os.getenv("LC_GATEWAY_KEY"):
        return "LC_GATEWAY_KEY", key
    if key := _gateway_file_key():
        return "LC_GATEWAY_KEY (GATEWAY_ENV_FILE)", key
    return next(((name, os.environ[name]) for name in _FALLBACK_KEY_VARS if os.getenv(name)), None)


def _api_key() -> str:
    if source := jev_key_source():
        return source[1]
    raise RuntimeError("Jev needs JEV_API_KEY, LC_GATEWAY_KEY, or a LangSmith key from a workspace with Jev.")


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
    source = jev_key_source()
    if source and source[0] == "LANGSMITH_API_KEY + JEV_WORKSPACE_ID":
        headers = {"X-Tenant-Id": os.environ["JEV_WORKSPACE_ID"]}
        clients = {
            "client": httpx2.Client(headers=headers, timeout=_TIMEOUT),
            "async_client": httpx2.AsyncClient(headers=headers, timeout=_TIMEOUT),
        }
    return TypeSafeClassifier(model=model, api_key=_api_key(), base_url=_gateway_url(), **clients)
