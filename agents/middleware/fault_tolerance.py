"""Fault-tolerance middleware for the TechHub deep agents.

Production agents run unattended, so they need limits as well as instructions
(see https://docs.langchain.com/oss/python/deepagents/fault-tolerance):

- `ModelFallbackMiddleware`: switch to backup models, in order, when the main one keeps
  failing. Put a model from another provider first so a provider outage is covered too.
- `ModelRetryMiddleware`: retry transient model errors (rate limits, 5xx, timeouts) with
  backoff. `on_failure="error"` re-raises after the last retry so the fallback can take
  over. `retry_on=is_transient` retries only rate limits, timeouts,
  conflicts, 5xx, and network errors; everything else goes straight to the fallback. The default retries every error a provider SDK doesn't
  classify, and langchain-openai classifies none.
- `ToolRetryMiddleware`: retry read-only tools only. Never retry tools with side
  effects (refunds, price changes): a retry could submit the action twice.
- `ModelCallLimitMiddleware` / `ToolCallLimitMiddleware`: stop runaway loops.

Order matters: middleware listed first wraps the ones after it, so fallback sits
outside retry (retry the main model first, then fall back).
"""

from langchain.agents.middleware import (
    ModelCallLimitMiddleware,
    ModelFallbackMiddleware,
    ModelRetryMiddleware,
    ToolCallLimitMiddleware,
    ToolRetryMiddleware,
)
from langchain_core.exceptions import ModelError

# Retry only what a retry can fix: rate limits, timeouts, conflicts, server errors, and
# network failures. Anything else (bad request, auth, unknown model, or a bug in our own
# code such as a ValueError) goes straight to the fallback instead of ~7s of retries.
_TRANSIENT_STATUSES = {408, 409, 429}
_TRANSIENT_ERRORS = {  # matched by class name, so no provider SDK import is needed
    "APIConnectionError", "APITimeoutError",  # openai, anthropic
    "TimeoutException", "ConnectError", "ReadError", "RemoteProtocolError",  # httpx
    "TimeoutError", "ConnectionError",  # builtins
}


def is_transient(exc: BaseException) -> bool:
    """Retry rate limits, 5xx errors, timeouts, and connection errors; nothing else."""
    if not isinstance(exc, Exception):
        return False
    if isinstance(exc, ModelError):
        return exc.is_retryable
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status in _TRANSIENT_STATUSES or status >= 500
    return any(cls.__name__ in _TRANSIENT_ERRORS for cls in type(exc).__mro__)


def fault_tolerance_middleware(
    fallback_models: list | None = None,
    retry_tools: list | None = None,
    model_call_limit: int = 40,
    tool_call_limit: int = 80,
    tool_limits: dict[str, int] | None = None,
) -> list:
    """Build the fault-tolerance middleware stack.

    Args:
        fallback_models: Model strings or chat models to try in order after the main model
            fails. None or [] skips the fallback.
        retry_tools: Read-only tools (or tool names) safe to retry. None or [] skips tool retries.
        model_call_limit: Max model calls per run; the run ends gracefully when reached.
        tool_call_limit: Max tool calls per run across all tools.
        tool_limits: Per-tool run limits, e.g. {"task": 10} to cap subagent delegations.

    Returns:
        A list of middleware to pass to `create_deep_agent(middleware=...)` or a subagent spec.
    """
    middleware = []
    if fallback_models:
        middleware.append(ModelFallbackMiddleware(*fallback_models))
    middleware.append(
        ModelRetryMiddleware(
            max_retries=3, backoff_factor=2.0, initial_delay=1.0, retry_on=is_transient, on_failure="error"
        )
    )
    if retry_tools:
        middleware.append(ToolRetryMiddleware(max_retries=2, tools=retry_tools))
    middleware.append(ModelCallLimitMiddleware(run_limit=model_call_limit, exit_behavior="end"))
    middleware.append(ToolCallLimitMiddleware(run_limit=tool_call_limit))
    for tool_name, limit in (tool_limits or {}).items():
        middleware.append(ToolCallLimitMiddleware(tool_name=tool_name, run_limit=limit))
    return middleware
