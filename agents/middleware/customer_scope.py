"""Customer-scope guard middleware for TechHub support agents.

Deep Agents filesystem permissions only govern the built-in file tools. Custom
tools (like the TechHub database tools) run with whatever access the process
has, so authorization has to be enforced around the tool call itself.

This middleware wraps every tool call and checks it against the *verified*
customer identity passed in runtime context (never against anything the model
or the user typed):

- Tools that take a `customer_id` may only be called with the verified ID.
- Tools that take an `order_id` may only touch orders owned by that customer.
- With no verified customer, customer-specific tools are refused outright.

Product and policy tools carry neither argument, so they pass straight through.

Both middlewares implement sync and async hooks: notebooks call `invoke()`,
while Agent Server (`langgraph dev`, Studio, deployments) runs agents async.
"""

import asyncio
import re
import sqlite3
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import SystemMessage, ToolMessage

from config import DEFAULT_DB_PATH


def _verified_customer_id(runtime: Any) -> str | None:
    """Read the verified customer ID from runtime context (dataclass or dict)."""
    context = getattr(runtime, "context", None)
    if context is None:
        return None
    if isinstance(context, dict):
        return context.get("customer_id")
    return getattr(context, "customer_id", None)


def _order_owner(order_id: str) -> str | None:
    """Return the customer_id that owns an order, or None if it doesn't exist."""
    with sqlite3.connect(DEFAULT_DB_PATH) as conn:
        row = conn.execute(
            "SELECT customer_id FROM orders WHERE order_id = ?", (order_id,)
        ).fetchone()
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
    """Tell the model who is verified. The guard below still enforces it on every tool call."""

    def _with_note(self, request):
        verified = _verified_customer_id(request.runtime)
        note = (
            f"\n\nVerified customer for this conversation: {verified}. "
            "When delegating account or order lookups, pass this customer ID to the specialist."
            if verified
            else "\n\nNo customer is verified in this conversation."
        )
        return _append_to_system(request, note)

    def wrap_model_call(self, request, handler):
        return handler(self._with_note(request))

    async def awrap_model_call(self, request, handler):
        return await handler(self._with_note(request))


class CustomerScopeGuard(AgentMiddleware):
    """Block tool calls that reach outside the verified customer's own data."""

    def _check(self, request) -> ToolMessage | None:
        args = request.tool_call.get("args", {}) or {}
        unknown = [k for k in args if _SCOPED_ARG.search(k) and k not in ("customer_id", "order_id")]
        if unknown:  # fail closed: a new tool must be taught to the guard before it can run
            return _refuse(request, f"the argument {unknown[0]!r} looks customer-scoped but this guard can't check it.")
        if "customer_id" not in args and "order_id" not in args:
            return None

        verified = _verified_customer_id(request.runtime)
        if not verified:
            return _refuse(
                request,
                "no verified customer in this conversation. Ask the customer to verify "
                "their identity before looking up account or order details.",
            )

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
