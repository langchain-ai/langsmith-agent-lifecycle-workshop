"""Customer-scope guard for the Managed Deep Agent (same idea as Module 4).

MDA hands every run a context set by the caller's application (for example
`{"customer_id": "CUST-003"}`) or by a schedule (`{"role": "ops"}`). Tools run
with the server's access, so authorization is enforced around each tool call:

- `customer_id` arguments must match the verified customer.
- `order_id` arguments must belong to the verified customer.
- Ops-only tools require `role == "ops"`.

Where the customer ID and role come from (most trusted first):

1. The authenticated caller's token claims (`principal.claims["customer_id"]`,
   `principal.claims["role"]`), when identity.py uses a JWT, Supabase, or backend
   provider that issues them. The caller can't forge these.
2. The run context, set by the calling application or a schedule. With the
   default LangSmith API-key identity every caller is a trusted workspace
   service, so the workshop uses this path.

If both are present and disagree, the guard refuses: a caller can't widen its
own access by passing a different `customer_id` in the context.

Agent Server runs agents asynchronously, so both middlewares implement the
async hooks (`awrap_*`) as well as the sync ones.
"""

import asyncio
import re
import sqlite3
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import SystemMessage, ToolMessage

from tools.support import DB_PATH

OPS_ONLY_TOOLS = {"get_delayed_orders"}


def _context_value(runtime: Any, key: str):
    context = getattr(runtime, "context", None)
    if isinstance(context, dict):
        return context.get(key)
    return getattr(context, key, None)


def _claim(runtime: Any, key: str):
    """A verified claim from the caller's identity token, if identity provides one."""
    server_info = getattr(runtime, "server_info", None)
    principal = getattr(server_info, "principal", None)
    claims = getattr(principal, "claims", None) or {}
    return claims.get(key)


def _identity_value(runtime: Any, key: str) -> tuple[str | None, bool]:
    """Return (value, conflict). Token claims win over the run context."""
    claimed, passed = _claim(runtime, key), _context_value(runtime, key)
    if claimed is not None:
        return claimed, passed is not None and passed != claimed
    return passed, False


def _order_owner(order_id: str) -> str | None:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("SELECT customer_id FROM orders WHERE order_id = ?", (order_id,)).fetchone()
    return row[0] if row else None


# Arguments that identify a customer or their data. Only customer_id and order_id are checked
# below; any other match is refused rather than allowed through unchecked.
_SCOPED_ARG = re.compile(r"customer|order|account|email", re.IGNORECASE)


def _refuse(request, reason: str) -> ToolMessage:
    return ToolMessage(
        content=f"Access denied: {reason}",
        tool_call_id=request.tool_call["id"],
        name=request.tool_call["name"],
        status="error",
    )



def _append_to_system(request, note: str):
    """Append a text block to the system message, keeping earlier middleware's content blocks.

    `request.override(system_prompt=...)` is deprecated: it rebuilds the message from plain
    text and drops blocks (e.g. prompt-cache markers) added by the harness middleware.
    """
    current = request.system_message.content if request.system_message else []
    blocks = [{"type": "text", "text": current}] if isinstance(current, str) else list(current)
    return request.override(system_message=SystemMessage(content=[*blocks, {"type": "text", "text": note}]))


class VerifiedCustomerPrompt(AgentMiddleware):
    """Tell the model who the application verified; the guard still enforces it."""

    def _with_note(self, request):
        customer_id, conflict = _identity_value(request.runtime, "customer_id")
        role, _ = _identity_value(request.runtime, "role")
        if conflict:
            note = "\n\nThe customer ID in the run context does not match the signed-in customer. Treat the customer as unverified."
        elif role == "ops":
            note = "\n\nThis run is an operations job (role: ops), not a customer conversation."
        elif customer_id:
            note = (
                f"\n\nVerified customer for this conversation: {customer_id}. "
                "When delegating account or order lookups, pass this customer ID to the specialist."
            )
        else:
            note = "\n\nNo customer is verified in this conversation."
        return _append_to_system(request, note)

    def wrap_model_call(self, request, handler):
        return handler(self._with_note(request))

    async def awrap_model_call(self, request, handler):
        return await handler(self._with_note(request))


class CustomerScopeGuard(AgentMiddleware):
    """Block tool calls outside the verified customer's data, and ops tools for non-ops callers."""

    def _check(self, request) -> ToolMessage | None:
        name = request.tool_call["name"]
        args = request.tool_call.get("args", {}) or {}

        if name in OPS_ONLY_TOOLS:
            role, _ = _identity_value(request.runtime, "role")
            if role != "ops":
                return _refuse(request, f"{name} is an operations tool and requires the ops role.")
            return None

        unknown = [k for k in args if _SCOPED_ARG.search(k) and k not in ("customer_id", "order_id")]
        if unknown:  # fail closed: a new tool must be taught to the guard before it can run
            return _refuse(request, f"the argument {unknown[0]!r} looks customer-scoped but this guard can't check it.")
        if "customer_id" not in args and "order_id" not in args:
            return None

        verified, conflict = _identity_value(request.runtime, "customer_id")
        if conflict:
            return _refuse(request, "the run context names a different customer than the signed-in caller.")
        if not verified:
            return _refuse(request, "no verified customer in this conversation; ask the customer to verify first.")
        if "customer_id" in args and args["customer_id"] != verified:
            return _refuse(request, "you can only look up the verified customer's own account.")
        if "order_id" in args:
            owner = _order_owner(args["order_id"])
            if owner is None:
                return _refuse(request, f"order {args['order_id']} was not found.")
            if owner != verified:
                return _refuse(request, f"order {args['order_id']} does not belong to this customer.")
        return None

    def wrap_tool_call(self, request, handler):
        return self._check(request) or handler(request)

    async def awrap_tool_call(self, request, handler):
        refusal = await asyncio.to_thread(self._check, request)
        return refusal or await handler(request)


verified_customer_prompt = VerifiedCustomerPrompt()
customer_scope_guard = CustomerScopeGuard()
