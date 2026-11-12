"""Deep Agents version of the TechHub customer support agent (Module 4).

The same job as the Module 1 supervisor (route to an order specialist and a
product/policy specialist), rebuilt on the Deep Agents harness. The harness
adds a filesystem, skills, AGENTS.md memory, context management, and subagent
delegation; this factory layers the TechHub-specific harness choices on top:

- AGENTS.md, skills, and an org policy loaded from `agents/deep_support/`
  under `/harness/` (read-only to the agent)
- Per-customer long-term memory under `/memories/` (StoreBackend)
- Customer-scope guard and PII redaction middleware (input, output, and tool results)
- A human-approved `request_refund` tool
- Fault-tolerance middleware (retries, a cross-provider fallback to Claude, call
  limits) on the main agent and each specialist
- A multi-model harness: specialists run on DEEP_AGENT_SMALL_MODEL
- Optional tool narrowing on the order specialist: provider tool search, or
  LLMToolSelectorMiddleware for models without it
- Optional JevToolGate: the Jev decision model screens tool calls for side effects
- Optional RubricMiddleware (verification loop) and CodeInterpreterMiddleware
  (dynamic subagents)
"""

from dataclasses import dataclass
from pathlib import Path

from deepagents import FilesystemPermission, RubricMiddleware, create_deep_agent
from deepagents.backends import CompositeBackend, FilesystemBackend, StateBackend, StoreBackend
from deepagents.middleware.subagents import GENERAL_PURPOSE_SUBAGENT
from langchain.agents.middleware import LLMToolSelectorMiddleware, PIIMiddleware, ProviderToolSearchMiddleware
from langchain.chat_models import init_chat_model
from langchain.tools import tool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

from agents.db_agent import DB_AGENT_BASE_TOOLS
from agents.docs_agent import DOCS_AGENT_BASE_TOOLS
from agents.middleware import JevToolGate, customer_scope_guard, fault_tolerance_middleware, verified_customer_prompt
from config import DEEP_AGENT_FALLBACK_MODELS, DEEP_AGENT_MODEL, DEEP_AGENT_SMALL_MODEL
from tools import get_customer_orders, query_my_orders

HARNESS_DIR = Path(__file__).parent / "deep_support"

# ============================================================================
# AGENT CONFIGURATION
# ============================================================================


@dataclass
class SupportContext:
    """Runtime context set by the application, never by the conversation."""

    customer_id: str | None = None


DEEP_SUPPORT_SYSTEM_PROMPT = """You are TechHub's customer support agent.
Follow the operating guide in your memory (AGENTS.md) and use your skills when a task matches them."""

ORDER_SPECIALIST = {
    "name": "order-specialist",
    "description": "Looks up TechHub orders, order items, prices paid, product availability, and the verified customer's order history.",
    "system_prompt": "You are TechHub's order specialist. Use your tools to answer precisely. "
    "Report exactly what the tools return; if a tool refuses access, say so plainly.",
    "tools": [*DB_AGENT_BASE_TOOLS, get_customer_orders],
    "middleware": [verified_customer_prompt, customer_scope_guard],
}

ORDER_TOOLS = {
    "rigid": ORDER_SPECIALIST["tools"],
    "sql": [query_my_orders],
}

PRODUCT_POLICY_SPECIALIST = {
    "name": "product-policy-specialist",
    "description": "Searches TechHub product specs and store policies (returns, warranty, shipping, compatibility).",
    "system_prompt": "You are TechHub's product and policy specialist. Search the documents and quote the "
    "specific policy terms or specs that answer the question, naming the source document.",
    "tools": DOCS_AGENT_BASE_TOOLS,
}

# Tools that always pause for a person, whatever any classifier says.
INTERRUPT_ON = {"request_refund": True}

# The org-wide harness assets are read-only to the agent.
HARNESS_PERMISSIONS = [
    FilesystemPermission(operations=["write"], paths=["/harness/**"], mode="deny"),
]

DEFAULT_RUBRIC = """A good TechHub support reply:
1. Answers the customer's actual question in the first sentence.
2. Names the policy or document behind any policy claim (e.g. "per our Return Policy").
3. States no order, price, or account detail that the tools did not return.
4. If a tool refused access to account or order data, asks the customer to verify instead of guessing.
5. Gives the customer a concrete next step."""


@tool
def request_refund(order_id: str, reason: str) -> str:
    """Submit a refund request for a delivered order. Requires human approval before it runs.

    Args:
        order_id: The order to refund (e.g. "ORD-2024-0001").
        reason: Short reason given by the customer.
    """
    # Mock action: a real implementation would create a ticket in the refunds system.
    return f"Refund request submitted for {order_id} (reason: {reason}). A support specialist will confirm the amount."


def _pii_middleware() -> list:
    """Redact emails and mask card numbers everywhere text crosses the model boundary.

    - apply_to_input: user messages, before the model sees them
    - apply_to_output: the model's replies, before they reach the customer or a trace
    - apply_to_tool_results: tool output (e.g. order records), before the model sees it
    """
    return [
        PIIMiddleware("email", strategy="redact", apply_to_input=True, apply_to_output=True, apply_to_tool_results=True),
        PIIMiddleware(
            "credit_card", strategy="mask", apply_to_input=True, apply_to_output=True, apply_to_tool_results=True
        ),
    ]


ORDER_TOOL_SELECTION_PROMPT = """Select the tools needed to complete this whole task, not just its first step.
Include tools for the follow-up lookups the answer will need: listing orders returns order IDs only,
so a question about what was ordered also needs the order-items or product tools."""


def order_tool_selector() -> LLMToolSelectorMiddleware:
    """Let an LLM narrow the order specialist's tools before each model call.

    The specialist sees 12 tools: 7 built-in file tools and 5 order tools. The selector
    reads the task it was given and passes on at most 3 tools, plus `read_file`.

    - model unset: selection uses the specialist's own model, so a fallback switches both
    - always_include=["read_file"]: the harness saves large tool results to files and the
      agent reads them back with `read_file`
    - on_parsing_failure="all": selection is an optimization, so a malformed selection
      keeps every tool instead of failing the run
    - system_prompt: selection runs again before every model call, from the task message
      only, so ask for the tools of every step; the default prompt let a small model drop
      `get_order_items` after the first lookup
    It is not an access control: the customer-scope guard still checks every tool call.
    """
    return LLMToolSelectorMiddleware(
        system_prompt=ORDER_TOOL_SELECTION_PROMPT,
        max_tools=3,
        always_include=["read_file"],
        on_parsing_failure="all",
    )


def order_tool_search() -> ProviderToolSearchMiddleware:
    """Defer the order tools behind the model provider's server-side tool search.

    The model starts with the tool names only and loads a schema when it needs one. No
    extra model call, and the tool list stays fixed for the run, so the prompt cache holds.
    Needs a provider with tool search (OpenAI gpt-5.4+, Anthropic Sonnet/Opus 4+ and Haiku 4.5+); the provider
    is read from each request, so a fallback to the other provider switches search with it.
    It pays off with large tool registries. With only 5 deferred tools here, the search turn
    cost more tokens than it saved, and Claude Haiku 4.5 searched the files instead.
    """
    return ProviderToolSearchMiddleware(searchable_tools=[t.name for t in ORDER_SPECIALIST["tools"]])


TOOL_NARROWING = {"search": order_tool_search, "selector": order_tool_selector}


def _with_harness(spec: dict, model, middleware: list) -> dict:
    """Copy a subagent spec with a model and extra middleware (run before the spec's own)."""
    return {**spec, "model": model, "middleware": [*middleware, *spec.get("middleware", [])]}


def _general_purpose(model, middleware: list) -> dict:
    """Replace the auto-added `general-purpose` subagent with a guarded, tool-less one.

    create_deep_agent adds a `general-purpose` subagent unless one is passed. The default
    gets the main agent's tools (here `request_refund`) but none of the main agent's
    middleware, so delegating "refund ORD-X" to it would skip the customer-scope guard.
    Passing our own spec with `tools: []` keeps it to the built-in file tools, under the
    same PII and limit middleware as the specialists.
    """
    return {**GENERAL_PURPOSE_SUBAGENT, "model": model, "tools": [], "middleware": middleware}


def _customer_namespace(runtime) -> tuple[str, ...]:
    """Scope long-term memory to the verified customer.

    With no verified customer, memory is scoped to the conversation (thread). A shared
    "anonymous" bucket would let one unverified user plant notes that the next one loads.
    """
    context = getattr(runtime, "context", None)
    customer_id = (
        context.get("customer_id") if isinstance(context, dict) else getattr(context, "customer_id", None)
    )
    if customer_id:
        return ("techhub", customer_id)
    info = getattr(runtime, "execution_info", None)
    # Callers may pass a UUID as the thread_id (LangGraph accepts it); store namespaces must be strings
    return ("techhub", "anonymous", str(getattr(info, "thread_id", None) or "no-thread"))


# ============================================================================
# FACTORY FUNCTION
# ============================================================================


def create_deep_support_agent(
    model=None,
    use_checkpointer: bool = True,
    store=None,
    redact_pii: bool = True,
    with_verifier: bool = False,
    verifier_model=None,
    on_evaluation=None,
    with_interpreter: bool = False,
    extra_middleware: list | None = None,
    subagent_model=None,
    guardrails: bool = True,
    fallback_models: list | None = None,
    narrow_tools: str | None = None,
    jev_tool_gate: bool = False,
    order_tools: str = "rigid",
):
    """Create the TechHub support agent on the Deep Agents harness.

    Args:
        model: Model to use (defaults to DEEP_AGENT_MODEL, openai:gpt-5.4).
        use_checkpointer: True for notebooks (MemorySaver); False for deployment.
        store: Store for `/memories/`. Defaults to an InMemoryStore in dev and to the
            platform store in deployment (`use_checkpointer=False`).
        redact_pii: Redact emails and mask credit card numbers in user input, model
            output, and tool results.
        with_verifier: Add RubricMiddleware. It only activates when a `rubric` is
            passed in the invocation state (see DEFAULT_RUBRIC).
        verifier_model: Grader model for the rubric (defaults to the main model).
        on_evaluation: Optional callback receiving each RubricEvaluation (iteration,
            result, explanation, per-criterion verdicts).
        with_interpreter: Add CodeInterpreterMiddleware, enabling dynamic subagents.
        extra_middleware: Additional middleware appended to the main agent.
        subagent_model: Model for the specialists (defaults to DEEP_AGENT_SMALL_MODEL, a
            multi-model harness). Pass the same value as `model` for a single-model harness.
        guardrails: Add fault-tolerance middleware (retries, fallback, call limits).
        fallback_models: Models to fall back to, in order (defaults to
            DEEP_AGENT_FALLBACK_MODELS: Claude Sonnet 5.5, then the small model).
        narrow_tools: Show the order specialist fewer tool schemas per call. "selector": an
            LLM picks the tools before each call (order_tool_selector); one extra model call
            per specialist turn. "search": provider tool search (order_tool_search). On this
            specialist (5 order tools) the selector roughly halved input tokens, while search
            raised them on gpt-5.4-mini and missed the order tools on Claude Haiku 4.5.
        jev_tool_gate: Add JevToolGate to the main agent: Jev scores each tool call for side
            effects and pauses likely ones for approval. Tools in `interrupt_on` and `task`
            are skipped. Needs Jev through the LLM Gateway; synthetic data only.
        order_tools: The order specialist's tools. "rigid" (default): the four lookup tools
            plus get_customer_orders. "sql": one `query_my_orders` tool that runs read-only
            SQL over the verified customer's own rows (Module 5's improvement).

    Returns:
        Compiled deep agent graph. Invoke with `context=SupportContext(customer_id=...)`.

    Examples:
        >>> agent = create_deep_support_agent()
        >>> agent.invoke(
        ...     {"messages": [{"role": "user", "content": "Where is my order ORD-2025-0050?"}]},
        ...     config={"configurable": {"thread_id": "1"}},
        ...     context=SupportContext(customer_id="CUST-003"),
        ... )
    """
    llm = init_chat_model(model or DEEP_AGENT_MODEL)
    small_llm = init_chat_model(subagent_model or DEEP_AGENT_SMALL_MODEL)
    fallbacks = DEEP_AGENT_FALLBACK_MODELS if fallback_models is None else fallback_models

    middleware = []
    if guardrails:
        middleware += fault_tolerance_middleware(
            fallback_models=fallbacks,
            model_call_limit=40,
            tool_call_limit=80,
            # Caps `task` calls the model makes. task() calls inside interpreter code (dynamic
            # subagents) aren't counted; CodeInterpreterMiddleware bounds those instead.
            tool_limits={"task": 20},
        )
    if redact_pii:
        middleware += _pii_middleware()
    if with_verifier:
        middleware.append(
            RubricMiddleware(model=verifier_model or llm, max_iterations=3, on_evaluation=on_evaluation)
        )
    if with_interpreter:
        from langchain_quickjs import CodeInterpreterMiddleware

        # At most 4 subagents at once from interpreter code. There is no total dispatch cap,
        # so each subagent's own call limits bound the work.
        middleware.append(CodeInterpreterMiddleware(max_subagent_concurrency=4))
    middleware += [verified_customer_prompt, customer_scope_guard]
    if jev_tool_gate:
        # After the guard, so refused calls never reach a reviewer
        middleware.append(JevToolGate(skip=[*INTERRUPT_ON, "task"]))
    middleware += extra_middleware or []

    def specialist_middleware(spec: dict) -> list:
        # Specialists are separate agents: they don't inherit the main agent's middleware.
        stack = []
        if guardrails:
            stack += fault_tolerance_middleware(
                # The specialist already runs on the small model; only the other provider is a fallback.
                fallback_models=[m for m in fallbacks if m != (subagent_model or DEEP_AGENT_SMALL_MODEL)],
                retry_tools=spec["tools"],
                model_call_limit=10,
                tool_call_limit=15,
            )
        if redact_pii:
            stack += _pii_middleware()
        return stack

    backend = CompositeBackend(
        default=StateBackend(),
        routes={
            "/harness/": FilesystemBackend(root_dir=HARNESS_DIR, virtual_mode=True),
            "/memories/": StoreBackend(namespace=_customer_namespace),
        },
    )

    if order_tools not in ORDER_TOOLS:
        raise ValueError(f"order_tools must be one of {list(ORDER_TOOLS)}")
    if order_tools != "rigid" and narrow_tools:
        raise ValueError("narrow_tools only applies to the rigid order tools")
    order_spec = {**ORDER_SPECIALIST, "tools": ORDER_TOOLS[order_tools]}
    order_middleware = specialist_middleware(order_spec)
    if narrow_tools:
        # Inside fault tolerance, so retries and the fallback also see the narrowed request
        order_middleware.append(TOOL_NARROWING[narrow_tools]())

    agent_kwargs = {
        "model": llm,
        "tools": [request_refund],
        "system_prompt": DEEP_SUPPORT_SYSTEM_PROMPT,
        "subagents": [
            _with_harness(order_spec, small_llm, order_middleware),
            _with_harness(PRODUCT_POLICY_SPECIALIST, small_llm, specialist_middleware(PRODUCT_POLICY_SPECIALIST)),
            _general_purpose(small_llm, specialist_middleware({"tools": []})),
        ],
        "memory": ["/harness/AGENTS.md"],
        "skills": ["/harness/skills/"],
        "backend": backend,
        "permissions": HARNESS_PERMISSIONS,
        "middleware": middleware,
        "interrupt_on": INTERRUPT_ON,
        "context_schema": SupportContext,
        "name": "deep_support_agent",
    }

    # Development: local checkpointer + store. Deployment: the platform provides both.
    if use_checkpointer:
        agent_kwargs["checkpointer"] = MemorySaver()
        agent_kwargs["store"] = store or InMemoryStore()
    elif store is not None:
        agent_kwargs["store"] = store

    return create_deep_agent(**agent_kwargs)
