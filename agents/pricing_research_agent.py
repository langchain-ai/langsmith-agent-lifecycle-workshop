"""TechHub pricing research agent (Module 4, Section 1: Deep Agents 101).

A deep agent that compares TechHub's catalog prices with current market prices,
researches follow-up questions, and proposes price changes for human approval.
It shows the core Deep Agents building blocks on the TechHub data:

- Planning (`TodoListMiddleware`, opt-in since deepagents 0.7)
- A virtual filesystem for reports (`/reports/`, thread-scoped)
- Subagents: `market-researcher` (web search) and `catalog-analyst` (TechHub DB)
- Long-term memory for analyst preferences (`/memories/`, StoreBackend)
- `AGENTS.md` + a skill, loaded from `agents/pricing_research/` at `/harness/`
- Human-in-the-loop on `propose_price_change`
- A multi-model harness: subagents run on a smaller model (DEEP_AGENT_SMALL_MODEL)
- A research budget (AGENTS.md caps + a `think_tool` reflection step) and
  fault-tolerance middleware (retries, fallback, call limits)

Web search uses the model provider's built-in search tool (no Tavily key needed).
The research budget, reflection step, and numbered citations follow the
deepagents `examples/deep_research` reference agent.
"""

import sqlite3
from pathlib import Path

from deepagents import FilesystemPermission, create_deep_agent
from deepagents.backends import CompositeBackend, FilesystemBackend, StateBackend, StoreBackend
from deepagents.middleware.subagents import GENERAL_PURPOSE_SUBAGENT
from langchain.agents.middleware import TodoListMiddleware
from langchain.chat_models import init_chat_model
from langchain.tools import tool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

from agents.middleware import fault_tolerance_middleware
from config import DEEP_AGENT_MODEL, DEEP_AGENT_SMALL_MODEL, DEFAULT_DB_PATH

HARNESS_DIR = Path(__file__).parent / "pricing_research"

# ============================================================================
# TOOLS
# ============================================================================


def web_search_tool(model: str) -> dict:
    """The provider's built-in (server-side) web search tool for a model string."""
    provider = model.split(":", 1)[0]
    if provider == "anthropic":
        # The 20260209 version (dynamic filtering) needs Sonnet/Opus 4.6+ or a 5.x model;
        # Haiku 4.5 rejects it with a 400 (tested 2026-10-29). Older models use 20250305.
        newer = any(tag in model for tag in ("sonnet-4-6", "opus-4-6", "sonnet-5", "opus-5"))
        return {"type": "web_search_20260209" if newer else "web_search_20250305", "name": "web_search"}
    if provider in ("google_genai", "google"):
        return {"google_search": {}}
    return {"type": "web_search"}  # OpenAI (Responses API)


@tool
def think_tool(reflection: str) -> str:
    """Record a short reflection after a search: what you found, what's missing, and whether to stop.

    Args:
        reflection: Findings so far, remaining gaps, and the decision (search again or stop).
    """
    return f"Reflection recorded: {reflection}"


@tool
def get_catalog_prices(category: str = "") -> str:
    """Get TechHub's current catalog prices and stock, optionally for one category.

    Args:
        category: One of Laptops, Monitors, Keyboards, Audio, Accessories. Empty for all.
    """
    sql = "SELECT product_id, name, category, price, in_stock FROM products"
    params: tuple = ()
    if category:
        sql += " WHERE lower(category) = lower(?)"
        params = (category,)
    with sqlite3.connect(DEFAULT_DB_PATH) as conn:
        rows = conn.execute(sql + " ORDER BY category, price DESC", params).fetchall()
    if not rows:
        return f"No products found for category '{category}'."
    return "\n".join(
        f"{pid} | {name} | {cat} | ${price:,.2f} | {'in stock' if stock else 'out of stock'}"
        for pid, name, cat, price, stock in rows
    )


@tool
def propose_price_change(product_id: str, new_price: float, rationale: str) -> str:
    """Propose a price change for a TechHub product. A pricing manager must approve it.

    Args:
        product_id: TechHub product ID (e.g. "TECH-LAP-001").
        new_price: Proposed new price in USD.
        rationale: Evidence-based reason, citing market prices.
    """
    # Mock action: a real implementation would open a change request in the pricing system.
    return f"Price change proposal recorded: {product_id} -> ${new_price:,.2f}. Rationale: {rationale}"


# ============================================================================
# AGENT CONFIGURATION
# ============================================================================

PRICING_SYSTEM_PROMPT = """You are TechHub's pricing research agent.
Follow the operating guide in your memory (AGENTS.md) and use your skills when a task matches them."""


MARKET_RESEARCHER_PROMPT = """You research current US market prices for one consumer electronics product at a time.

- Use web search. Aim for 3+ major US retailers (for example Amazon, Best Buy, the manufacturer's store).
- After each search, call think_tool: what you found, what's missing, and whether to stop.
- Budget: at most 3 search rounds. Stop early once you have 3 prices with URLs.
- Return a short list: retailer, price, sale or regular, URL. Never invent prices; say "no reliable price found"."""


def _chat_model(model_name: str):
    """Chat model for a model string. OpenAI's built-in web search needs the Responses API."""
    kwargs = {"use_responses_api": True} if model_name.startswith("openai:") else {}
    return init_chat_model(model_name, **kwargs)


def pricing_subagents(model: str, guardrails: bool = True) -> list[dict]:
    """The two specialists. They run on `model` (the small model in a multi-model harness)."""
    llm = _chat_model(model)
    researcher_limits = fault_tolerance_middleware(model_call_limit=8, tool_call_limit=10) if guardrails else []
    analyst_limits = (
        fault_tolerance_middleware(retry_tools=[get_catalog_prices], model_call_limit=5, tool_call_limit=5)
        if guardrails
        else []
    )
    return [
        {
            "name": "market-researcher",
            "description": "Searches the web for current retailer prices, promotions, and model refreshes for a "
            "specific product. Returns prices with retailer names and source URLs.",
            "system_prompt": MARKET_RESEARCHER_PROMPT,
            "model": llm,
            "tools": [web_search_tool(model), think_tool],
            "middleware": researcher_limits,
        },
        {
            "name": "catalog-analyst",
            "description": "Looks up TechHub's own catalog prices, categories, and stock.",
            "system_prompt": "You report TechHub's catalog data exactly as the tool returns it.",
            "model": llm,
            "tools": [get_catalog_prices],
            "middleware": analyst_limits,
        },
        # Replaces the auto-added `general-purpose` subagent, which would get the main agent's
        # tools (web search, propose_price_change) without the research budget's limits.
        {
            **GENERAL_PURPOSE_SUBAGENT,
            "model": llm,
            "tools": [],
            "middleware": fault_tolerance_middleware(model_call_limit=5, tool_call_limit=5) if guardrails else [],
        },
    ]


# ============================================================================
# FACTORY FUNCTION
# ============================================================================


def create_pricing_research_agent(
    model: str | None = None,
    subagent_model: str | None = None,
    use_checkpointer: bool = True,
    store=None,
    guardrails: bool = True,
):
    """Create the TechHub pricing research deep agent.

    Args:
        model: Model string for the main (planning) agent. Defaults to DEEP_AGENT_MODEL.
        subagent_model: Model string for the subagents. Defaults to DEEP_AGENT_SMALL_MODEL
            (multi-model harness). Pass the same value as `model` for a single-model harness.
        use_checkpointer: True for notebooks (MemorySaver); False for deployment.
        store: Store for `/memories/` (InMemoryStore in dev; the platform store when deployed).
        guardrails: Add fault-tolerance middleware (retries, fallback, call limits). Keep it on;
            the flag exists so the notebook can show the agent with and without it.

    Returns:
        Compiled deep agent graph.

    Example:
        >>> agent = create_pricing_research_agent()
        >>> agent.invoke(
        ...     {"messages": [{"role": "user", "content": "Benchmark our laptop prices against the market."}]},
        ...     config={"configurable": {"thread_id": "1"}},
        ... )
    """
    model_name = model or DEEP_AGENT_MODEL
    small_model_name = subagent_model or DEEP_AGENT_SMALL_MODEL
    llm = _chat_model(model_name)
    # The fallback model gets the main agent's tools, so pick a search tool version both can
    # call: Claude Sonnet 5.5 supports web_search_20260209, its Haiku 4.5 fallback doesn't.
    search_tool = web_search_tool(model_name)
    if guardrails and small_model_name != model_name and web_search_tool(small_model_name) != search_tool:
        search_tool = web_search_tool(small_model_name)

    middleware = [TodoListMiddleware()]
    if guardrails:
        middleware += fault_tolerance_middleware(
            # Same-provider fallback only: web_search_tool() is the provider's built-in
            # tool, so a Claude fallback can't call OpenAI's web search (or vice versa).
            fallback_models=[_chat_model(small_model_name)] if small_model_name != model_name else None,
            retry_tools=[get_catalog_prices],
            model_call_limit=40,
            tool_call_limit=60,
            tool_limits={"task": 10},  # research budget: subagent delegations per request
        )

    backend = CompositeBackend(
        default=StateBackend(),  # /reports/ and scratch files live with the thread
        routes={
            "/harness/": FilesystemBackend(root_dir=HARNESS_DIR, virtual_mode=True),
            "/memories/": StoreBackend(namespace=lambda rt: ("techhub-pricing",)),
        },
    )

    agent_kwargs = {
        "model": llm,
        "tools": [search_tool, get_catalog_prices, propose_price_change],
        "system_prompt": PRICING_SYSTEM_PROMPT,
        "subagents": pricing_subagents(small_model_name, guardrails=guardrails),
        "middleware": middleware,
        "memory": ["/harness/AGENTS.md"],
        "skills": ["/harness/skills/"],
        "backend": backend,
        "permissions": [FilesystemPermission(operations=["write"], paths=["/harness/**"], mode="deny")],
        "interrupt_on": {"propose_price_change": True},
        "name": "pricing_research_agent",
    }

    if use_checkpointer:
        agent_kwargs["checkpointer"] = MemorySaver()
        agent_kwargs["store"] = store or InMemoryStore()
    elif store is not None:
        agent_kwargs["store"] = store

    return create_deep_agent(**agent_kwargs)
