"""Build Module 6 notebooks (Deploying agents into production) for the TechHub workshop.

Usage (from the repo root):
    uv run python scripts/notebook_builders/build_module6.py workshop_modules/module_6
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
import os
import warnings
from pathlib import Path

from dotenv import dotenv_values, load_dotenv
from langgraph_sdk import get_client

load_dotenv()
warnings.filterwarnings("ignore", category=UserWarning)

PROJECT = Path("../../managed_agent")
DEPLOYMENT_URL = os.environ.get("MDA_DEPLOYMENT_URL")
assert DEPLOYMENT_URL, "Run `mda deploy` in managed_agent/ and set MDA_DEPLOYMENT_URL in .env"

# MDA's identity.py authenticates callers with a LangSmith API key
client = get_client(url=DEPLOYMENT_URL, api_key=os.environ["LANGSMITH_API_KEY"])
print("Agent Server:", DEPLOYMENT_URL)
''')

HELPERS = code('''
def answer_text(run_or_state):
    """Final assistant text (handles string and content-block responses)."""
    content = run_or_state["messages"][-1]["content"]
    if isinstance(content, str):
        return content
    return " ".join(block.get("text", "") for block in content if isinstance(block, dict))


async def ask(question, customer_id=None, thread_id=None, role=None):
    """Run the deployed agent on a (new) thread with the verified customer (or ops role) as context."""
    thread_id = thread_id or (await client.threads.create())["thread_id"]
    context = {k: v for k, v in {"customer_id": customer_id, "role": role}.items() if v}
    run = await client.runs.wait(
        thread_id,
        "techhub-support",
        input={"messages": [{"role": "user", "content": question}]},
        context=context,
    )
    return thread_id, run
''')

# ============================================================================
# SECTION 1
# ============================================================================
s1 = [
    md('''
# Module 6, Section 1: Managed Deep Agents

In this section, we'll put the TechHub customer support agent into production with **Managed Deep Agents (MDA)**. The agent is built on [Deep Agents](https://docs.langchain.com/oss/python/deepagents/overview), LangChain's open-source agent harness. MDA runs that harness on LangSmith: you describe the agent as files in a folder, and LangSmith provides the server, persistence, sandbox, memory, schedules, and sign-in.

If you did Module 4, this is the same support agent you built there with `create_deep_agent`.

We'll cover:
1. **From Deep Agents to Managed Deep Agents**: what moves where, from `create_deep_agent` to `define_deep_agent`
2. **Project anatomy**: an agent is a directory
3. **Local dev and deploy**: `mda dev` → `mda deploy`
4. **Call the deployed agent** with the LangGraph SDK, with a verified customer as run context
5. **Human-in-the-loop over the API**
6. **Context Hub, memory, and schedules**

'''),
    md("## Setup"),
    SETUP,
    HELPERS,
    md('''
## 1. From Deep Agents to Managed Deep Agents

| Deep Agents (`agents/deep_support_agent.py`) | Managed Deep Agents (`managed_agent/`) |
|---|---|
| `create_deep_agent(...)` builds and compiles the graph | `define_deep_agent(...)` only *declares* it; MDA compiles and runs it |
| `memory=["/harness/AGENTS.md"]` | `instructions.md` (synced to Context Hub) |
| `skills=["/harness/skills/"]` + a `FilesystemBackend` route | `skills/` (synced to Context Hub, read-only to the agent) |
| `StoreBackend` route at `/memories/` | `memory.py` (`/memories/agent/`, shared, mounted for ops runs only) |
| `StateBackend` scratch + no code execution | `sandbox/`: a real filesystem and shell per thread |
| `MemorySaver` + `InMemoryStore` | Managed checkpointer and store |
| `langgraph.json` + `langgraph deploy` | `mda deploy` |
| You build these yourself | `schedules/` (crons), `channels/` (Slack), `identity.py` (caller auth) |

The tools, subagents, middleware (fault tolerance, PII redaction, customer-scope guard), the multi-model setup, and refund approval carry over unchanged: `define_deep_agent` accepts the same `tools`, `subagents`, `middleware`, and `interrupt_on`.
'''),
    md('''
### Production guardrails MDA doesn't add for you

MDA supplies the server, persistence, sandbox, and auth. Limits and data controls are still harness choices in `agent.py`:

| Guardrail | Where | What it does |
|---|---|---|
| Fault tolerance | `middleware/fault_tolerance.py` | Retries transient model errors, falls back to Claude Sonnet 5.5 and then the small model, retries read-only tools only, caps model and tool calls per run |
| PII redaction | `pii_middleware()` in `agent.py` | Redacts emails and masks card numbers in user input, model output, and tool results |
| Customer scope | `middleware/customer_scope.py` | Every order lookup must belong to the verified customer. Identity token claims win over run context |
| Approval | `interrupt_on` | `request_refund` waits for a human |
| Shared memory | `memory.py` | Agent memory mounts for `role == "ops"` runs only |
| Sandbox egress | `sandbox/__init__.py` | Default-deny allowlist: PyPI and GitHub tarballs on port 443 |
| Multi-model | `model.py` | Specialists run on the small model (`gpt-5.4-mini` or `claude-haiku-4-5`); the main agent plans on the main model |
| Delegation paths | `agent.py` | Every subagent lists its `tools` explicitly, and an explicit `general-purpose` spec replaces the default, so no subagent can call `request_refund` without the guard |

**Who is the customer?** The workshop passes `customer_id` in the run context because `identity.py` uses LangSmith API keys, so every caller is a trusted workspace service. In production, sign customers in with a JWT, Supabase, or backend identity provider and put `customer_id` in the token. The guard reads `principal.claims["customer_id"]` first and refuses a run whose context names a different customer. See [Identity](https://docs.langchain.com/langsmith/python/managed-deep-agents-identity) for the provider options.
'''),
    md('''
## 2. Project anatomy: an agent is a directory

A file's location decides its role. Everything outside the managed paths is ordinary Python you import. Here is the top level of `managed_agent/`. To read any file, open the folder in your editor (in Instruqt, the VS Code tab).
'''),
    code('''
for path in sorted(PROJECT.iterdir()):
    if not path.name.startswith((".", "__")):
        print(path.name + ("/" if path.is_dir() else ""))
'''),
    md('''
### How a project starts: `mda init`

`managed_agent/` began as the project that `mda init` writes: a minimal agent you can deploy straight away. The next cell
creates a throwaway one in a temporary folder, so you can see what you start from. Nothing is deployed.
'''),
    code('''
import subprocess
import tempfile

scratch = Path(tempfile.mkdtemp())
subprocess.run(
    ["uv", "run", "--project", str(PROJECT), "mda", "init", "support-bot",
     "--model", "anthropic:claude-sonnet-5-5",
     "--instructions", "You are TechHub's support assistant.",
     "--no-sandbox"],
    cwd=scratch, stdin=subprocess.DEVNULL, capture_output=True, check=True,
)
starter = scratch / "support-bot"
for path in sorted(starter.iterdir()):
    print(path.name)
print("\\n--- agent.py ---")
print((starter / "agent.py").read_text())
'''),
    md('''
That is a complete agent: a `name`, a `model`, `instructions.md` for the system prompt, and `identity.py` for who may call
it. `--no-sandbox` left out the sandbox; without the flag, `mda init` also writes `sandbox/`. `mda init --help` lists the
other options, such as `--memory agent` and `--channel slack`.

`managed_agent/` is the same kind of project after adding what TechHub's support agent needs: `tools/` and `middleware/`
(ordinary Python that `agent.py` imports), subagents and refund approval in `agent.py`, `memory.py`, `sandbox/`, and
`evals/`. You add each of those files only when the agent needs it.
'''),
    md('''
### Defining the agent: `define_deep_agent`

Every MDA project has an `agent.py` that exports `agent = define_deep_agent(...)`. The starter from `mda init` only sets
two arguments:

```python
from managed_deepagents import define_deep_agent

agent = define_deep_agent(
    name="support-bot",                    # the assistant ID callers use
    model="anthropic:claude-sonnet-5-5",   # any provider:model string, or a chat model object
)
```

TechHub's support agent uses the same call with more arguments. This is the definition in `managed_agent/agent.py`:

```python
agent = define_deep_agent(
    name="techhub-support",
    model=resolve_model(),
    tools=[request_refund],
    subagents=[ORDER_SPECIALIST, PRODUCT_POLICY_SPECIALIST, GENERAL_PURPOSE],
    middleware=[
        *fault_tolerance_middleware(
            fallback_models=FALLBACK_MODELS,
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
```

| Argument | What it does here |
|---|---|
| `name` | The assistant ID. Callers use `techhub-support`, whatever the deployment is called |
| `model` | `resolve_model()` in `model.py` picks a model from the credentials you have (in the Instruqt lab, Claude on Amazon Bedrock) |
| `tools` | Tools the main agent can call itself. Order lookups live in the order specialist instead |
| `subagents` | The order specialist, the product and policy specialist, and an explicit `general-purpose` subagent. Each lists its own tools and middleware |
| `middleware` | Retries, fallback models and call limits; PII redaction; the verified-customer prompt; the customer-scope guard |
| `interrupt_on` | Pauses before `request_refund` until a person approves it |
| `context_schema` | The run context a caller can pass (`customer_id`, `role`) |

There is no `system_prompt`, `memory`, `skills`, `backend`, `store` or `checkpointer` argument. MDA fills those in from
`instructions.md`, `skills/`, `memory.py`, `sandbox/` and its managed runtime. The next cell prints the whole file,
including the subagent definitions.
'''),
    code('''
print((PROJECT / "agent.py").read_text())
'''),
    md('''
| Path | What MDA does with it |
|---|---|
| `agent.py` | Required. Exports `agent = define_deep_agent(...)` |
| `instructions.md`, `skills/` | System prompt and skills, synced to **Context Hub** on deploy |
| `memory.py` | Opt-in durable memory (`MemoryLayer`) |
| `sandbox/__init__.py` + `setup.sh` | A LangSmith sandbox per thread; `setup.sh` runs once and is saved as a snapshot |
| `schedules/<name>.py` | One LangSmith cron per file (direct children only) |
| `identity.py` | Who may call the deployment |
| `tools/`, `middleware/` | Your own modules, imported by `agent.py` |

> ⚠️ `mda build` packages the **whole project folder** (up to 200 MB). Keep the project in its own directory, which is why the tools are copied into `managed_agent/tools/` rather than imported from the repo's `tools/`.
'''),
    md('''
## 3. Local dev and deploy

From `managed_agent/` in a terminal:

```bash
uv tool install --prerelease allow managed-deepagents   # once: installs the `mda` CLI
uv sync                                                 # the project's own environment
mda dev                                                 # compile, build the sandbox snapshot, run locally in Studio
mda deploy                                              # build and host it on LangSmith
```

`.env` (copy `.env.example`) needs `LANGSMITH_API_KEY` plus **one** way to reach the model. `model.py` picks the model strings from what's set:

| Option | `managed_agent/.env` | Main / specialists |
|---|---|---|
| A. Your own provider key(s) | `OPENAI_API_KEY` and/or `ANTHROPIC_API_KEY` | `openai:gpt-5.4` / `gpt-5.4-mini`; Anthropic only: `claude-sonnet-5-5` / `claude-haiku-4-5`. With both keys, Claude is the fallback |
| B. LangSmith LLM Gateway | `LANGSMITH_GATEWAY_API_KEY="<LangSmith key>"`, no provider keys. The workspace needs provider secrets, and the key needs `gateway:invoke` | `langsmith:openai/gpt-5.4` / `langsmith:openai/gpt-5.4-mini` |

Why `LANGSMITH_GATEWAY_API_KEY` and not `LANGSMITH_API_KEY`? `LANGSMITH_API_KEY` is reserved: it authenticates the CLI and is never uploaded to the deployment. `DEEP_AGENT_MODEL` overrides the main model, e.g. `anthropic:claude-sonnet-5-5` or `langsmith:anthropic/claude-sonnet-5-5`.

`mda deploy` routes each input to a managed surface:

```text
instructions.md + skills/**  -> Context Hub
.env                         -> deploy auth + hosted secrets (never in the build archive)
project source files         -> build archive -> hosted Agent Server
schedules/*.py               -> LangSmith cron jobs
sandbox/setup.sh             -> sandbox snapshot that new threads clone
```
'''),
    md('''
## 4. Call the deployed agent

The deployment is a standard **Agent Server**, so any LangGraph SDK client can call it. The application passes the **verified** customer as run `context`; the customer-scope guard (`middleware/customer_scope.py`) enforces it on every tool call.
'''),
    code('''
assistants = await client.assistants.search()
print("Graphs on this deployment:", [a["graph_id"] for a in assistants])

_, run = await ask("What's the status of my order ORD-2025-0050?", customer_id="CUST-003")
print("\\n✅ Verified, own order:\\n" + answer_text(run)[:400])

_, run = await ask("What's the status of order ORD-2023-0006?", customer_id="CUST-003")
print("\\n⛔ Someone else's order:\\n" + answer_text(run)[:300])
'''),
    md('''
## 5. Human-in-the-loop over the API

`interrupt_on={"request_refund": True}` works the same when deployed. The run pauses with status `interrupted`; your application (or a support console) shows the pending action and resumes the same thread with a decision.
'''),
    code('''
customer = {"customer_id": "CUST-003"}
thread = await client.threads.create()


async def pending_interrupts():
    state = await client.threads.get_state(thread["thread_id"])
    return state.get("interrupts") or [i for task in state["tasks"] for i in task.get("interrupts", [])]


run = await client.runs.wait(
    thread["thread_id"],
    "techhub-support",
    input={"messages": [{"role": "user", "content": "The MacBook Air M2 in my order ORD-2024-0032 arrived with a dead pixel cluster. Please submit a refund request for it."}]},
    context=customer,
)

# The agent may confirm details before acting; if so, answer once on the same thread
interrupts = await pending_interrupts()
if not interrupts:
    print("🤖 Agent asked first:", answer_text(run)[:250], "\\n")
    await client.runs.wait(
        thread["thread_id"],
        "techhub-support",
        input={"messages": [{"role": "user", "content": "Yes, that's correct. Please submit the refund request now."}]},
        context=customer,
    )
    interrupts = await pending_interrupts()

pending = interrupts[0]["value"]["action_requests"][0]
print("⏸️  Waiting for approval:", pending["name"], pending["args"])
'''),
    code('''
run = await client.runs.wait(
    thread["thread_id"],
    "techhub-support",
    command={"resume": {"decisions": [{"type": "approve"}]}},
    context=customer,
)
print(answer_text(run)[:400])
'''),
    md('''
## 6. Context Hub, memory, and schedules

**Context Hub.** `instructions.md` and `skills/` live in Context Hub after a deploy. Edit them in the LangSmith UI and the running deployment picks up the change on the next run, with no redeploy. Try it: open the deployment, edit the "Answer style" section of the instructions, and re-run the cell in §4. The next `mda deploy` notices the UI edit and asks whether to keep it or overwrite it from `instructions.md`; in a script, pass `--context-strategy keep-hub` or `overwrite`.

**Agent memory is a trust boundary.** The agent layer (`/memories/agent/`) is one tree shared by every run that mounts it, and its `AGENTS.md` is loaded into each later run. If customers could write to it, one customer could plant a note, or an instruction, that the next customer's run follows. So `memory.py` mounts it only for operations runs:

```python
def ops_only(context) -> bool:
    role = context.get("role") if isinstance(context, dict) else getattr(context, "role", None)
    return role == "ops"

memory = define_memory(agent=MemoryLayer(allow=ops_only))
```

> **Who sets `role`?** `allow` only sees the run context, not the signed-in identity. With API-key identity every caller is a trusted service, so that's fine for this workshop. In production, set `role` from a trusted backend (`define_identity(auth="backend")`), not from end-user input.

`allow` runs once per run, before storage mounts. Returning `False` skips the mount for that run and deletes nothing. A tip every customer should get belongs in `instructions.md` or a skill, which a person reviews in Context Hub. Per-customer memory needs the `user` layer, which requires identity.

Below, the ops team saves a tip, then we list `/memories/agent/` from an ops run and from a customer run. The customer run gets the runtime's own answer: the layer isn't mounted.
'''),
    code('''
# The ops team saves a tip (agent memory is mounted for role="ops")
_, run = await ask(
    "Support tip to remember: customers often confuse the 14-day opened-item window "
    "with the 30-day unopened window, so always state both.",
    role="ops",
)
print("Ops run:", answer_text(run)[:250])


async def memory_listing(**who):
    """Ask the agent to list /memories/agent/ and return the raw tool result."""
    thread_id, run = await ask(
        "Run ls on /memories/agent/ with your file tools and paste the raw result. Do not answer anything else.", **who
    )
    messages = (await client.threads.get_state(thread_id))["values"]["messages"]
    results = [str(m["content"])[:200] for m in messages if m["type"] == "tool"]
    return results or answer_text(run)[:200]


print("\\nOps run sees:     ", await memory_listing(role="ops"))
print("Customer run sees:", await memory_listing(customer_id="CUST-019"))
'''),
    md('''
**Schedules (the event-driven loop).** Each file directly under `schedules/` becomes a LangSmith cron when you deploy. In this repo the digest is parked in `schedules/_demo/` (nested files are ignored), so it doesn't run every weekday. To demo it:

```bash
mv schedules/_demo/delayed_orders_digest.py schedules/
mda dev        # schedules run locally while the server is up; or `mda deploy` for a hosted cron
```

The schedule passes `context={"role": "ops"}`, which the guard requires for the ops-only `get_delayed_orders` tool.
'''),
    code('''
print((PROJECT / "schedules/_demo/delayed_orders_digest.py").read_text())
'''),
    md('''
**Connections and channels (not built here).** Two more managed surfaces, for when the agent reaches past its own database:

| Surface | What it does | How |
|---|---|---|
| Connections | Credentials for an external service live in the LangSmith workspace, not in `.env`, so they rotate without a redeploy. An agent-owned connection is one shared credential; a user-owned OAuth connection acts as whoever called the agent | `mda connections create <slug>` (a fixed API key, your own OAuth app, or MCP OAuth), then `connections.get("<slug>", {"type": "agent"})` in a tool, or on a server in `tools/mcp.py` |
| Channels | The agent answers where people already are, such as a Slack thread, instead of only over the API | A declaration in `channels/`; `mda deploy` sets up the Slack app |

For TechHub, a carrier's tracking API would be an agent-owned connection, and a Slack channel would let the support team ask the agent from a thread. Both follow the same rules as everything above: the scope guard still decides which customer's data a run may see. See [Manage connections](https://docs.langchain.com/langsmith/python/managed-deep-agents-connections).
'''),
    md('''
## Recap

- MDA describes a Deep Agents harness as a folder of files; `mda deploy` turns the folder into a hosted Agent Server.
- The guard, PII redaction, fault tolerance, and refund approval came along unchanged: harness choices are portable.
- Context Hub lets you change instructions and skills without a redeploy.
- Agent memory is shared by every run that mounts it: gate it with `allow` so customers can't write what other customers read.
- In production, the customer ID comes from the identity token, not the run context.

**Next:** Section 2 looks at the runtime API and the sandbox.
'''),
]

# ============================================================================
# SECTION 2
# ============================================================================
s2 = [
    md('''
# Module 6, Section 2: Runtime and Sandboxes

Every Managed Deep Agent runs on **LangSmith Agent Server**. In this section:
1. **Runtime primitives**: assistants, threads, runs, and streaming
2. **Sandboxes**: running code safely, and deciding what data goes inside
3. **Security checklist** for sandboxes
4. **Evaluate before you ship**: Harbor evals for the managed agent
5. **Where to go next**: deployment options, monitoring
'''),
    md("## Setup"),
    SETUP,
    HELPERS,
    md('''
## 1. Runtime primitives

| Primitive | What it is |
|---|---|
| **Assistant** | A configured instance of a graph (here: `techhub-support`) |
| **Thread** | A conversation's persisted state (checkpoints) |
| **Run** | One invocation on a thread; can be waited on, streamed, backgrounded, or interrupted |
| **Cron** | A scheduled run (MDA creates these from `schedules/`) |
| **Store** | Long-term memory (MDA's memory layers sit on Context Hub) |

The server also exposes an **MCP endpoint** and the full Agent Server API at `<deployment>/docs`.
'''),
    code('''
thread_id, run = await ask("Which of my orders shipped most recently?", customer_id="CUST-003")

state = await client.threads.get_state(thread_id)
print("Messages persisted on the thread:", len(state["values"]["messages"]))
print("Checkpoint:", state["checkpoint"]["checkpoint_id"])

threads = await client.threads.search(limit=5)
print("\\nRecent threads:", [(t["thread_id"][:8], t["status"]) for t in threads])
'''),
    md("Streaming works the same way as for any LangGraph deployment. Here we stream updates and print which node produced each one:"),
    code('''
thread = await client.threads.create()
async for chunk in client.runs.stream(
    thread["thread_id"],
    "techhub-support",
    input={"messages": [{"role": "user", "content": "Is the warranty on monitors different from laptops?"}]},
    context={"customer_id": "CUST-003"},
    stream_mode="updates",
):
    if chunk.event == "updates" and isinstance(chunk.data, dict):
        print("•", ", ".join(chunk.data.keys()))
'''),
    md('''
## 2. Sandboxes: running code safely

`sandbox/__init__.py` gives each **thread** its own LangSmith sandbox: a microVM with a filesystem, a shell, and an `execute` tool. `sandbox/setup.sh` runs once at deploy; the result is captured as a **snapshot** that new threads clone, so they start ready.
'''),
    code('''
print((PROJECT / "sandbox/__init__.py").read_text().split('"""')[-1])
print((PROJECT / "sandbox/setup.sh").read_text())
'''),
    md('''
### What goes in the sandbox is a security decision

The sandbox gets only **public** data: product docs, store policies, and the product catalog. Customer and order data stays in the agent server behind the guarded tools.

If `techhub.db` were in the sandbox, the model could run `sqlite3` over every customer's orders and the customer-scope guard would never see it. **Code execution bypasses tool-level authorization**, so only put data in a sandbox that every caller of the agent is allowed to see.
'''),
    code('''
_, run = await ask(
    "Using /workspace/techhub/products.json in your sandbox, run Python to compute the average price and "
    "item count per category. Show the table and the code you ran.",
    customer_id="CUST-003",
)
print(answer_text(run)[:1500])
'''),
    md('''
### Egress: default-deny

`proxy_config={"access_control": {"allow_list": [...]}}` makes the sandbox network default-deny. The allowlist holds only the hosts `setup.sh` needs, pinned to port 443, which also blocks raw TCP (SSH, databases).

> ⚠️ **Which policy you're seeing depends on your plan.** Non-Enterprise organizations get LangSmith's managed egress allowlist by default, and it *replaces* the project's `access_control` ([organization-level restricted egress](https://docs.langchain.com/langsmith/sandbox-auth-proxy#organization-level-restricted-egress)). That list includes PyPI, npm, GitHub, OpenAI, Anthropic, and LangSmith, so those stay reachable even though this project doesn't list them. Enterprise organizations without restricted egress get exactly this project's list.

Ask the agent to reach a host that neither list allows:
'''),
    code('''
_, run = await ask(
    "In your sandbox, run this exact command and show me its raw output: "
    "curl -sS -m 10 -o /dev/null -w 'HTTP %{http_code}' https://example.com; echo \\" exit=$?\\"",
    customer_id="CUST-003",
)
print(answer_text(run)[:600])
'''),
    md('''
## 3. Sandbox security checklist

| Topic | What to know |
|---|---|
| Isolation | Sandboxes are **microVMs**, not containers. Non-root execution and dropped Linux capabilities are not currently configurable; restrict what code can reach instead |
| Network | Set a default-deny `allow_list` in `proxy_config` (this project allows PyPI and GitHub tarballs on 443 only). Non-Enterprise orgs also get a LangSmith-managed egress allowlist, which replaces yours. The **auth proxy** injects credentials so secrets never enter the sandbox |
| Output | Treat everything the sandbox produces as untrusted input; review it before acting on it |
| Secrets | Never write secrets in `setup.sh`: everything on disk becomes part of every thread's snapshot |
| Scope | One sandbox per thread, reclaimed after `idle_ttl_seconds` |
| Data | Only what every caller may see (see above). Customer data stays behind guarded tools |
| Permissions | Declaring an MDA sandbox clears filesystem permission rules; control access through the tools you expose |

See [LangSmith sandboxes](https://docs.langchain.com/langsmith/sandboxes) and [sandbox auth proxy](https://docs.langchain.com/langsmith/sandbox-auth-proxy).
'''),
    md('''
## 4. Evaluate before you ship: Harbor evals

MDA evals are [Harbor](https://www.harborframework.com/docs/tasks) tasks ([docs](https://docs.langchain.com/langsmith/python/managed-deep-agents-evals)). `mda evals init` creates the workspace (`evals/harbor-job.json`). Each direct child of `evals/` with an `instruction.md` and `tests/` is a task:

- Harbor builds the task's container.
- The MDA adapter installs the **compiled agent** into the container and runs `sandbox/setup.sh`.
- The agent answers `instruction.md`.
- `tests/test.sh` scores the final state from `/logs/agent/result.json`.

An `identity.json` in the task becomes the caller's verified identity, so you can test authorization the way a signed-in customer would hit it. The eval runner passes no run context; the guard reads identity claims first.

The project ships three tasks, one per thing that matters for this agent:
'''),
    code('''
import json

for task in sorted(p for p in (PROJECT / "evals").iterdir() if (p / "instruction.md").exists()):
    claims = json.loads((task / "identity.json").read_text()).get("claims", {})
    print(f"▶ {task.name}   (caller claims: {claims})")
    print("  instruction:", (task / "instruction.md").read_text().strip())
    print("  pass rule: ", next(l for l in (task / "task.toml").read_text().splitlines() if l.startswith("# PASS RULE")).removeprefix("# PASS RULE: "))
    print()
'''),
    md('''
The verifiers are deterministic checks on the agent's output, not an LLM judge. The cross-customer task is the security one: it fails if any detail of another customer's order shows up anywhere in the run, including subagent reports. It also catches a leak through the default `general-purpose` subagent, which would otherwise get the order tools without the guard:
'''),
    code('''
print((PROJECT / "evals/cross-customer-order-refused/tests/verify.py").read_text())
'''),
    md('''
**Run them** (needs Docker and `uv`; from `managed_agent/`):

```bash
HARBOR_LANGSMITH_DATASET=mda-techhub-support-evals \\
PYTHONPATH=.mda/evals/harbor-adapter \\
uv run --env-file .env --python 3.12 --with 'harbor[langsmith]==0.21.0' harbor run \\
  --config evals/harbor-job.json --yes \\
  --plugin mda_harbor.job_plugin:MDAJobPlugin \\
  --plugin mda_harbor.langsmith_plugin:LangSmithPlugin

uv run --python 3.12 --with 'harbor[langsmith]==0.21.0' harbor view .mda/evals/jobs
```

With `LANGSMITH_API_KEY` set, the runs are recorded in the `HARBOR_LANGSMITH_DATASET` dataset in LangSmith. When an eval fails:
- If the task measured the wrong thing, fix the task or verifier.
- If it exposed an agent failure, fix the agent and re-run.

Then deploy. Running the evals on every change, before release, is what makes them a gate. `managed_agent/evals/README.md` has the details, including how to run them through the LLM Gateway.

> 💡 **Building your own:** the [`eval-engineering` skill](https://github.com/langchain-ai/langchain-skills/blob/main/config/skills/eval-engineering/SKILL.md) walks a coding agent through a Task Spec (`Task.md`), environment, and verifier. That's how these three were built.
'''),
    md('''
## 5. Where to go next

| Topic | Where |
|---|---|
| Deeper evaluation: judge alignment, trajectory evals, experiments | Module 5 (evaluation) |
| Deployment options: Cloud, BYOC, self-hosted | LangSmith Deployment docs. MDA runs on LangSmith Cloud (GCP US/EU/APAC, AWS US) during public beta; BYOC and self-hosted aren't supported yet |
| Online evals, Insights, Engine (the hill-climbing loop) | Module 3 (online evals, the data flywheel); the Monitoring and Governance workshop for Insights and Engine |
| Tear down when you're done | `mda delete` in `managed_agent/` (asks for confirmation) |

## Recap

- Agent Server primitives (assistants, threads, runs, crons, store) are the same for every LangSmith deployment.
- Sandboxes give the agent a real shell per thread, provisioned once by `setup.sh`.
- Code execution bypasses tool-level guards, so decide deliberately what data goes into the sandbox.
- Restrict egress with an allowlist and treat sandbox output as untrusted.
- Gate releases on Harbor evals: correctness, authorization, and grounding, scored from the agent's own output.
'''),
]

save("section_1_managed_deep_agents.ipynb", s1)
save("section_2_runtime_and_sandboxes.ipynb", s2)
