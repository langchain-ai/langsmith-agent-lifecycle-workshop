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

- LANGSMITH_API_KEY is used by default.
- JEV_WORKSPACE_ID: set it when your key's default workspace isn't the one holding the
  TYPESAFE_API_KEY secret (for example a personal access token with access to several
  workspaces). It is sent as the X-Tenant-Id header.

Data: TypeSafe offers zero data retention per org on request and no BAA. Use synthetic
or test data (TechHub is synthetic), not customer data, until your security team has
reviewed it.
"""

import os
from functools import lru_cache

import httpx2
from langchain_typesafe import TypeSafeClassifier

GATEWAY_URL = "https://gateway.smith.langchain.com"
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
    return TypeSafeClassifier(model=model, api_key=os.environ["LANGSMITH_API_KEY"], base_url=GATEWAY_URL, **clients)
