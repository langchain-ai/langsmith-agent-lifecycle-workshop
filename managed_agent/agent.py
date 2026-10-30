"""TechHub support agent as a Managed Deep Agent (Module 6).

The same harness as Module 4 (`agents/deep_support_agent.py`), declared with
`define_deep_agent`. MDA supplies what the factory wired by hand:

- instructions.md + skills/   -> synced to Context Hub (editable without redeploy)
- memory.py                   -> durable agent memory (shared by all callers)
- sandbox/                    -> a per-thread LangSmith sandbox, provisioned by setup.sh
- schedules/                  -> LangSmith cron jobs
- identity.py                 -> caller authentication
- checkpointer, store, backend, and the Agent Server runtime

Production guardrails declared here (the parts MDA does not supply):
- Fault tolerance: retries, a cross-provider fallback (Claude Sonnet 5.5, then the
  small model), and call limits (middleware/fault_tolerance.py)
- PII redaction on user input, model output, and tool results
- Customer-scope guard (identity claims first, then run context) and HITL on refunds
- A multi-model harness: specialists run on the smaller model from model.py
"""

from dataclasses import dataclass

from deepagents.middleware.subagents import GENERAL_PURPOSE_SUBAGENT
from langchain.agents.middleware import PIIMiddleware
from managed_deepagents import define_deep_agent

from middleware.customer_scope import customer_scope_guard, verified_customer_prompt
from middleware.fault_tolerance import fault_tolerance_middleware
from model import resolve_fallback_models, resolve_model, resolve_small_model
from tools.support import (
    get_customer_orders,
    get_delayed_orders,
    get_order_items,
    get_order_status,
    get_product_info,
    request_refund,
)


@dataclass
class SupportContext:
    """Set by the calling application (or a schedule), never by the conversation.

    In production, issue `customer_id` and `role` as identity token claims instead
    (see identity.py); the guard prefers claims and refuses a mismatching context.
    """

    customer_id: str | None = None
    role: str = "customer"


SMALL_MODEL = resolve_small_model()
FALLBACK_MODELS = resolve_fallback_models()
SPECIALIST_FALLBACKS = [m for m in FALLBACK_MODELS if m != SMALL_MODEL]  # specialists already run on SMALL_MODEL
ORDER_TOOLS = [get_order_status, get_order_items, get_customer_orders, get_product_info, get_delayed_orders]


def pii_middleware() -> list:
    """Redact emails and mask card numbers in user input, model output, and tool results."""
    return [
        PIIMiddleware("email", strategy="redact", apply_to_input=True, apply_to_output=True, apply_to_tool_results=True),
        PIIMiddleware(
            "credit_card", strategy="mask", apply_to_input=True, apply_to_output=True, apply_to_tool_results=True
        ),
    ]


ORDER_SPECIALIST = {
    "name": "order-specialist",
    "description": "Looks up TechHub orders, order items, prices paid, product availability, the verified "
    "customer's order history, and (for ops jobs) delayed orders.",
    "system_prompt": "You are TechHub's order specialist. Use your tools and report exactly what they return; "
    "if a tool refuses access, say so plainly.",
    "model": SMALL_MODEL,
    "tools": ORDER_TOOLS,
    "middleware": [
        *fault_tolerance_middleware(
            fallback_models=SPECIALIST_FALLBACKS, retry_tools=ORDER_TOOLS, model_call_limit=10, tool_call_limit=15
        ),
        *pii_middleware(),
        verified_customer_prompt,
        customer_scope_guard,
    ],
}

PRODUCT_POLICY_SPECIALIST = {
    "name": "product-policy-specialist",
    "description": "Answers product spec, compatibility, return, warranty, and shipping questions from the "
    "TechHub docs in the sandbox.",
    "model": SMALL_MODEL,
    # Explicit empty list: a spec without "tools" inherits the main agent's tools
    # (request_refund) without the customer-scope guard. The sandbox file tools are added by the harness.
    "tools": [],
    "middleware": [
        *fault_tolerance_middleware(fallback_models=SPECIALIST_FALLBACKS, model_call_limit=10, tool_call_limit=15),
        *pii_middleware(),
    ],
    "system_prompt": "You are TechHub's product and policy specialist. Search /workspace/techhub/documents with "
    "grep and read_file, then quote the specific terms that answer the question and name the source file.",
}

# Replaces the auto-added `general-purpose` subagent, which would otherwise get the main
# agent's tools (request_refund) without the guard. Tool-less: built-in file tools only.
GENERAL_PURPOSE = {
    **GENERAL_PURPOSE_SUBAGENT,
    "model": SMALL_MODEL,
    "tools": [],
    "middleware": [
        *fault_tolerance_middleware(fallback_models=SPECIALIST_FALLBACKS, model_call_limit=10, tool_call_limit=15),
        *pii_middleware(),
    ],
}

agent = define_deep_agent(
    name="techhub-support",
    model=resolve_model(),  # gpt-5.4 by default via a direct key or the LangSmith Gateway (model.py)
    tools=[request_refund],
    subagents=[ORDER_SPECIALIST, PRODUCT_POLICY_SPECIALIST, GENERAL_PURPOSE],
    middleware=[
        *fault_tolerance_middleware(
            fallback_models=FALLBACK_MODELS,  # Claude Sonnet 5.5, then the small model
            model_call_limit=40,
            tool_call_limit=80,
            tool_limits={"task": 20},
        ),
        *pii_middleware(),
        verified_customer_prompt,
        customer_scope_guard,
    ],
    interrupt_on={"request_refund": True},
    context_schema=SupportContext,
)
