"""Build Module 4 notebooks (Deep Agents 201) for the TechHub workshop.

Usage (from the repo root):
    uv run python scripts/notebook_builders/build_module4.py workshop_modules/module_4
"""

import sys
from pathlib import Path

import nbformat as nbf

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
KERNEL = {"display_name": "Python 3 (ipykernel)", "language": "python", "name": "python3"}


def md(s):
    return nbf.v4.new_markdown_cell(s.strip("\n"))


def code(s):
    return nbf.v4.new_code_cell(s.strip("\n"))


def save(name, cells):
    nb = nbf.v4.new_notebook()
    nb.cells = cells
    for i, cell in enumerate(cells):  # stable ids, so regenerating gives a clean diff
        cell["id"] = f"cell-{i:03d}"
    nb.metadata["kernelspec"] = KERNEL
    nbf.write(nb, OUT / name)
    print("wrote", OUT / name, len(cells), "cells")


SETUP = code('''
import uuid
import warnings

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
warnings.filterwarnings("ignore", category=UserWarning)

from utils.langsmith_links import project_url, trace_link

print(f"📊 All traces from this workshop: {project_url()}")
''')

HELPERS = code('''
def new_thread():
    """A fresh conversation (thread) for each example."""
    return {"configurable": {"thread_id": str(uuid.uuid4())}}


def tool_calls(result):
    """Names of the tools the main agent called (subagent name in brackets for `task`)."""
    names = []
    for m in result["messages"]:
        for tc in getattr(m, "tool_calls", None) or []:
            extra = f"[{tc['args'].get('subagent_type')}]" if tc["name"] == "task" else ""
            names.append(tc["name"] + extra)
    return names


def truncate(text, limit=600):
    return text if len(text) <= limit else text[:limit] + "…"


def show(result, limit=600):
    """Print this turn's messages: human / ai / tool, as in a LangGraph trace."""
    messages = result["messages"]
    last_human = max((i for i, m in enumerate(messages) if m.type == "human"), default=0)
    for m in messages[last_human:]:
        m.model_copy(update={"content": truncate(m.text, limit)}).pretty_print()
''')

# ============================================================================
# SECTION 1
# ============================================================================
s1 = [
    md('''
# Module 4, Section 2: Deep Agents 201: Harness Engineering

Section 1 introduced the Deep Agents building blocks with a pricing research agent. In Module 1 we hand-built a supervisor that routed customer questions to a database agent and a documents agent. Now we rebuild **the same TechHub support agent on the Deep Agents harness**, then improve it by tuning the harness while the model stays fixed.

> **Harness engineering**: the harness is everything around the model: the system prompt, tools, context, middleware, execution environment, and verification. You find a failure mode in a trace, change the harness, and re-verify. Done this way, LangChain's coding agent went from 52.8% to 66.5% on Terminal Bench 2.0 (from outside the Top 30 to the Top 5) with the model held fixed ([Improving Deep Agents with harness engineering](https://www.langchain.com/blog/improving-deep-agents-with-harness-engineering)).

In this section:
1. **Same job, new harness**: the Module 1 supervisor as a deep agent
2. **Context engineering**: `AGENTS.md` vs skills vs memory
3. **Routing memory** with `CompositeBackend` (per-customer memory, read-only org policy)
4. **Context quarantine**: why subagents keep the main context small
5. **Custom middleware**: verified identity, PII redaction, and a customer-scope guard
6. **Human-in-the-loop** on a sensitive tool (refunds)
7. **Read-only org assets** with filesystem permissions

Section 3 covers dynamic subagents and verification loops.
'''),
    md("""## Setup

**Prerequisites:** `uv sync`, a `.env` with model access (direct provider keys or the LLM Gateway, see [Model access](../../README.md#model-access-direct-keys-or-the-llm-gateway) in the README; `uv run python verify_setup.py` checks it), and the document vectorstore, which the product-policy specialist searches: `uv run python data/data_generation/build_vectorstore.py` (one-time, about 60 seconds)."""),
    SETUP,
    HELPERS,
    md('''
## 1. Same job, new harness

A deep agent is `create_agent()` plus a pre-built middleware stack: a virtual **filesystem**, **subagents** through a `task` tool, **context management** (offloading large tool results and summarizing long conversations), and optional planning.

Below is the Module 1 supervisor rebuilt as a deep agent. The specialists become **subagent specs** (name, description, prompt, tools) instead of hand-wrapped tool functions.
'''),
    code('''
from deepagents import create_deep_agent
from langchain.chat_models import init_chat_model

from agents.db_agent import DB_AGENT_BASE_TOOLS
from agents.docs_agent import DOCS_AGENT_BASE_TOOLS
from config import DEEP_AGENT_MODEL

llm = init_chat_model(DEEP_AGENT_MODEL)  # openai:gpt-5.4 by default (config.py)

simple_agent = create_deep_agent(
    model=llm,
    system_prompt="You are TechHub's customer support agent. Delegate to your specialists and answer concisely.",
    subagents=[
        {
            "name": "order-specialist",
            "description": "Looks up TechHub orders, order items, prices, and product availability.",
            "system_prompt": "You are TechHub's order specialist. Report exactly what the tools return.",
            "tools": DB_AGENT_BASE_TOOLS,
        },
        {
            "name": "product-policy-specialist",
            "description": "Searches TechHub product specs and store policies (returns, warranty, shipping).",
            "system_prompt": "You are TechHub's product and policy specialist. Quote the terms that answer the question.",
            "tools": DOCS_AGENT_BASE_TOOLS,
        },
    ],
)

# The harness gives the agent these tools before we add any of our own
print("Built-in tools:", sorted(simple_agent.nodes["tools"].bound.tools_by_name))
'''),
    code('''
with trace_link("Deep agent: same question as Module 1"):
    result = simple_agent.invoke(
        {"messages": [{"role": "user", "content": "How much is TECH-LAP-001 and does it have a warranty?"}]}
    )
show(result)
'''),
    md('''
**What changed versus Module 1:** we didn't write any tool-wrapping code. The `task` tool delegates to a subagent, which runs in its own context window and returns only its final answer.

`ls`, `read_file`, `write_file`, `edit_file`, `glob`, `grep`, and `delete` work on the agent's filesystem. `execute` only runs commands when the backend is a sandbox, which we add in Module 6.

From here on we use the full TechHub harness from `agents/deep_support_agent.py`, built step by step below.
'''),
    md('''
## 2. Context engineering: AGENTS.md vs skills vs memory

A deep agent has three ways to give the model knowledge, each loaded differently:

| Surface | Loaded | Use for | TechHub file |
|---|---|---|---|
| **`AGENTS.md` (memory)** | Always, injected into the system prompt | Operating rules every turn needs | `agents/deep_support/AGENTS.md` |
| **Skills** | On demand: name and description at startup, the body only when a task matches | Procedures for specific tasks | `agents/deep_support/skills/*/SKILL.md` |
| **Long-term memory files** | When the agent reads them | Things learned about a customer over time | `/memories/preferences.md` (per customer) |

Skills use **progressive disclosure**: only the frontmatter costs context until the skill is actually needed.
'''),
    code('''
from pathlib import Path

harness_dir = Path("../../agents/deep_support")
for path in sorted(harness_dir.rglob("*.md")):
    print(path.relative_to(harness_dir))

print("\\n--- skills/returns-and-warranty/SKILL.md (frontmatter) ---")
print("\\n".join((harness_dir / "skills/returns-and-warranty/SKILL.md").read_text().splitlines()[:4]))
'''),
    code('''
from langgraph.store.memory import InMemoryStore

from agents import SupportContext, create_deep_support_agent

store = InMemoryStore()  # holds /memories/ so we can inspect it below
agent = create_deep_support_agent(store=store)

with trace_link("Skill loaded on demand"):
    result = agent.invoke(
        {"messages": [{"role": "user", "content": "I opened my new laptop 10 days ago and don't like it. Can I return it?"}]},
        config=new_thread(),
        context=SupportContext(customer_id="CUST-003"),
    )
show(result)
'''),
    md('''
Look at the tool calls: the agent used `read_file` to open the matching `SKILL.md` and then followed its steps. Open the trace to see which files it read.

**Context management is on by default.** Large tool results are offloaded to the filesystem and replaced with a file path and a short preview. When the conversation gets close to the model's context limit, older turns are summarized. See [Deep Agents context engineering](https://docs.langchain.com/oss/python/deepagents/overview) for the current thresholds.
'''),
    md('''
## 3. Routing memory with `CompositeBackend`

A `CompositeBackend` routes filesystem paths to different storage backends. The TechHub agent uses three routes:

| Path | Backend | Scope |
|---|---|---|
| `/harness/` | `FilesystemBackend` on `agents/deep_support/` | Org-owned `AGENTS.md`, skills, and policies (read-only, see §7) |
| `/memories/` | `StoreBackend`, namespaced by the **verified** customer ID | Long-term memory per customer |
| everything else | `StateBackend` | Scratch files for this thread only |

The namespace comes from the runtime context the *application* sets, never from what the user types. So one customer's memory can never reach another customer's conversation. With no verified customer, memory is scoped to the conversation itself: a shared "anonymous" bucket would let one unverified user plant notes that the next one loads.
'''),
    code('''
# Thread 1: CUST-003 states a lasting preference
with trace_link("Memory: CUST-003 states a preference"):
    r1 = agent.invoke(
        {"messages": [{"role": "user", "content": "Please remember: I prefer email updates and I only buy Logitech peripherals."}]},
        config=new_thread(),
        context=SupportContext(customer_id="CUST-003"),
    )
show(r1, 200)

# Thread 2: a brand-new conversation, same customer
with trace_link("Memory: new thread, same customer"):
    r2 = agent.invoke(
        {"messages": [{"role": "user", "content": "Which mouse would you recommend for me?"}]},
        config=new_thread(),
        context=SupportContext(customer_id="CUST-003"),
    )
show(r2, 300)
'''),
    code('''
# Thread 3: a different customer asks the same question
with trace_link("Memory: a different customer, no history"):
    r3 = agent.invoke(
        {"messages": [{"role": "user", "content": "Which mouse would you recommend for me?"}]},
        config=new_thread(),
        context=SupportContext(customer_id="CUST-019"),
    )
show(r3, 300)

print("\\n🗂️ Memory namespaces in the store:", list(store.list_namespaces()))
for item in store.search(("techhub", "CUST-003")):
    print(f"\\n{item.key}:")
    print(item.value.get("content") if isinstance(item.value, dict) else item.value)
'''),
    md('''
CUST-003's second thread used the stored preference. CUST-019 has no memory, so the agent asked or answered generically.

> ⚠️ `CompositeBackend` strips the route prefix before handing the path to the backend, so `/memories/preferences.md` is stored under the key `/preferences.md`. Keep this in mind if you seed memory from application code.
'''),
    md('''
## 4. Context quarantine with subagents

Each subagent runs in its own context window. The main agent sees only the subagent's final answer, not the dozens of tool calls behind it. That keeps the main context small, which means lower cost and latency, and fewer chances for the model to lose track.

We stream with `subgraphs=True` to count tool calls inside and outside the subagents.
'''),
    code('''
main_calls, subagent_calls = [], []
for namespace, chunk in agent.stream(
    {"messages": [{"role": "user", "content": "What are my 5 most recent orders, with product names?"}]},
    config=new_thread(),
    context=SupportContext(customer_id="CUST-003"),
    stream_mode="updates",
    subgraphs=True,
):
    for update in chunk.values():
        for m in (update or {}).get("messages", []) if isinstance(update, dict) else []:
            for tc in getattr(m, "tool_calls", None) or []:
                (subagent_calls if namespace else main_calls).append(tc["name"])

print(f"Main agent tool calls ({len(main_calls)}): {main_calls}")
print(f"Subagent tool calls   ({len(subagent_calls)}): {sorted(set(subagent_calls))}")
'''),
    md('''
### Fewer tools per model call

Quarantine keeps the specialist's work out of the main context, but the specialist's own context still carries every tool schema on every call. The order specialist sees 12 tools: 7 built-in file tools from the harness and 5 order tools. Most questions need 2 or 3 of them.

LangChain has three levers for this ([built-in middleware](https://docs.langchain.com/oss/python/langchain/middleware/built-in), [skills](https://docs.langchain.com/oss/python/deepagents/skills)):

| Lever | How it works | Cost |
|---|---|---|
| Provider tool search (`ProviderToolSearchMiddleware`) | Tools are deferred; the model searches the provider's index and loads a schema when it needs one | A search turn; needs OpenAI gpt-5.4+ or a recent Claude model |
| Skill tools (`include_tools` in `SKILL.md`) | A tool becomes callable only after the agent reads the skill that lists it | Fits when tools group by procedure |
| `LLMToolSelectorMiddleware` | A model picks the relevant tools before each model call | One extra model call per turn |

The general guidance is to start with provider tool search for large tool registries, and to use the LLM selector for models without it. But measure on your own agent. `create_deep_support_agent(narrow_tools=...)` adds either one to the order specialist, so we can compare them on the same question.

The selector's settings:

| Setting | Value | Why |
|---|---|---|
| `model` | unset | Selection uses the specialist's own (small) model, and switches with it on a fallback |
| `max_tools` | 3 | Extra selections beyond 3 are dropped |
| `always_include` | `["read_file"]` | The harness saves large tool results to files and reads them back with `read_file` |
| `system_prompt` | Select tools for **every step** of the task | Selection reruns before each model call, from the task message only |
| `on_parsing_failure` | `"all"` | Selection is an optimization; a malformed answer keeps every tool instead of failing the run |

The main agent gets neither: its 9 tools are mostly the harness's own (`task`, the file tools), and losing `task` would stop delegation.
'''),
    code('''
def specialist_usage(agent, question):
    """Input tokens across the specialists' model calls, and the tools they called."""
    tokens, calls = 0, []
    for namespace, chunk in agent.stream(
        {"messages": [{"role": "user", "content": question}]},
        config=new_thread(),
        context=SupportContext(customer_id="CUST-003"),
        stream_mode="updates",
        subgraphs=True,
    ):
        for update in chunk.values():
            for m in (update or {}).get("messages", []) if isinstance(update, dict) else []:
                if namespace and m.type == "ai":
                    tokens += (m.usage_metadata or {}).get("input_tokens", 0)
                    calls += [tc["name"] for tc in m.tool_calls]
    return tokens, sorted(set(calls))

question = "What are my 5 most recent orders, with product names?"
variants = [
    ("All 12 tools", agent),
    ("Tool search", create_deep_support_agent(narrow_tools="search")),
    ("LLM selector", create_deep_support_agent(narrow_tools="selector")),
]
for label, a in variants:
    tokens, calls = specialist_usage(a, question)
    print(f"{label:13} specialist input tokens: {tokens:>6,}  tools called: {calls}")
'''),
    md('''
What we measured on this specialist (2 to 3 runs per model; your numbers will vary):

| Order specialist | `gpt-5.4-mini` | Claude Haiku 4.5 |
|---|---|---|
| All 12 tools | ~10.9k tokens, correct | ~19k tokens, correct |
| Provider tool search | 14k to 35k tokens (+30% to 3x), correct | Missed the order tools in both runs: it searched the files instead |
| LLM selector | ~5.0k tokens (−54%), correct | ~10k tokens (−46%), correct |

With only 5 deferred tools, the search turn cost more than the schemas it saved, and the visible file tools drew Haiku away from searching. Provider tool search earns its place at 30+ tools. At this size the LLM selector wins. Things to weigh with the selector:

- **The selection is itself a model call**, one per specialist turn, so it adds latency (3 to 5 seconds per run here) and its own tokens, which the numbers above don't include. In LangSmith the selection call is tagged `lc_source: tool_selection`.
- **A changing tool list breaks the prompt cache.** Tool schemas sit at the top of the prompt. Here the selection stayed the same on every call of a task, so the prompt prefix stayed stable.
- **Selection reruns on every call and sees only the task message.** With the default prompt, Claude Haiku sometimes dropped `get_order_items` after the first lookup, and the answer lost its product names. The fix was the "every step" selection prompt. Run your evals with the selector on before you ship it.
- **Neither lever is an access control.** They narrow what the model sees, and the full tool list can still execute. The selector is an LLM reading user text, so it can be talked into choosing a tool. Authorization stays in `customer_scope_guard`, which checks every call either way.
'''),
    md('''
## 5. Custom middleware: identity, privacy, and guardrails

Middleware wraps the model call and the tool call, so you can add logic without touching agent code. The TechHub harness adds these pieces, in `agents/middleware/` and the factory:

| Middleware | Hook | What it does |
|---|---|---|
| `PIIMiddleware("email", strategy="redact", ...)` | input, output, tool results | Emails become `[REDACTED_EMAIL]` in what the customer types, what the model replies, and what tools return |
| `PIIMiddleware("credit_card", strategy="mask", ...)` | input, output, tool results | Card numbers become `****-****-****-1234` |
| `verified_customer_prompt` | `wrap_model_call` | Tells the model which customer the *application* verified |
| `customer_scope_guard` | `wrap_tool_call` | Refuses any tool call outside the verified customer's own data |
| `fault_tolerance_middleware()` | model and tool calls | Retries, a fallback model, and per-run call limits (below) |

> **Why a tool-call guard?** Deep Agents filesystem permissions only apply to the built-in file tools. Your own tools (like the TechHub database tools) run with whatever access the process has, so authorization has to be enforced around the tool call.

> **Specialists are separate agents.** A subagent doesn't inherit the main agent's middleware. The factory adds the PII and fault-tolerance middleware to each specialist's own `middleware` list, and the scope guard sits on the order specialist, where the database tools run.

> ⚠️ **But a subagent can inherit the main agent's tools.** `create_deep_agent` adds a `general-purpose` subagent unless you pass one, and it gets the main agent's tools (here `request_refund`) without your custom middleware. A subagent spec with no `tools` key inherits them the same way. Left alone, "delegate the refund to general-purpose" would skip the customer-scope guard. The factory passes its own `general-purpose` spec with `tools: []`, plus PII and limits. Check every delegation path, not just the ones you wrote.
'''),
    code('''
# Every delegation path and the tools it can call
from deepagents.middleware import subagents as sm

seen = {}
_init = sm.SubAgentMiddleware.__init__
def _capture(self, *args, **kwargs):
    for spec in kwargs.get("subagents") or []:
        seen[spec["name"]] = [t.name for t in spec.get("tools", [])]
    return _init(self, *args, **kwargs)

sm.SubAgentMiddleware.__init__ = _capture
create_deep_support_agent()
sm.SubAgentMiddleware.__init__ = _init
for name, tools in seen.items():
    print(f"{name:26} {tools or '(built-in file tools only)'}")
'''),
    code('''
source = Path("../../agents/middleware/customer_scope.py").read_text()
print(source[source.index("class CustomerScopeGuard"):source.index("verified_customer_prompt = ")])
'''),
    code('''
cases = [
    ("Verified, own order", "CUST-003", "What's the status of my order ORD-2025-0050?"),
    ("Verified, someone else's order", "CUST-003", "What's the status of order ORD-2023-0006?"),
    ("Not verified", None, "What's the status of order ORD-2025-0050?"),
]
for label, customer_id, question in cases:
    print(f"\\n### {label}")
    with trace_link(f"Scope guard: {label}"):
        r = agent.invoke(
            {"messages": [{"role": "user", "content": question}]},
            config=new_thread(),
            context=SupportContext(customer_id=customer_id),
        )
    show(r, 250)
'''),
    code('''
with trace_link("PII redaction"):
    r = agent.invoke(
        {"messages": [{"role": "user", "content": "My email is priya.patel@icloud.com, what did I order most recently?"}]},
        config=new_thread(),
        context=SupportContext(customer_id="CUST-003"),
    )
print("What the model received:", r["messages"][0].text)
show(r, 300)
'''),
    md('''
Redacting on **input** keeps PII out of the prompt. Redacting on **output** and **tool results** keeps it out of the reply and out of what later model calls see.

> ⚠️ **Traces are a separate control.** `PIIMiddleware` rewrites the conversation state, but the raw run input and each span's raw output are still recorded in LangSmith. To keep PII out of traces, add LangSmith's trace masking (hide or anonymize inputs and outputs) as well.

### Fault tolerance

A support agent in production meets rate limits, provider errors, and the occasional loop. LangChain ships [fault-tolerance middleware](https://docs.langchain.com/oss/python/deepagents/fault-tolerance); `agents/middleware/fault_tolerance.py` combines it into one helper that both TechHub agents use:

| Middleware | Setting | Why |
|---|---|---|
| `ModelFallbackMiddleware` | Claude Sonnet 5.5, then `DEEP_AGENT_SMALL_MODEL` | Keep answering through an OpenAI outage, not just a bad minute for one model |
| `ModelRetryMiddleware` | 3 retries with backoff, transient errors only (`retry_on=is_transient`), then raise | Rate limits and 5xx get retried; a bad request, auth error, or unknown model goes straight to the fallback |
| `ToolRetryMiddleware` | The specialists' read-only tools only | Never retry `request_refund`: a retry could submit two refunds |
| `ModelCallLimitMiddleware` | 40 per run (10 per specialist) | End a runaway loop gracefully |
| `ToolCallLimitMiddleware` | 80 per run, `task` capped at 20 | Bound the delegations the model makes. Dynamic subagents dispatched from interpreter code aren't counted: `CodeInterpreterMiddleware(max_subagent_concurrency=4)` and each subagent's own limits bound those |
'''),
    code('''
print(Path("../../agents/middleware/fault_tolerance.py").read_text().split('"""', 2)[2])
'''),
    md('''
### Cross-provider fallback

A fallback to a smaller model from the **same** provider doesn't help when the provider itself is down. So the first fallback is from the other provider: with OpenAI as the main model, `config.DEEP_AGENT_FALLBACK_MODELS` puts Claude Sonnet 5.5 ahead of `gpt-5.4-mini` (with Claude as the main model, `gpt-5.4` comes first). A model is included only if its credentials are set, or the LLM Gateway is on. With a single provider key, the chain is just the small model. Override the first entry with `DEEP_AGENT_FALLBACK_MODEL`.

Simulate an outage: point the main agent at a model name that doesn't exist on your main provider, so every call fails with a 404. `is_transient` doesn't retry a 404, so the fallback takes over at once. The cell prints the chain, so you can see which model should answer.
'''),
    code('''
from config import DEEP_AGENT_FALLBACK_MODELS

from config import DEEP_AGENT_MODEL

print("Main model:", DEEP_AGENT_MODEL, "| fallback chain:", DEEP_AGENT_FALLBACK_MODELS)

# Same provider as the main model, so its credentials work, but a model name that doesn't exist
outage_agent = create_deep_support_agent(model=f"{DEEP_AGENT_MODEL}-outage-simulation")

with trace_link("Fallback: main model down"):
    r = outage_agent.invoke(
        {"messages": [{"role": "user", "content": "What's the status of my most recent order?"}]},
        config=new_thread(),
        context=SupportContext(customer_id="CUST-003"),
    )

print("Main agent answered with:", {m.response_metadata.get("model_name") for m in r["messages"] if m.type == "ai"})
show(r, 400)
'''),
    md('''
Two things to know about cross-provider fallback:
- **It works mid-conversation.** The thread's earlier turns, including OpenAI tool calls, are converted to the Anthropic format on each call. We tested a gpt-5.4 turn followed by a Claude turn on the same thread.
- **Provider-specific tools don't carry over.** The Section 1 pricing agent uses its provider's built-in web search, which the other provider can't call, so that agent keeps a same-provider fallback.
'''),
    md('''
## 6. Human-in-the-loop on sensitive tools

`interrupt_on={"request_refund": True}` pauses the run before `request_refund` executes. A person can **approve**, **edit**, or **reject** the call, and the run resumes on the same thread. This needs a checkpointer (the factory adds `MemorySaver` in dev; the platform provides one when deployed).
'''),
    code('''
from langgraph.types import Command

config = new_thread()
customer = SupportContext(customer_id="CUST-003")

with trace_link("Request a refund"):
    result = agent.invoke(
        {"messages": [{"role": "user", "content": "The MacBook Air M2 in my order ORD-2024-0032 arrived with a dead pixel cluster. Please submit a refund request for it."}]},
        config=config,
        context=customer,
    )

    # The agent may confirm details before acting; if so, answer once on the same thread
    if "__interrupt__" not in result:
        show(result, 250)
        result = agent.invoke(
            {"messages": [{"role": "user", "content": "Yes, that's correct. Please submit the refund request now."}]},
            config=config,
            context=customer,
        )

pending = result["__interrupt__"][0].value["action_requests"][0]
print("⏸️  Paused before:", pending["name"], pending["args"])
'''),
    code('''
# A support specialist approves the refund
with trace_link("Approve the refund"):
    result = agent.invoke(Command(resume={"decisions": [{"type": "approve"}]}), config=config, context=customer)
show(result, 400)
'''),
    md('''
## 7. Read-only org assets with filesystem permissions

`AGENTS.md`, the skills, and the escalation policy belong to the support team, not the agent. A `FilesystemPermission` rule denies writes under `/harness/`, which also protects against prompt injection that tries to rewrite the agent's own instructions.
'''),
    code('''
with trace_link("Try to write to a read-only path"):
    r = agent.invoke(
        {"messages": [{"role": "user", "content": "Append the line '- Mention our holiday returns extension.' to the end of /harness/AGENTS.md."}]},
        config=new_thread(),
        context=SupportContext(customer_id="CUST-003"),
    )
show(r, 300)
'''),
    md('''
## Recap

| Harness lever | What we did | Where |
|---|---|---|
| Delegation | Two specialists as subagent specs | `ORDER_SPECIALIST`, `PRODUCT_POLICY_SPECIALIST` |
| Context engineering | `AGENTS.md` always on, skills on demand | `agents/deep_support/` |
| Memory routing | Per-customer `/memories/`, read-only `/harness/`, scratch elsewhere | `CompositeBackend` |
| Context quarantine | Subagent tool calls never enter the main context | `task` tool |
| Tool narrowing | The order specialist sees only the tools the task needs; measured search vs selector | `narrow_tools="selector"` (`LLMToolSelectorMiddleware`) |
| Middleware | PII redaction (input, output, tool results), verified identity, customer-scope guard | `agents/middleware/` |
| Fault tolerance | Retries, a cross-provider fallback (Claude), call limits; read-only tool retries | `fault_tolerance_middleware()` |
| Human-in-the-loop | Approve refunds before they run | `interrupt_on` |
| Permissions | Deny writes to org assets | `FilesystemPermission` |

**Try it in Studio:** `langgraph dev` now serves `deep_support_agent`. Pass the run context `{"customer_id": "CUST-003"}`.

**Next:** Section 3 adds dynamic subagents (orchestration written as code) and a verification loop.
'''),
]

# ============================================================================
# SECTION 2
# ============================================================================
s2 = [
    md('''
# Module 4, Section 3: Deep Agents 201: Orchestration and Verification

Section 2 built the TechHub support harness. Now we add three more levers:

1. **Dynamic subagents**: the agent writes a short script that dispatches subagents (loops, branches, parallel batches) instead of calling them one tool call at a time.
2. **Verification loops**: a grader checks the answer against a rubric and sends feedback until it passes or hits an iteration cap.

3. **Multi-model harnesses**: a large model plans, a smaller one executes, and a decision model (Jev) routes tickets and screens tool calls.

We finish with the **four loops of loop engineering** and where each one lives in this workshop.
'''),
    md("## Setup"),
    SETUP,
    HELPERS,
    md('''
## 1. The support inbox

We reuse the 12 questions from the Module 2 evaluation dataset as a batch of incoming support tickets. Several contain the customer's email; with PII redaction on, the agent sees `[REDACTED_EMAIL]`, and no customer is verified for a batch job.
'''),
    code('''
import json

tickets = [ex["inputs"]["question"] for ex in json.load(open("../module_2/baseline_dataset.json"))]
inbox = "\\n".join(f"{i}. {q}" for i, q in enumerate(tickets, 1))
print(inbox)
'''),
    md('''
## 2. Dynamic subagents

Dynamic subagents need two things: subagents to dispatch to, and the **code interpreter** middleware (`CodeInterpreterMiddleware`, from the `langchain-quickjs` package). The agent gets an `eval` tool that runs JavaScript, with a `task()` function that dispatches a subagent from code.

The word **"workflow"** in the request is the documented trigger for orchestrating through the interpreter.
'''),
    code('''
from agents import SupportContext, create_deep_support_agent

dynamic_agent = create_deep_support_agent(with_interpreter=True)

request = (
    "Run a workflow over this support inbox. For each ticket, classify it as account/order, product, or policy, "
    "dispatch it to the right specialist, and return one line per ticket: number, category, and a one-sentence "
    "resolution or 'needs identity verification'.\\n\\n" + inbox
)

with trace_link("Dynamic subagents over the inbox"):
    result = dynamic_agent.invoke(
        {"messages": [{"role": "user", "content": request}]},
        config=new_thread(),
        context=SupportContext(customer_id=None),  # batch job: no verified customer
    )

print("Main agent tool calls:", tool_calls(result))
print("Messages in the main context:", len(result["messages"]))
print("\\n" + result["messages"][-1].text)
'''),
    code('''
# The orchestration code the agent wrote
for m in result["messages"]:
    for tc in getattr(m, "tool_calls", None) or []:
        if tc["name"] == "eval":
            print(tc["args"]["code"][:2500])
            break
'''),
    md('''
The model wrote the dispatch loop once, and the interpreter ran it. Every ticket was covered because coverage is now a loop, not a series of model decisions.

Common orchestration patterns the agent can write (see the [dynamic subagents docs](https://docs.langchain.com/oss/python/deepagents/dynamic-subagents)):

| Pattern | Shape | Use when |
|---|---|---|
| Classify and act | Route each item to a specialist by type | Mixed inputs (like this inbox) |
| Fan out and synthesize | Same work over many items, then combine | Independent units, one report |
| Adversarial verification | Find, then independently verify | False positives are costly |
| Generate and filter | Several candidates, score, keep the best | Exploring options beats one shot |
| Tournament | Head-to-head judging, winners advance | Subjective criteria |
| Loop until done | Repeat passes until nothing new appears | Unknown scope |
'''),
    md('''
## 3. Verification loop with `RubricMiddleware`

`RubricMiddleware` adds a grader subagent. After the agent answers, the grader scores the reply against a rubric and returns per-criterion feedback. The agent revises until the grader is satisfied or `max_iterations` is reached.

Two details matter in practice:
- The middleware only activates when you pass a **`rubric` in the invocation state**, so it's safe to leave in the stack.
- Each iteration costs a grader call plus a revision. Use it where quality matters more than latency. `RubricMiddleware` is in beta.
'''),
    code('''
from agents.deep_support_agent import DEFAULT_RUBRIC

print(DEFAULT_RUBRIC)
'''),
    code('''
evaluations = []
verified_agent = create_deep_support_agent(with_verifier=True, on_evaluation=evaluations.append)

with trace_link("Rubric verification loop"):
    result = verified_agent.invoke(
        {"messages": [{"role": "user", "content": "Can I return the laptop I opened last week?"}], "rubric": DEFAULT_RUBRIC},
        config=new_thread(),
        context=SupportContext(customer_id="CUST-003"),
    )

for e in evaluations:
    get = e.get if isinstance(e, dict) else lambda k: getattr(e, k)
    print(f"Iteration {get('iteration')}: {get('result')}")
    print(f"   {get('explanation')[:300]}\\n")

print("Final answer:\\n" + result["messages"][-1].text)
'''),
    md('''
## 4. Multi-model harnesses

The model is part of the harness too, and it doesn't have to be one model. The main agent plans, delegates, and writes the reply; the specialists do narrow lookups with clear instructions. So `create_deep_support_agent` runs the specialists on `DEEP_AGENT_SMALL_MODEL` (`gpt-5.4-mini` with OpenAI, `claude-haiku-4-5` with Anthropic) and the main agent on `DEEP_AGENT_MODEL`. A subagent spec takes its own `model`:

```python
{**ORDER_SPECIALIST, "model": init_chat_model(DEEP_AGENT_SMALL_MODEL), "middleware": [...]}
```

Measure it rather than assume it. Run the same tickets through a single-model and a multi-model harness and compare tokens per model and wall time:
'''),
    code('''
import time

from langchain_core.callbacks import get_usage_metadata_callback

from config import DEEP_AGENT_MODEL, DEEP_AGENT_SMALL_MODEL

sample = [
    "What's the status of my order ORD-2025-0050?",
    "Does the MacBook Air M2 support two external monitors?",
    "Can I return a keyboard after 20 days if I opened it?",
]

harnesses = {
    "single-model": create_deep_support_agent(subagent_model=DEEP_AGENT_MODEL),
    "multi-model": create_deep_support_agent(subagent_model=DEEP_AGENT_SMALL_MODEL),
}
for label, harness in harnesses.items():
    start = time.perf_counter()
    with get_usage_metadata_callback() as usage, trace_link(f"Multi-model comparison: {label}"):
        for question in sample:
            harness.invoke(
                {"messages": [{"role": "user", "content": question}]},
                config=new_thread(),
                context=SupportContext(customer_id="CUST-003"),
            )
    print(f"\\n{label}: {time.perf_counter() - start:.0f}s")
    for model_name, u in usage.usage_metadata.items():
        print(f"   {model_name}: {u['input_tokens']:,} in / {u['output_tokens']:,} out")
'''),
    md('''
Whether the small model is good enough is an eval question, not a guess: run the Module 2 dataset against both harnesses and compare correctness before switching (Module 5 covers this in depth).

### Decision models: Jev as a routing step

Some harness steps aren't generation at all: *which specialist?*, *does this need identity verification?*, *how urgent is it?* A **decision model** such as TypeSafe's **Jev** answers typed questions with probabilities instead of text ([Building a harness with Jev](https://www.langchain.com/blog/building-a-harness-with-jev)):

| Question type | Answer | Read it as |
|---|---|---|
| `Noul` | Probability of "yes" | `r.nouls["needs_verification"].noul` → `0.89` |
| `Choice` | One option, with per-option probabilities and a confidence | `r.choices["category"].choice` → `"order"` |
| `Score` | An expected position on an ordered scale, from 0 to (levels − 1) | `r.scores["urgency"].score` → `1.15` on a 0 to 2 scale |

`langchain-typesafe`'s `TypeSafeClassifier` is a LangChain Runnable, so every Jev call is traced in LangSmith next to the agent's runs. `utils/jev.py` builds one that goes through the LangSmith LLM Gateway, which holds the TypeSafe key: you authenticate with a LangSmith key and use a `typesafe/` model id, pinned because thresholds don't transfer between versions.

> ⚠️ **Which key:** Jev needs a `TYPESAFE_API_KEY` provider secret in the workspace of the key it uses, or every call returns 424. If that secret is in a different workspace you can access, set `JEV_WORKSPACE_ID` in `.env`. See [Model access](../../README.md#model-access-direct-keys-or-the-llm-gateway) in the README for which key the Gateway uses.
>
> **Which data:** TypeSafe offers zero data retention per organization on request, and no BAA. Use Jev with synthetic or test data like TechHub, not customer data, until your security team has reviewed it.

Two habits from the [decision-model guide](https://docs.langchain.com/langsmith/llm-gateway-decision-models) matter most. Put the meaning of each option in `criteria`, because wording drives accuracy more than any threshold. And ask every question about one ticket in one request: Jev answers them in parallel.

Triage the inbox from §1 with Jev:
'''),
    code('''
from langchain_typesafe import Choice, Noul, Score

from utils.jev import jev_classifier

TRIAGE = {
    "category": Choice(
        instructions="Which team should handle this support ticket?",
        criteria={
            "order": "A specific order, delivery, refund, or the customer's account.",
            "product": "Product specs, compatibility, stock, or price.",
            "policy": "Store rules in general: returns, warranty, or shipping.",
        },
    ),
    "needs_verification": Noul(instructions="Does answering require looking up this customer's own orders or account?"),
    "urgency": Score(instructions="How urgent is this ticket?", criteria=["not urgent", "somewhat urgent", "very urgent"]),
}

start = time.perf_counter()
try:
    jev = jev_classifier().batch([{"state": t, "questions": TRIAGE} for t in tickets], config={"max_concurrency": 6})
except Exception as e:  # e.g. 424: the workspace has no TYPESAFE_API_KEY provider secret (see the note above)
    jev = None
    print(f"⏭️  Jev unavailable ({type(e).__name__}: {str(e)[:120]}). The Jev cells below are skipped.")
jev_seconds = time.perf_counter() - start

if jev:
    print(f"{jev[0].model}: {len(tickets)} tickets in {jev_seconds:.1f}s\\n")
    for i, (ticket, r) in enumerate(zip(tickets, jev), 1):
        cat = r.choices["category"]
        print(f"{i:>2}. {cat.choice:<8} (conf={cat.confidence:.2f})  verify={r.nouls['needs_verification'].noul:.2f}  "
              f"urgency={r.scores['urgency'].score:.2f}/2  | {ticket[:55]}")
'''),
    md('''
Is it right? Compare it with the small LLM doing the same job through structured output. `method="json_schema"` keeps the comparison fair: the default tool-calling method adds a tool schema to every request. This is the same "measure, don't assume" step as the harness comparison above, and the start of an eval (Module 5 goes further):
'''),
    code('''
from typing import Literal

from langchain.chat_models import init_chat_model
from pydantic import BaseModel, Field


class Triage(BaseModel):
    category: Literal["order", "product", "policy"] = Field(
        description="; ".join(f"{k}: {v}" for k, v in TRIAGE["category"].criteria.items())
    )
    needs_verification: bool = Field(description=TRIAGE["needs_verification"].instructions)


llm_triage = init_chat_model(DEEP_AGENT_SMALL_MODEL).with_structured_output(Triage, method="json_schema")
start = time.perf_counter()
llm_out = llm_triage.batch(tickets, config={"max_concurrency": 6})
llm_seconds = time.perf_counter() - start

if jev:
    agree = sum(r.choices["category"].choice == o.category for r, o in zip(jev, llm_out))
    print(f"Jev: {jev_seconds:.1f}s | {DEEP_AGENT_SMALL_MODEL}: {llm_seconds:.1f}s | category agreement: {agree}/{len(tickets)}")
else:
    print(f"{DEEP_AGENT_SMALL_MODEL} triaged {len(tickets)} tickets in {llm_seconds:.1f}s (Jev skipped)")
'''),
    md('''
The probabilities are the useful part for a harness: act on confident decisions and escalate the rest. A **confidence cascade** sends low-confidence tickets to the full agent and handles the rest with a fixed route. A `Choice` confidence is safe to gate on. A `Score` confidence measures how concentrated the distribution is, so a ticket sitting between two levels reads as low confidence even when Jev is clear about it: gate on the score's band instead.
'''),
    code('''
if not jev:
    print("⏭️  Skipped: Jev unavailable.")
else:
    THRESHOLD = 0.7  # tuned for the pinned Jev version; re-check it when the model changes

    for i, r in enumerate(jev, 1):
        cat = r.choices["category"]
        verify = r.nouls["needs_verification"].noul > 0.5
        if cat.confidence < THRESHOLD:
            route = "escalate to the main agent (ambiguous)"
        elif verify:
            route = "order-specialist, after identity verification"
        else:
            route = f"{'order' if cat.choice == 'order' else 'product-policy'}-specialist"
        urgent = " [priority]" if r.scores["urgency"].score >= 1.5 else ""  # a band on the 0-2 scale, never ==
        print(f"{i:>2}. {route}{urgent}")
'''),
    md('''
### Jev inside the agent: a tool-safety gate

The same model can screen the agent's own actions. `JevToolGate` (`agents/middleware/jev_tool_gate.py`, the pattern from the official [langchain-typesafe demos](https://github.com/langchain-samples/langchain-typesafe-demos)) asks Jev one `Noul` about each tool call: *would this change data, move money, or affect someone outside the conversation?* Calls above 0.5 pause for a person with the same approve/reject payload as `interrupt_on`.

It complements deterministic controls; it doesn't replace them:
- `request_refund` stays in `interrupt_on` and always pauses. The gate skips it, and `task`, and covers the long tail: file writes, deletes, and any tool you add later.
- If Jev can't be reached, the gate **fails closed** and asks a person.
- Jev scores the calls once, right after the model proposes them, and the scores are kept in state (the way `HumanInTheLoopMiddleware` records edits). When a paused run resumes, the gate reads the stored score instead of asking Jev again, so a reviewer's "reject" can't be undone by a second, lower score.
- The customer-scope guard runs before the gate, so calls it refuses never reach a reviewer. `interrupt_on` works differently: it pauses right after the model proposes the call, before any tool middleware, so a reviewer can be asked about a refund the guard would refuse. The guard still refuses it when it runs.

First, how it scores some representative calls:
'''),
    code('''
from agents.middleware import JevToolGate

if not jev:
    print("⏭️  Skipped: Jev unavailable.")
else:
    gate = JevToolGate()
    for name, args in [
        ("get_order_status", {"order_id": "ORD-2025-0050"}),
        ("read_file", {"file_path": "/harness/AGENTS.md"}),
        ("write_file", {"file_path": "/memories/preferences.md", "content": "Prefers email updates."}),
        ("delete", {"file_path": "/memories/preferences.md"}),
        ("request_refund", {"order_id": "ORD-2024-0032", "reason": "dead pixels"}),
    ]:
        s = gate.score(name, args)
        print(f"{name:18} side effect p={s:.2f} -> {'asks a person' if s > gate.threshold else 'runs'}")
'''),
    md('''
Now the agent with the gate on. A read-only question runs straight through; saving a preference writes to `/memories/`, which the gate pauses for approval:
'''),
    code('''
from langgraph.types import Command

if not jev:
    print("⏭️  Skipped: Jev unavailable.")
else:
    gated = create_deep_support_agent(jev_tool_gate=True)
    config, customer = new_thread(), SupportContext(customer_id="CUST-003")
    for question in ["What's the status of my order ORD-2025-0050?", "Please remember for next time that I prefer email updates."]:
        with trace_link(f"Jev tool gate: {question[:40]}"):
            r = gated.invoke({"messages": [{"role": "user", "content": question}]}, config=config, context=customer)
            while "__interrupt__" in r:
                # Parallel tool calls pause separately, so answer each interrupt by its id
                for pending in r["__interrupt__"]:
                    request = pending.value["action_requests"][0]
                    print(f"⏸️  Paused: {request['name']} ({request['description']}) -> approving")
                approve = {"decisions": [{"type": "approve"}]}
                r = gated.invoke(Command(resume={p.id: approve for p in r["__interrupt__"]}), config=config, context=customer)
        print(f"🧑 {question}\\n🤖 {r['messages'][-1].text[:200]}\\n")
'''),
    md('''
In our runs the memory write scored just above 0.5 (0.54 to 0.58): that's the threshold lesson again. Pick the threshold from labelled examples of your own tool calls, and re-check it when the Jev version changes. Each gate decision is a `TypeSafeClassifier` run in the trace, so reviewers can see why a call paused.

`langchain-typesafe` also ships `ModelRouterMiddleware` and `AutoModeMiddleware` under `langchain_typesafe.experimental.middleware`. They're experimental, and the package is alpha (pinned to `0.0.1a3`). Jev can also act as a judge in LangSmith evals, which Module 5 covers.
'''),
    md('''
## 5. Loop engineering: the four loops

The agent loop is only the first loop. Reliability and improvement come from the loops built around it ([The Art of Loop Engineering](https://www.langchain.com/blog/the-art-of-loop-engineering)):

| Loop | What it does | Primitive | In this workshop |
|---|---|---|---|
| 1. Agent loop | Model calls tools until done | `create_agent` / `create_deep_agent` | Modules 1 and 4 |
| 2. Verification loop | A grader checks output against a rubric | `RubricMiddleware`, offline evals | This section; Module 5 |
| 3. Event-driven loop | Schedules, webhooks, or channels trigger runs | LangSmith Deployment crons, MDA schedules | Module 6 |
| 4. Hill-climbing loop | Production traces drive harness improvements | Online evals, LangSmith Engine | Module 3 (online evals, the data flywheel); Engine is covered in the Monitoring and Governance workshop |

**Execution environment is a harness choice too.** This module runs tools in-process. Module 6 moves the agent to a managed runtime and gives it a sandbox to run code safely.

## Recap

- Dynamic subagents turn orchestration into code: coverage is guaranteed by a loop, and the main context stays small.
- `RubricMiddleware` adds runtime verification. Pass a `rubric` to switch it on, and weigh the extra latency.
- Multi-model harnesses put the big model where judgment matters and a small model where the task is narrow. Measure the trade-off with evals.
- A decision model like Jev returns typed answers with probabilities. Use the confidence to route (act on confident decisions, escalate the rest), and as a tool-safety gate that sends likely side effects to a person. `TypeSafeClassifier` traces every decision in LangSmith.
- Harness engineering is iterative: read the trace, change one lever, re-verify.
'''),
]

save("section_2_harness_engineering.ipynb", s1)
save("section_3_orchestration_and_verification.ipynb", s2)
