"""Check the workshop setup before you start: which model path is active, and that it answers.

    uv run python verify_setup.py              # resolve the config, then one call per model
    uv run python verify_setup.py --no-calls   # resolve and print only, no model calls

It resolves credentials the same way the notebooks do (config.py), prints which path
is in play (direct provider keys, the LLM Gateway, or a gateway env file) and which
variable supplied each credential, then sends one short message to every model the
modules use. Variable names only: no secret value is ever printed.
"""

import argparse
import os
import sys

from dotenv import load_dotenv

load_dotenv()

import config  # noqa: E402  (after load_dotenv, like the notebooks)

FIXES = {
    "424": "the key's workspace has no secret for this provider. Add it under Settings > Integrations > "
    "Provider secrets, or use a key from a workspace that has it (the Gateway reads the key's own workspace)",
    "403": "the key lacks the gateway:invoke permission. Ask a workspace admin for a role or service key with it",
    "Missing credentials": "no model credential. Set OPENAI_API_KEY / ANTHROPIC_API_KEY, or LANGSMITH_GATEWAY=true "
    "with a workspace-scoped LANGSMITH_GATEWAY_API_KEY",
}


GATEWAY_401 = ("LangSmith rejected the key. Check it, and that it's workspace-scoped: organization-scoped keys "
               "aren't supported for the Gateway")
DIRECT_401 = "the provider rejected the key. Check OPENAI_API_KEY / ANTHROPIC_API_KEY in .env"


def explain(exc: Exception, gateway_on: bool) -> str:
    text = f"{type(exc).__name__}: {exc}"
    fixes = {**FIXES, "401": GATEWAY_401 if gateway_on else DIRECT_401}
    for marker, fix in fixes.items():
        if marker in text:
            return f"{text[:140]}\n      fix: {fix}"
    return text[:200]


def present(*names: str) -> str:
    found = [n for n in names if os.getenv(n)]
    return ", ".join(found) if found else "none"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--no-calls", action="store_true", help="skip the model calls")
    args = parser.parse_args()

    gateway_on = config.LLM_GATEWAY_ENABLED or "gateway.smith.langchain.com" in os.getenv("OPENAI_BASE_URL", "")
    print("── Model access ─────────────────────────────────────────")
    print(f"path              : {config.MODEL_CREDENTIAL_SOURCE}")
    print(f"provider keys     : {present('OPENAI_API_KEY', 'ANTHROPIC_API_KEY')}")
    print(f"gateway           : {'on' if gateway_on else 'off'}"
          f" (LANGSMITH_GATEWAY={'set' if os.getenv('LANGSMITH_GATEWAY') else 'unset'},"
          f" base URLs: {present('OPENAI_BASE_URL', 'ANTHROPIC_BASE_URL')})")
    if config.MODEL_CREDENTIAL_SOURCE == "gateway-env-file":
        key_from = "the provider-key variables loaded from GATEWAY_ENV_FILE"
    elif config.LLM_GATEWAY_ENABLED:
        key_from = config.GATEWAY_KEY_SOURCE or "LANGSMITH_API_KEY (fallback: it must be workspace-scoped)"
    elif gateway_on:
        key_from = "the provider-key variables (base URLs point at the Gateway)"
    elif config.MODEL_CREDENTIAL_SOURCE.startswith("none"):
        key_from = "none: no model credential is set (see the README's Model access section)"
    else:
        key_from = "n/a (direct provider keys)"
    print(f"gateway key from  : {key_from}")
    print(f"gateway env file  : {os.getenv('GATEWAY_ENV_FILE') or 'unset'}")
    print(f"langsmith key     : {'set' if os.getenv('LANGSMITH_API_KEY') else 'MISSING'}"
          f" · endpoint {os.getenv('LANGSMITH_ENDPOINT') or 'https://api.smith.langchain.com (default)'}")
    from utils.jev import jev_key_source

    jev_source = jev_key_source()
    print(f"jev key from      : {jev_source[0] if jev_source else 'MISSING (Jev cells skip themselves)'}")
    print("── Models ───────────────────────────────────────────────")
    models = {
        "workshop (M1-3)": config.DEFAULT_MODEL,
        "deep agent (M4)": config.DEEP_AGENT_MODEL,
        "small (M4)": config.DEEP_AGENT_SMALL_MODEL,
    }
    models.update({f"fallback {i} (M4)": m for i, m in enumerate(config.DEEP_AGENT_FALLBACK_MODELS, 1)})
    for label, model in models.items():
        print(f"{label:<17} : {model}")
    print(f"vectorstore       : {'found' if config.DEFAULT_VECTORSTORE_PATH.exists() else 'MISSING: run data/data_generation/build_vectorstore.py'}")

    if args.no_calls:
        return 0

    print("── Calls ────────────────────────────────────────────────")
    from langchain.chat_models import init_chat_model

    failed = 0
    for model in dict.fromkeys(models.values()):
        try:
            init_chat_model(model).invoke("Reply with the single word: ok")
            print(f"✓ {model}")
        except Exception as exc:  # noqa: BLE001 - report every failure, keep going
            failed += 1
            print(f"✗ {model}\n      {explain(exc, gateway_on)}")
    try:
        from langchain_typesafe import Noul

        from utils.jev import jev_classifier

        r = jev_classifier().invoke({"state": "ping", "questions": {"q": Noul(instructions="Is this a greeting?")}})
        print(f"✓ Jev ({r.nouls['q'].noul:.2f}), Module 4 Section 3 and Module 5 Section 4")
    except Exception as exc:  # noqa: BLE001 - Jev is optional: its cells skip themselves
        print(f"• Jev unavailable (optional; Module 4 Section 3 and Module 5 Section 4 skip its cells)\n      {explain(exc, True)}")

    print("─────────────────────────────────────────────────────────")
    print("✅ Ready" if not failed else f"❌ {failed} model(s) failed: see the fix lines above")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
