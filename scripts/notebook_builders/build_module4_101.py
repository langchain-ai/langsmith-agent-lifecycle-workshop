"""Build Module 4 Section 1: Deep Agents 101 (pricing research agent on TechHub).

Usage (from the repo root):
    uv run python scripts/notebook_builders/build_module4_101.py workshop_modules/module_4
"""

import sys
from pathlib import Path

import nbformat as nbf

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)


def md(s):
    return nbf.v4.new_markdown_cell(s.strip("\n"))


def code(s):
    return nbf.v4.new_code_cell(s.strip("\n"))


cells = [
    md('''
# Module 4, Section 1: Deep Agents 101

So far TechHub's agents answer customer questions in a few tool calls. Some work is bigger: **"Are we priced competitively on monitors? Research the market, write it up, and recommend changes."** That takes planning, many searches, notes that outlive one turn, delegation, and a human sign-off. This is what **Deep Agents** is built for.

**A deep agent is `create_agent()` plus a harness**, a pre-built middleware stack that gives the model:

| Capability | What it adds | How |
|---|---|---|
| **Planning** | A to-do list the agent writes and updates (opt-in) | `TodoListMiddleware` → `write_todos` |
| **Filesystem** | Files to save work, notes, and large results | `ls`, `read_file`, `write_file`, `edit_file`, `glob`, `grep` |
| **Subagents** | Delegate a task to a specialist with its own context window | `task` tool |
| **Context management** | Offloads large tool results and summarizes long conversations | On by default |
| **Memory and skills** | `AGENTS.md` instructions always loaded; skills loaded on demand | `memory=`, `skills=` |
| **Human-in-the-loop** | Pause before sensitive actions | `interrupt_on=` |
| **Guardrails** | Retries, a fallback model, and call limits for unattended runs | `middleware=` (LangChain built-ins) |

We'll build a **TechHub pricing research agent** one capability at a time:
1. Your first deep agent: market prices with web search
2. Planning with a to-do list
3. Saving work to the filesystem
4. Delegating to subagents
5. The full agent: `AGENTS.md`, skills, and a pricing review
6. Follow-up research on the user's question
7. Long-term memory across conversations
8. Human approval for price changes
9. Guardrails: a research budget and fault tolerance

Web search uses the model provider's **built-in search tool** (`{"type": "web_search"}` for OpenAI), so no search API key is needed.
'''),
    md("## Setup"),
    code('''
import uuid
import warnings

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
warnings.filterwarnings("ignore", category=UserWarning)

from utils.langsmith_links import project_url, trace_link

print(f"📊 All traces from this workshop: {project_url()}")
'''),
    code('''
def new_thread():
    """A fresh conversation (thread) for each example."""
    return {"configurable": {"thread_id": str(uuid.uuid4())}}


def tool_calls(result):
    """Tools the main agent called in the latest turn (subagent name in brackets for `task`)."""
    messages = result["messages"]
    last_human = max((i for i, m in enumerate(messages) if m.type == "human"), default=0)
    names = []
    for m in messages[last_human:]:
        for tc in getattr(m, "tool_calls", None) or []:
            extra = f"[{tc['args'].get('subagent_type')}]" if tc["name"] == "task" else ""
            names.append(tc["name"] + extra)
    return names


def show(result, width=900):
    print("🔧 Tool calls:", tool_calls(result))
    print("💬 Answer:", result["messages"][-1].text[:width])


def file_text(file_data):
    """Text of a file in the agent's state (StateBackend stores a list of lines or a string)."""
    content = file_data.get("content", "") if isinstance(file_data, dict) else file_data
    return "\\n".join(content) if isinstance(content, list) else str(content)
'''),
    md('''
## 1. Your first deep agent

Two tools to start:
- **`web_search`**: the model provider's built-in search. It runs on the provider's side, so there's nothing to install.
- **`get_catalog_prices`**: TechHub's own prices from the product database.
'''),
    code('''
from deepagents import create_deep_agent
from langchain.chat_models import init_chat_model

from agents.pricing_research_agent import get_catalog_prices, web_search_tool
from config import DEEP_AGENT_MODEL

# use_responses_api is needed for OpenAI's built-in web search
llm = init_chat_model(DEEP_AGENT_MODEL, **({"use_responses_api": True} if DEEP_AGENT_MODEL.startswith("openai:") else {}))
web_search = web_search_tool(DEEP_AGENT_MODEL)
print("Model:", DEEP_AGENT_MODEL, "| search tool:", web_search)

first_agent = create_deep_agent(
    model=llm,
    tools=[web_search, get_catalog_prices],
    system_prompt="You are TechHub's pricing analyst. Compare our prices with current US retail prices and cite sources.",
)

print("Built-in harness tools:", sorted(first_agent.nodes["tools"].bound.tools_by_name))
'''),
    code('''
with trace_link("First deep agent: one product"):
    result = first_agent.invoke(
        {"messages": [{"role": "user", "content": "How does our Sony WH-1000XM5 price compare with major US retailers right now?"}]}
    )
show(result)
'''),
    md('''
The harness added file tools and a `task` tool before we wrote any of our own. For a single product, the agent just searched and answered.

> **Where's the search?** Provider web search runs on the model provider's side, so it doesn't appear in `tool_calls`. It shows up as content blocks in the response (`web_search_call` on OpenAI, `server_tool_use` / `web_search_tool_result` on Anthropic), and you can see each search in the LangSmith trace.

Bigger jobs need more structure.
'''),
    md('''
## 2. Planning with a to-do list

Planning is **opt-in** (since deepagents 0.7): add `TodoListMiddleware` and the agent gets a `write_todos` tool. For multi-step work it writes a plan, marks items `in_progress` → `completed`, and revises the plan as it learns. The to-dos are part of the agent's state, so a UI can show progress live.
'''),
    code('''
from langchain.agents.middleware import TodoListMiddleware
from langgraph.checkpoint.memory import MemorySaver

planning_agent = create_deep_agent(
    model=llm,
    tools=[web_search, get_catalog_prices],
    system_prompt="You are TechHub's pricing analyst. Compare our prices with current US retail prices and cite sources.",
    middleware=[TodoListMiddleware()],
    checkpointer=MemorySaver(),  # keeps state (to-dos, files) across turns of a thread
)

config = new_thread()
with trace_link("Planning: two keyboards"):
    result = planning_agent.invoke(
        {"messages": [{"role": "user", "content": "Compare our prices for the Logitech MX Keys keyboard and the Logitech MX Master 3S mouse with 2-3 major US retailers each."}]},
        config=config,
    )

print("📝 Plan:")
for todo in result.get("todos", []):
    print(f"   [{todo['status']}] {todo['content']}")
print()
show(result, 600)
'''),
    md('''
## 3. Saving work to the filesystem

Deep agents work with files the way people do: save intermediate results, then read them back later. By default files live in **agent state** (`StateBackend`), scoped to the thread. That's why the follow-up below, on the **same thread**, can read and extend what the agent already did.
'''),
    code('''
result = planning_agent.invoke(
    {"messages": [{"role": "user", "content": "Save that comparison as a short markdown table to /reports/peripherals_pricing.md."}]},
    config=config,
)
show(result, 300)

files = planning_agent.get_state(config).values.get("files", {})
print("\\n🗂️ Files in this thread:", list(files))
for path, data in files.items():
    print(f"\\n--- {path} ---\\n{file_text(data)[:1500]}")
'''),
    md('''
## 4. Delegating to subagents

A **subagent** is a specialist the main agent calls through the `task` tool. Each runs in its **own context window** and returns only its final answer, so dozens of search results never clutter the main agent's context.

TechHub's pricing agent has two specialists:
- `market-researcher`: web search plus a `think_tool` reflection step; returns retailer, price, sale or regular, URL
- `catalog-analyst`: TechHub catalog only

Independent `task` calls can run in parallel.

**A multi-model harness.** The specialists do narrow, well-specified work, so they run on a smaller, cheaper model (`DEEP_AGENT_SMALL_MODEL`: `gpt-5.4-mini` with OpenAI, `claude-haiku-4-5` with Anthropic) while the main agent plans and writes the comparison on `DEEP_AGENT_MODEL`. A subagent spec takes its own `model`, so the split is one line per specialist.

**A research budget.** Research has no natural end, so the market researcher's prompt caps it at 3 search rounds and asks it to call `think_tool` after each search: what it found, what's missing, and whether to stop. This follows the deepagents [`deep_research`](https://github.com/langchain-ai/deepagents/tree/main/examples/deep_research) reference agent.
'''),
    code('''
from agents.pricing_research_agent import MARKET_RESEARCHER_PROMPT, pricing_subagents
from config import DEEP_AGENT_SMALL_MODEL

print(f"Main agent: {DEEP_AGENT_MODEL} | specialists: {DEEP_AGENT_SMALL_MODEL}\\n")
for sub in pricing_subagents(DEEP_AGENT_SMALL_MODEL):
    print(f"• {sub['name']}: {sub['description']}")
print("\\nmarket-researcher prompt:\\n" + MARKET_RESEARCHER_PROMPT)

delegating_agent = create_deep_agent(
    model=llm,
    system_prompt="You are TechHub's pricing lead. Delegate catalog lookups and market research to your specialists, then compare.",
    subagents=pricing_subagents(DEEP_AGENT_SMALL_MODEL),
    middleware=[TodoListMiddleware()],
)

with trace_link("Subagents: two audio products"):
    result = delegating_agent.invoke(
        {"messages": [{"role": "user", "content": "Are we competitively priced on the AirPods Pro (2nd gen) and the JBL Flip 6?"}]}
    )
show(result, 800)
'''),
    md('''
## 5. The full agent: AGENTS.md, skills, and a pricing review

The finished agent (`agents/pricing_research_agent.py`) packages everything, plus two kinds of context loaded from `agents/pricing_research/`:

| File | Loaded | Purpose |
|---|---|---|
| `AGENTS.md` | Always (system prompt) | How the agent works: delegate, the research budget, numbered citations, save reports, the flagging thresholds |
| `skills/competitive-pricing/SKILL.md` | On demand | Step-by-step method and the report format for a pricing review |

Both are mounted read-only at `/harness/` (a `FilesystemPermission` denies writes).

`AGENTS.md` sets the **research budget** for the whole agent: one researcher per product, at most 4 in parallel, at most 2 delegation rounds, and no re-researching a product already in `/reports/`. Reports cite each source once as `[1]`, `[2]` and end with a `### Sources` list.
'''),
    code('''
from pathlib import Path

print(Path("../../agents/pricing_research/skills/competitive-pricing/SKILL.md").read_text())
'''),
    code('''
from langgraph.store.memory import InMemoryStore

from agents import create_pricing_research_agent

store = InMemoryStore()  # backs /memories/ (section 7)
agent = create_pricing_research_agent(store=store)

review = new_thread()
with trace_link("Full agent: monitor pricing review"):
    result = agent.invoke(
        {"messages": [{"role": "user", "content": "Run our competitive pricing review for the Monitors category."}]},
        config=review,
    )

print("📝 Plan:")
for todo in result.get("todos", []):
    print(f"   [{todo['status']}] {todo['content']}")
print()
show(result, 1500)
'''),
    code('''
files = agent.get_state(review).values.get("files", {})
reports = {p: d for p, d in files.items() if p.startswith("/reports/")}
for path, data in reports.items():
    print(f"--- {path} ---\\n{file_text(data)[:2500]}")
'''),
    md('''
## 6. Follow-up research on the user's question

The report is in the thread's filesystem, so a follow-up doesn't start over: the agent reads what it already found and researches only the new question.
'''),
    code('''
with trace_link("Follow-up research"):
    result = agent.invoke(
        {"messages": [{"role": "user", "content": "Dig deeper on the Samsung 32-inch curved gaming monitor: are there current promotions or a newer model that explain the market price? Update the report."}]},
        config=review,
    )
show(result, 1200)
'''),
    md('''
## 7. Long-term memory across conversations

Thread files disappear with the thread. For things that should persist, such as an analyst's preferences, the agent routes `/memories/` to a **`StoreBackend`**, a long-term store shared across threads. `AGENTS.md` tells it to save preferences in `/memories/preferences.md` and read them at the start of a task.
'''),
    code('''
result = agent.invoke(
    {"messages": [{"role": "user", "content": "For future reviews: always include Best Buy, Amazon, and B&H Photo, and flag anything sold out at those retailers."}]},
    config=new_thread(),
)
show(result, 300)

print("\\n🗂️ Long-term memory:")
for item in store.search(("techhub-pricing",)):
    print(f"{item.key}:\\n{item.value.get('content') if isinstance(item.value, dict) else item.value}")
'''),
    code('''
# A brand-new conversation picks the preferences up from memory
with trace_link("New thread uses memory"):
    result = agent.invoke(
        {"messages": [{"role": "user", "content": "Quick check: how does our Logitech C920 webcam price compare?"}]},
        config=new_thread(),
    )
show(result, 800)
'''),
    md('''
## 8. Human approval for price changes

Changing a price is a business decision, so `propose_price_change` is configured with `interrupt_on`. The run pauses before the tool runs; a pricing manager can **approve**, **edit** (for example, a different price), or **reject**, and the run resumes on the same thread.
'''),
    code('''
from langgraph.types import Command

result = agent.invoke(
    {"messages": [{"role": "user", "content": "Based on the monitor review, propose a price change for the product that is furthest from the market median."}]},
    config=review,
)

# The agent may confirm details before acting; if so, answer once on the same thread
if "__interrupt__" not in result:
    print("🤖 Agent asked first:", result["messages"][-1].text[:300], "\\n")
    result = agent.invoke(
        {"messages": [{"role": "user", "content": "Yes, go ahead and submit that proposal."}]},
        config=review,
    )

pending = result["__interrupt__"][0].value["action_requests"][0]
print("⏸️  Waiting for approval:", pending["name"], pending["args"])
'''),
    code('''
# The pricing manager approves the proposal
result = agent.invoke(Command(resume={"decisions": [{"type": "approve"}]}), config=review)
print(result["messages"][-1].text[:600])
'''),
    md('''
## 9. Guardrails: a research budget and fault tolerance

Prompts ask the agent to stay on budget; middleware enforces it. A research agent that runs unattended (a nightly pricing review, say) also has to survive a provider hiccup. The full agent adds LangChain's built-in [fault-tolerance middleware](https://docs.langchain.com/oss/python/deepagents/fault-tolerance) through one helper, `agents/middleware/fault_tolerance.py`:

| Middleware | Setting here | Why |
|---|---|---|
| `ModelFallbackMiddleware` | Falls back to `DEEP_AGENT_SMALL_MODEL` | Keep working if the main model keeps failing |
| `ModelRetryMiddleware` | 3 retries, exponential backoff | Rate limits and 5xx errors are usually transient |
| `ToolRetryMiddleware` | `get_catalog_prices` only | Retry **read-only** tools. Never retry `propose_price_change`: a retry could submit it twice |
| `ModelCallLimitMiddleware` | 40 per run (8 per researcher) | Stop a runaway loop with a graceful ending |
| `ToolCallLimitMiddleware` | 60 per run, `task` capped at 10 | Enforce the research budget on delegations |

Order matters: middleware listed first wraps the rest, so the fallback sits outside the retries.
'''),
    code('''
import inspect

from agents.middleware import fault_tolerance_middleware

print(inspect.getsource(fault_tolerance_middleware))
'''),
    md("Here is the call limit at work: the same delegating agent with a budget of 3 model calls. Instead of erroring or looping, the run ends cleanly and says why."),
    code('''
budget_agent = create_deep_agent(
    model=llm,
    system_prompt="You are TechHub's pricing lead. Delegate catalog lookups and market research to your specialists, then compare.",
    subagents=pricing_subagents(DEEP_AGENT_SMALL_MODEL),
    middleware=[TodoListMiddleware(), *fault_tolerance_middleware(model_call_limit=3)],
)

with trace_link("Guardrails: model call limit"):
    result = budget_agent.invoke(
        {"messages": [{"role": "user", "content": "Benchmark every keyboard and every audio product we sell against 3 retailers each."}]}
    )
limit_notice = "Model call limits exceeded"
print("Model calls made by the main agent:", sum(1 for m in result["messages"] if m.type == "ai" and not m.text.startswith(limit_notice)))
show(result, 400)
'''),
    md('''
## Recap

| Capability | What we used | TechHub example |
|---|---|---|
| Built-in tools | Provider web search + a catalog tool | Market prices vs our catalog |
| Planning | `TodoListMiddleware` | A visible plan for multi-product research |
| Filesystem | `StateBackend` (per thread) | `/reports/*.md` that follow-ups build on |
| Subagents | `task` → `market-researcher`, `catalog-analyst` | Isolated research, parallel lookups |
| Instructions and skills | `AGENTS.md` + `skills/competitive-pricing` | Consistent method and report format |
| Long-term memory | `StoreBackend` at `/memories/` | Analyst preferences across conversations |
| Human-in-the-loop | `interrupt_on` | Approval before any price change |
| Multi-model harness | Subagent `model` | Specialists on the small model, planning on the main one |
| Research budget | `AGENTS.md` caps, `think_tool`, `task` limit | Bounded, cited research |
| Fault tolerance | Retry, fallback, and call-limit middleware | Survives provider errors, can't loop forever |

**Try it in Studio:** `langgraph dev` serves `pricing_research_agent`.

**In production (Module 6):** Managed Deep Agents supports the same provider search tool dict, or built-in **Parallel** web search: add the Parallel MCP server in `tools/mcp.py`, with no search API key. It's in private beta, on LangSmith Plus and Startup plans only, and LangSmith managed tools run in GCP US only.

**Next:** Sections 2 and 3 (Deep Agents 201) take the TechHub *support* agent and improve it by engineering the harness: context, middleware, dynamic subagents, and verification loops.
'''),
]

nb = nbf.v4.new_notebook()
nb.cells = cells
for i, cell in enumerate(cells):  # stable ids, so regenerating gives a clean diff
    cell["id"] = f"cell-{i:03d}"
nb.metadata["kernelspec"] = {"display_name": "Python 3 (ipykernel)", "language": "python", "name": "python3"}
nbf.write(nb, OUT / "section_1_deep_agents_101.ipynb")
print("wrote", OUT / "section_1_deep_agents_101.ipynb", len(cells), "cells")
