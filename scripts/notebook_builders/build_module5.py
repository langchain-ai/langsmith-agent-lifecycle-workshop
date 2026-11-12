"""Build Module 5 notebooks (Evals 201) for the TechHub workshop.

Usage (from the repo root):
    uv run python scripts/notebook_builders/build_module5.py workshop_modules/module_5
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


# ============================================================================
# SECTION 3: Harbor evals (see docs/2026-11-12-module-5-section-3-v2-plan.md)
# ============================================================================
s3 = [
    md('''
# Module 5, Section 3: Harbor Evals

**An environment eval runs the agent in a fresh sandbox and grades what the run left behind.**

It's the same loop you've used since Module 2:

<img src="../../images/offline_eval_process.png">

[Harbor](https://www.harborframework.com/docs) swaps each part:

<img src="../../images/harbor_eval_process.svg">

| Offline eval (Module 2) | Harbor | What changes |
|---|---|---|
| **Example**: inputs and reference outputs | **Task**: a folder with the instruction, the caller's identity, a Dockerfile, and `tests/` | Each test case brings its own machine and its own checks |
| **Application**: your function, in this process | **Sandbox**: a fresh machine running the real agent with its real setup | The agent runs the way it runs in production |
| **Run**: inputs and outputs | **Run state**: every message, tool call, and tool result (`result.json`) | The grader sees what happened, not only what was said |
| **Evaluator**: `f(inputs, outputs, reference)` | **Verifier**: `verify.py(result.json)` | Plain code over the evidence; the hidden truth lives in `tests/` |
| **Experiment results** | The same LangSmith experiment | One feedback score per check |

In this section:
1. **Vocabulary**: task, environment, verifier, trial, job, reward
2. **Why**: what only the run state can show
3. **Setup**
4. **Anatomy of a task**
5. **Run a job**, and read Harbor's summary
6. **Three outcomes**: failed, errored, invalid
7. **Design a task**: a refund must wait for human approval
8. **Trust the verifier**: known answers, locally and in the sandbox
9. **Run it, then break it**
10. **Read it in LangSmith**
11. **Where this goes**
'''),
    md('''
## 1. Vocabulary

| Harbor term | What it is | Here | In LangSmith |
|---|---|---|---|
| **Task** | One test case: instruction + environment + verifier, in one folder | `managed_agent/evals/<task>/` | A dataset example |
| **Environment** | The machine the agent runs in, built from the task's Dockerfile | A LangSmith sandbox (`--env langsmith`) | The `environment-start` step of a run |
| **Verifier** | Code that reads the run state and writes the scores | `tests/verify.py` | The `verification-start` step of a run |
| **Trial** | One agent attempt at one task | One sandbox, one agent run | A run in the experiment |
| **Job** | A batch of trials across tasks | One `harbor_run(...)` call | An experiment |
| **Reward** | The verifier's scores: `reward` plus one per check | `/logs/verifier/reward.json` | Feedback columns |
'''),
    md('''
## 2. Why: what only the run state can show

A dataset evaluator grades what the agent **said**. Some properties are about what the agent **did**:

- **Side effects**: did the refund actually go out?
- **Pauses**: did the run stop for human approval?
- **Data crossing customers**: did another customer's order show up anywhere, including in a subagent's messages the customer never sees?
- **The environment**: does it work with the compiled agent, its sandbox setup, and a signed-in caller?

The refund case shows the difference. `request_refund` is the agent's only tool that changes anything, and `interrupt_on={"request_refund": True}` makes the run stop for a person to approve it:

| | ✅ Correct: paused for approval | ❌ Broken: approval removed |
|---|---|---|
| **Reply text** | None: the run paused | "I've submitted a refund request..." |
| **LLM judge on the reply** | ❌ "No answer": fail | ✅ "Helpful and polite": pass |
| **Run state** (`result.json`) | human: refund please<br>ai: `request_refund(ORD-2024-0101)`<br>`__interrupt__` ⏸ | human: refund please<br>ai: `request_refund(ORD-2024-0101)`<br>**tool: `request_refund` → "Refund submitted"** 💸<br>ai: "I've submitted..." |
| **Verifier on the run state** | ✅ reward 1 | ❌ reward 0 |

The judge is wrong both times, and the verifier is right both times, because the broken run has a `request_refund` **tool result**: the tool ran. We build this task in §7.
'''),
    md('''
## 3. Setup

Harbor runs the managed agent from Module 6, through the MDA adapter. The adapter gives each trial a verified caller from the task's `identity.json`, the way a signed-in customer's token would. (For a plain Deep Agent with no identity, Harbor's built-in `--agent langgraph` does the same job; see [Harbor integrations](https://docs.langchain.com/langsmith/harbor-integrations).)

You need `uv`, `LANGSMITH_API_KEY`, and model access (a provider key, or `LANGSMITH_GATEWAY_API_KEY`; see the README). `--env langsmith` runs trials in LangSmith sandboxes, so you don't need Docker. The next cell prepares the managed agent's eval runner if it isn't ready yet.

The helpers in `utils/harbor_runs.py` wrap the command from `managed_agent/evals/README.md`, show a live progress panel, and read results back.
'''),
    code('''
import json
import os
import shutil
import subprocess
import sys
import tempfile
import warnings

from dotenv import load_dotenv
from langsmith import Client

load_dotenv()
warnings.filterwarnings("ignore", category=UserWarning)

from utils.harbor_runs import DATASET, PROJECT, harbor_run, harbor_summary, mda_runner_ready, results_table, uv_env

EVALS = PROJECT / "evals"

assert shutil.which("uv"), "Install uv: https://docs.astral.sh/uv/"
assert os.environ.get("LANGSMITH_API_KEY"), "Set LANGSMITH_API_KEY in .env"
model_keys = ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "LANGSMITH_GATEWAY_API_KEY", "LANGSMITH_API_KEY_GATEWAY", "LC_GATEWAY_KEY"]
assert any(os.environ.get(k) for k in model_keys), f"Set one of {model_keys} in .env (see the README)"

if not mda_runner_ready():
    for argv in (["uv", "sync", "--python", "3.14"], ["uv", "run", "mda", "evals", "init"]):
        print("$", " ".join(argv))
        subprocess.run(argv, cwd=PROJECT, env=uv_env(), check=True)
print("MDA eval runner ready:", mda_runner_ready())
'''),
    md('''
## 4. Anatomy of a task

```
order-status-own-order/
├── instruction.md     → the user's message
├── identity.json      → who is asking: signed-in customer CUST-003
├── task.toml          → timeouts, CPU and memory, env vars
├── environment/
│   └── Dockerfile     → the machine the agent runs in
├── tests/
│   ├── test.sh        → what Harbor runs after the agent stops
│   ├── verify.py      → the checks: plain Python, no LLM judge
│   └── mda_result.py  → shared helper: reads the run state, writes the scores
└── Task.md            → the spec, for people; the agent never sees it
```

The input and the verifier for one task:
'''),
    code('''
task = EVALS / "order-status-own-order"
print("--- instruction.md\\n" + (task / "instruction.md").read_text())
print("--- identity.json\\n" + (task / "identity.json").read_text())
print("--- tests/verify.py\\n" + (task / "tests/verify.py").read_text())
'''),
    md('''
`report()` prints each check and writes `reward.json`: the overall `reward` plus one score per check. `test.sh` deletes any reward file before `verify.py` runs, because the agent ran in the same machine and could have left one behind.
'''),
    md('''
## 5. Run a job

The managed agent ships with three tasks, each checking one property:

| Task | The customer asks | Passes when |
|---|---|---|
| `order-status-own-order` | About their own order | The answer says "Shipped" and gives the right tracking number (correctness) |
| `cross-customer-order-refused` | About another customer's order | Nothing from that order appears anywhere in the run (authorization) |
| `opened-item-return-window` | Whether an opened keyboard can be returned after 20 days | The answer cites the 14-day window and says no (grounding) |

One job runs all three as parallel trials, about 3 minutes:

```
harbor_run(EXISTING, ...)        one job
  │
  ├─ MDA plugin compiles managed_agent/agent.py once
  │
  ├─ trial: order-status     ┐
  ├─ trial: cross-customer   ├─ each in its own sandbox:
  └─ trial: opened-item      ┘    start machine → install agent → run instruction.md
                                  as identity.json → save result.json → verify.py → reward.json
  │
  └─ LangSmith plugin: one experiment, one run per trial, one feedback score per reward key
```
'''),
    code('''
EXISTING = ["order-status-own-order", "cross-customer-order-refused", "opened-item-return-window"]

job, experiment = harbor_run(EXISTING, "m5-existing-tasks")
'''),
    md('''
**Harbor's summary**, as `harbor run` prints it in a terminal. The first table has one column per reward key, each the **mean over trials** (names are cut to fit). The second counts trials by score for each key, without labels:
'''),
    code('''
harbor_summary(experiment)
'''),
    md('''
Read the means carefully. `Reward` is 1.000 because all three tasks passed. But each check column belongs to **one** task, and Harbor averages it over all three trials, so a check that passed shows **0.333**. Per task, read back from the LangSmith experiment:
'''),
    code('''
results_table(experiment)
'''),
    md('''
## 6. Three outcomes

A score of 0 doesn't always mean the agent failed:

| Outcome | What happened | Whose problem | How it shows |
|---|---|---|---|
| **Failed** | The verifier ran and a check failed | The agent (or the task measured the wrong thing) | `reward` 0, and the failing check is 0 |
| **Errored** | The sandbox, the runner, or a timeout failed before scoring | Infrastructure: fix it and rerun | `harbor_error` feedback (⚠️ in the panel and the table) |
| **Invalid** | The verifier found no evidence (no `result.json`) | Neither: rerun | `reward` 0 plus `invalid` 1 |

Count only **failed** trials against the agent.
'''),
    md('''
## 7. Design a task: a refund must wait for human approval

The task from §2. What should happen, and what a broken agent does:

```
Customer (CUST-003): "My LG monitor from ORD-2024-0101 died. Refund please."
        │
        ▼
   main agent ──► request_refund(order_id="ORD-2024-0101")
                        │
            ┌───────────┴───────────────┐
            ▼                           ▼
   approval check (interrupt_on)    no approval check (broken)
   ⏸ run pauses, tool does NOT run  💸 refund runs immediately
   no final answer                  "Yes — I've submitted a refund request..."
```

Design it spec-first, the way the [`eval-engineering` skill](https://github.com/langchain-ai/langchain-skills/blob/main/config/skills/eval-engineering/SKILL.md) recommends. The spec says what passes before any code exists, from facts in the database: `ORD-2024-0101` belongs to `CUST-003`, was delivered, and holds one LG 24" monitor.
'''),
    code('''
refund_task = EVALS / "refund-requires-approval"
print((refund_task / "Task.md").read_text())
'''),
    md('''
The input names the order and asks for a refund explicitly, so a correct agent always gets as far as requesting it. The caller is signed in as `CUST-003`:
'''),
    code('''
print("--- instruction.md\\n" + (refund_task / "instruction.md").read_text())
print("--- identity.json\\n" + (refund_task / "identity.json").read_text())
'''),
    md('''
### The verifier

Two checks, both on the run state:

```
result.json
   ├── R1: an ai message calls request_refund with order_id "ORD-2024-0101"
   │       (without this, an agent that refuses to help would pass)
   └── R2: no tool message named request_refund
           (a result means the tool ran: the pause didn't hold)

reward = 1 only if R1 and R2 both pass
```

> 💡 **Try it first:** write R1 and R2 yourself with `tool_calls(messages)` and `role_of(m)` from `mda_result.py`, then compare with the verifier below.
'''),
    code('''
print((refund_task / "tests/verify.py").read_text())
'''),
    md('''
## 8. Trust the verifier

A wrong verifier is worse than none: it reports pass, and nobody looks again. Before trusting its scores, check it against answers you already know.

| | Local fixtures | Oracle |
|---|---|---|
| What runs | `verify.py` on hand-made run states | Harbor's built-in `oracle` agent, which runs the task's `solution/solve.sh` instead of a model |
| Where | Your machine | A real sandbox, through `test.sh` |
| Checks | The verifier's logic, good and bad cases | The whole task: Dockerfile, `test.sh`, verifier |
| Cost | About a second | About 10 seconds, no model calls |

**Local fixtures.** The verifier reads its paths from environment variables, so it runs here as-is. One known-good state and one known-bad:
'''),
    code('''
QUESTION = {"type": "human", "content": (refund_task / "instruction.md").read_text()}
REFUND_CALL = {"type": "ai", "content": "", "tool_calls": [{"name": "request_refund", "args": {"order_id": "ORD-2024-0101"}, "id": "call_1"}]}
FIXTURES = {
    "paused for approval (expect pass)": {"messages": [QUESTION, REFUND_CALL], "__interrupt__": [{"value": "approve?"}]},
    "refund ran (expect fail)": {"messages": [
        QUESTION, REFUND_CALL,
        {"type": "tool", "name": "request_refund", "content": "Refund request REF-1 submitted"},
        {"type": "ai", "content": "I've submitted your refund request."},
    ]},
}

for outcome, state in FIXTURES.items():
    with tempfile.TemporaryDirectory() as tmp:
        result = os.path.join(tmp, "result.json")
        with open(result, "w") as f:
            json.dump(state, f)
        env = {**os.environ, "MDA_EVAL_RESULT": result, "MDA_EVAL_INVALID": os.path.join(tmp, "invalid.txt"), "MDA_EVAL_REWARD": os.path.join(tmp, "reward.json")}
        run = subprocess.run([sys.executable, str(refund_task / "tests/verify.py")], env=env, capture_output=True, text=True)
    print(f"▶ {outcome}\\n{run.stdout}")
'''),
    md('''
**The oracle.** `solution/solve.sh` writes the run state a correct agent leaves behind. If the oracle doesn't score 1, the task itself is broken, before any model is involved:
'''),
    code('''
print((refund_task / "solution/solve.sh").read_text())

job, oracle_experiment = harbor_run(["refund-requires-approval"], "m5-refund-oracle", agent="oracle")
harbor_summary(oracle_experiment)
'''),
    md('''
## 9. Run it, then break it

Now the real agent, about 2 minutes. Expect reward 1 and **no final answer**: the run paused for approval.
'''),
    code('''
job, approval_experiment = harbor_run(["refund-requires-approval"], "m5-refund-approval")
results_table(approval_experiment)
'''),
    md('''
A task that has never failed hasn't shown it can catch anything. Remove the approval step from `agent.py`, the way a careless refactor might, and run again. The cell restores `agent.py` when the run ends, even if it fails.
'''),
    code('''
agent_py = PROJECT / "agent.py"
original = agent_py.read_text()
APPROVAL = 'interrupt_on={"request_refund": True},'
assert original.count(APPROVAL) == 1, "agent.py changed: find the interrupt_on line by hand"

agent_py.write_text(original.replace(APPROVAL, "interrupt_on={},"))
try:
    job, no_approval_experiment = harbor_run(["refund-requires-approval"], "m5-refund-no-approval")
finally:
    agent_py.write_text(original)
assert agent_py.read_text() == original
print("agent.py restored\\n")
results_table(no_approval_experiment)
'''),
    md('''
| | Approval on | Approval removed |
|---|---|---|
| `requested_a_refund_for_ord_2024_0101` | ✅ 1 | ✅ 1 |
| `refund_never_ran_without_approval` | ✅ 1 | ❌ **0**: the regression |
| `reward` | ✅ 1 | ❌ 0 |
| Final answer | None: paused | "Yes — I've submitted a refund request..." |

The per-check scores say exactly what broke. When a task fails, decide which side is wrong: if it measured the wrong thing, fix the task; if it caught a real problem, fix the agent.

If you see `harbor_error` instead (for example, "Agent setup timed out"), the sandbox failed before the agent ran: that's the **errored** outcome from §6, not a result. Rerun the cell.
'''),
    md('''
## 10. Read it in LangSmith

```
Harbor                              LangSmith
──────                              ─────────
evals/ (the tasks)           ──►    dataset   m5-harbor-techhub-support
  each task                  ──►      example
harbor_run(...) (a job)      ──►    experiment
  each trial                 ──►      run, with steps environment-start,
                                      agent-start, verification-start
  reward.json keys           ──►        feedback columns
  trial crashed              ──►        harbor_error feedback
```

Compare the approved and broken runs: open the link, select the `refund-requires-approval` example, and look at the feedback columns.
'''),
    code('''
client = Client()
dataset = client.read_dataset(dataset_name=DATASET)
compare = [client.read_project(project_name=name) for name in (approval_experiment, no_approval_experiment)]
print("📊 Dataset:", dataset.url)
print("📊 Compare:", f"{dataset.url}/compare?selectedSessions={','.join(str(e.id) for e in compare)}")
'''),
    md('''
> ⚠️ For managed agent runs, Harbor doesn't record token counts or cost yet (`tokens` and `cost_usd` are empty on each run).

## 11. Where this goes

**From evaluation to training.** A verifier's reward is a training signal too. The same tasks can drive reinforcement learning or rejection-sampled fine-tuning, and Harbor records every trial's full trajectory. Per-check scores give partial credit, and many task variations stop a model from memorizing one answer.

**Harbor tasks or dataset evaluators?**

```
                    What are you checking?
                            │
       ┌────────────────────┴────────────────────┐
       ▼                                         ▼
 How good is the answer?               Did something happen (or not)?
 (correct, complete, grounded)         (side effect, approval pause, data
       │                                crossing customers, the real setup)
       ▼                                         ▼
 Dataset evaluator                       Harbor task
 many examples, seconds each             a few tasks, minutes each
       └──────────────────┬──────────────────────┘
                          ▼
         run both before release: dataset evals show whether quality
         moved; Harbor tasks block a release that breaks what must never break
```

## Recap

- An environment eval runs the agent in a fresh sandbox and grades the run state, not just the reply.
- A task is a folder: instruction, identity, environment, and a verifier that is plain code.
- One score per check makes a failure explain itself. Failed, errored, and invalid are different outcomes.
- Write the spec first, then trust the verifier only after it passes known answers: local fixtures, then the oracle.
- Break the agent on purpose once. A task that has never failed hasn't shown it can catch anything.
'''),
]

save("section_3_harbor_evals.ipynb", s3)
