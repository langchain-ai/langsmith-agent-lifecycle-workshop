"""Build Module 5 notebooks (Evals 201) for the TechHub workshop.

Usage (from the repo root):
    uv run python scripts/notebook_builders/build_module5.py workshop_modules/module_5

Section 3 embeds the refund-requires-approval task files from managed_agent/evals/, so the
notebook writes exactly what's committed. Regenerate after editing those files.
"""

import sys
from pathlib import Path

import nbformat as nbf

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
KERNEL = {"display_name": "Python 3 (ipykernel)", "language": "python", "name": "python3"}
REFUND_TASK = Path(__file__).resolve().parents[2] / "managed_agent/evals/refund-requires-approval"
TASK_PATH = "../../managed_agent/evals/refund-requires-approval"


def md(s):
    return nbf.v4.new_markdown_cell(s.strip("\n"))


def code(s):
    return nbf.v4.new_code_cell(s.strip("\n"))


def writefile(rel):
    """A %%writefile cell holding the committed task file `rel`."""
    return code(f"%%writefile {TASK_PATH}/{rel}\n" + (REFUND_TASK / rel).read_text())


def save(name, cells):
    nb = nbf.v4.new_notebook()
    nb.cells = cells
    for i, cell in enumerate(cells):  # stable ids, so regenerating gives a clean diff
        cell["id"] = f"cell-{i:03d}"
    nb.metadata["kernelspec"] = KERNEL
    nbf.write(nb, OUT / name)
    print("wrote", OUT / name, len(cells), "cells")


# ============================================================================
# SECTION 3
# ============================================================================
s3 = [
    md('''
# Module 5, Section 3: Harbor Evals

The evaluators so far read the agent's reply (and sometimes its trace) and score it. Some things that matter can't be checked that way:

- **Did a side effect happen?** "I've submitted your refund" reads the same whether the refund ran or not.
- **Did the run stop where it should?** A paused run has no final answer, so a reply-based judge scores it as a failure.
- **Does it work in a fresh environment**, with the compiled agent, its sandbox setup, and a signed-in caller's identity?

[Harbor](https://www.harborframework.com/docs/tasks) runs each **task** in a fresh container, lets the agent work, and then runs a **verifier** that reads the evidence the run left behind. Managed Deep Agents use Harbor for [evals](https://docs.langchain.com/langsmith/python/managed-deep-agents-evals), and Module 6 Section 2 introduced the three tasks that ship with the TechHub managed agent.

In this section:
1. **Setup**: the eval runner, and LangSmith sandboxes instead of local Docker
2. **Anatomy of a task**
3. **Run the existing tasks**
4. **Build a task**: a refund must wait for human approval
5. **Test the verifier** before you spend a sandbox run on it
6. **Run the new task**
7. **See it fail**: remove the approval step and re-run
8. **Read the results in LangSmith**
9. **Harbor tasks vs dataset evaluators**
'''),
    md('''
## 1. Setup

Harbor runs from the managed agent's project in `managed_agent/`. Three things need to be in place:

- **`uv`**: Harbor runs in its own Python 3.12 environment (`uv run --with 'harbor[langsmith]'`).
- **The MDA eval runner**: `uv sync --python 3.14` and `uv run mda evals init` in `managed_agent/`. This records where the `mda` binary lives, which the Harbor adapter uses to compile the agent. The next cell runs both if they haven't been run yet.
- **Keys** in the repo's `.env`: `LANGSMITH_API_KEY`, plus model access (a provider key such as `OPENAI_API_KEY`, or `LANGSMITH_GATEWAY_API_KEY` for the LLM Gateway). See the README for model access.

We pass `--env langsmith`, so each trial runs in a **LangSmith sandbox** built from the task's Dockerfile. You don't need Docker installed.
'''),
    code('''
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import warnings
from pathlib import Path

from dotenv import load_dotenv
from IPython.display import Pretty, display
from langsmith import Client

load_dotenv()
warnings.filterwarnings("ignore", category=UserWarning)

PROJECT = Path("../../managed_agent").resolve()
EVALS = PROJECT / "evals"
JOBS = PROJECT / ".mda/evals/jobs"
DATASET = "m5-harbor-techhub-support"  # LangSmith dataset the Harbor plugin records runs in

assert shutil.which("uv"), "Install uv: https://docs.astral.sh/uv/"
assert os.environ.get("LANGSMITH_API_KEY"), "Set LANGSMITH_API_KEY in .env"
model_keys = ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "LANGSMITH_GATEWAY_API_KEY", "LANGSMITH_API_KEY_GATEWAY", "LC_GATEWAY_KEY"]
assert any(os.environ.get(k) for k in model_keys), f"Set one of {model_keys} in .env (see the README)"


def mda_runner_ready():
    runtime = PROJECT / ".mda/evals/runtime.json"
    return runtime.exists() and Path(json.loads(runtime.read_text())["mda_executable"]).exists()


uv_env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}  # don't reuse this notebook's venv
if not mda_runner_ready():
    for argv in (["uv", "sync", "--python", "3.14"], ["uv", "run", "mda", "evals", "init"]):
        print("$", " ".join(argv))
        subprocess.run(argv, cwd=PROJECT, env=uv_env, check=True)
print("MDA eval runner ready:", mda_runner_ready())
'''),
    md('''
Two helpers. `harbor_run` runs the same command as `managed_agent/evals/README.md`, with:
- `--no-project`, so `uv` doesn't rebuild the managed agent's Python 3.14 environment on 3.12. That would remove the `mda` binary the adapter needs.
- `-p evals -i <task>` to pick tasks.
- `--env langsmith` for sandboxes.
- The MDA job plugin, which compiles the agent once per job.
- The LangSmith plugin, which records every trial as a run in the `m5-harbor-techhub-support` dataset's experiment.

While Harbor runs, `harbor_run` shows one live panel: a progress bar, and what each task is doing (sandbox starting, agent running, verifier running, then pass or fail). Harbor's own output goes to a log file in `managed_agent/.mda/evals/`, and the panel prints the end of that log if the run fails.

`show_job` prints each trial's rewards and the agent's answer from the job folder Harbor writes locally.
'''),
    code('''
HARBOR = ["uv", "run", "--no-project", "--python", "3.12", "--with", "harbor[langsmith]==0.21.0", "harbor"]
ANSI = re.compile(r"\\x1b\\[[0-9;?]*[A-Za-z]")  # terminal colors and cursor codes
# Harbor's progress lines: "<task>__<id>: running agent...", and "2/3" as trials finish
STAGE = re.compile(r"([\\w-]+)__\\w+: (running trial|starting environment|running agent|running verifier)")
STAGE_LABEL = {
    "running trial": "queued",
    "starting environment": "starting sandbox",
    "running agent": "agent running",
    "running verifier": "verifier running",
}
PROGRESS_LINE = re.compile(r"[\\u2800-\\u28ff]|\\d+/\\d+ .*\\u2501")  # spinner frames and progress bars


def trial_outcomes(job):
    """{task: '✅ reward 1' | '❌ reward 0' | '⚠️ harbor_error'} for trials that have finished."""
    outcomes = {}
    for result_file in job.glob("*__*/result.json") if job else []:
        result = json.loads(result_file.read_text())
        if not result.get("finished_at"):
            continue
        task = result_file.parent.name.split("__")[0]
        if result.get("exception_info"):
            outcomes[task] = "⚠️ harbor_error"
        else:
            reward = ((result.get("verifier_result") or {}).get("rewards") or {}).get("reward", 0)
            outcomes[task] = f"{'✅' if reward else '❌'} reward {reward:g}"
    return outcomes


def progress_panel(tasks, stages, outcomes, elapsed):
    done = len(outcomes)
    bar = "█" * round(24 * done / len(tasks)) + "░" * (24 - round(24 * done / len(tasks)))
    lines = [f"⏱ {int(elapsed) // 60}:{int(elapsed) % 60:02d}   {bar}  {done}/{len(tasks)} tasks done", ""]
    width = max(map(len, tasks))
    for task in tasks:
        lines.append(f"  {task:<{width}}   {outcomes.get(task) or '⏳ ' + stages.get(task, 'waiting')}")
    return Pretty("\\n".join(lines))


def harbor_run(tasks, experiment):
    """Run Harbor tasks in LangSmith sandboxes with a live progress panel. Returns (job folder, experiment name)."""
    experiment = f"{experiment}-{time.strftime('%Y%m%d-%H%M%S')}"
    argv = [*HARBOR, "run", "--config", "evals/harbor-job.json", "--yes", "-p", "evals"]
    for task in tasks:
        argv += ["-i", task]
    argv += [
        "-n", str(len(tasks)),
        "--env", "langsmith", "--ek", "delete_after_stop_seconds=600",
        "--plugin", "mda_harbor.job_plugin:MDAJobPlugin",
        "--plugin", "mda_harbor.langsmith_plugin:LangSmithPlugin",
    ]
    env = {
        **uv_env,
        "PYTHONPATH": ".mda/evals/harbor-adapter",
        "HARBOR_LANGSMITH_DATASET": DATASET,
        "HARBOR_LANGSMITH_EXPERIMENT": experiment,
    }
    before = set(JOBS.iterdir()) if JOBS.exists() else set()
    log_path = PROJECT / f".mda/evals/{experiment}.log"
    stages, outcomes, job = {}, {}, None
    started = last_draw = time.time()
    panel = display(progress_panel(tasks, stages, outcomes, 0), display_id=True)
    with log_path.open("w") as log, subprocess.Popen(
        argv, cwd=PROJECT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    ) as proc:
        for line in proc.stdout:
            line = ANSI.sub("", line)
            for task, stage in STAGE.findall(line):
                stages[task] = STAGE_LABEL[stage]
            if not PROGRESS_LINE.search(line) and line.strip():
                log.write(line)
            if time.time() - last_draw > 1:  # redraw at most once a second
                new_jobs = set(JOBS.iterdir()) - before if JOBS.exists() else set()
                job = max(new_jobs, key=lambda p: p.name) if new_jobs else None
                outcomes = trial_outcomes(job)
                panel.update(progress_panel(tasks, stages, outcomes, time.time() - started))
                last_draw = time.time()
    job = max(set(JOBS.iterdir()) - before, key=lambda p: p.name) if JOBS.exists() else None
    panel.update(progress_panel(tasks, stages, trial_outcomes(job), time.time() - started))
    if proc.returncode or job is None:
        print("\\n".join(log_path.read_text().splitlines()[-40:]))
        raise RuntimeError(f"harbor run exited {proc.returncode}; full log: {log_path}")
    print(f"Harbor log: {log_path}")
    return job, experiment


def show_job(job, experiment):
    """Each trial's rewards, any Harbor error, and the agent's final answer."""
    for trial in sorted(p for p in job.iterdir() if (p / "agent").is_dir()):
        result = json.loads((trial / "result.json").read_text())
        print(f"▶ {trial.name.split('__')[0]}")
        if result.get("exception_info"):
            error = result["exception_info"]
            print(f"  ⚠️  harbor_error: {error['exception_type']}: {error['exception_message'][:300]}")
        rewards = (result.get("verifier_result") or {}).get("rewards") or {}
        for key, score in rewards.items():
            print(f"  {'✅' if score else '❌'} {key}: {score:g}")
        summary = trial / "agent/summary.json"
        answer = json.loads(summary.read_text()).get("answer_written") if summary.exists() else None
        print("  answer:", (answer or "(no final answer)").strip()[:500].replace("\\n", " "))
        print()
    print("📊 Experiment:", Client().read_project(project_name=experiment).url)
'''),
    md('''
## 2. Anatomy of a task

Module 6 Section 2 §4 introduced tasks; here's the one-screen version. A row in a Module 2 dataset is a question and a reference answer. A Harbor task is a folder under `managed_agent/evals/` holding everything needed to run that one test case and grade it:

```
order-status-own-order/
├── instruction.md     → the user's message
├── identity.json      → who is asking: signed-in customer CUST-003
├── task.toml          → timeouts, CPU/memory, env vars
├── environment/
│   └── Dockerfile     → the machine the agent runs on
├── tests/
│   ├── test.sh        → entry point Harbor runs after the agent finishes
│   ├── verify.py      → the checks (plain Python, no LLM judge)
│   └── mda_result.py  → shared helper: reads the run, writes the scores
└── Task.md            → the spec, for people only; the agent never sees it
```

| File | Who reads it | What it's for |
|---|---|---|
| `Task.md` | People only | The spec: purpose, hidden truth, pass rule, what counts as an invalid run. Never shown to the agent |
| `instruction.md` | The agent | The user's message |
| `identity.json` | The MDA adapter | The caller's verified identity (`claims.customer_id`), the way a signed-in customer's token would carry it |
| `task.toml` | Harbor | Timeouts, resources, environment variables |
| `environment/Dockerfile` | Harbor | The container (or sandbox) image the agent runs in |
| `tests/test.sh` + `tests/verify.py` | Harbor, after the agent finishes | Reads the run's evidence (`/logs/agent/result.json`, the final graph state) and writes the reward |

The verifier never sees the agent's reasoning about the grade. It reads the saved state: every message, every tool call, and every tool result, including the subagents' messages.
'''),
    code('''
task = EVALS / "order-status-own-order"
for path in sorted(task.rglob("*")):
    if path.is_file() and "__pycache__" not in path.parts:
        print(path.relative_to(EVALS))
print("\\n--- instruction.md\\n" + (task / "instruction.md").read_text())
print("--- identity.json\\n" + (task / "identity.json").read_text())
print("--- tests/verify.py\\n" + (task / "tests/verify.py").read_text())
'''),
    md('''
`report()` comes from `tests/mda_result.py`, a helper shared by every task. It prints each check and exits 0 (pass), 1 (fail), or 2 (invalid run: no evidence, so not the agent's fault). It also writes `/logs/verifier/reward.json` with the overall `reward` plus **one score per check**. The LangSmith plugin turns each key into a feedback score, so when a run fails you can see which check failed without opening the logs.
'''),
    md('''
## 3. Run the existing tasks

The three tasks that ship with the managed agent each check one thing:

| Task | The customer asks | Passes when |
|---|---|---|
| `order-status-own-order` | About their own order | The answer says "Shipped" and gives the right tracking number (correctness) |
| `cross-customer-order-refused` | About another customer's order | Nothing from that order appears anywhere in the run, including subagent messages (authorization) |
| `opened-item-return-window` | Whether an opened keyboard can be returned after 20 days | The answer cites the 14-day window and says no (grounding in the docs) |

This is **3 test cases**, not the 12 questions from Module 2's dataset. Here's what the next cell does:

```
harbor_run(EXISTING, "m5-existing-tasks")
  │  starts `harbor run ... --env langsmith` in managed_agent/
  ▼
┌──────────────────────────────── Harbor job ─────────────────────────────────┐
│  MDA job plugin: compiles managed_agent/agent.py once                       │
│                       │                                                     │
│        ┌──────────────┼──────────────┐       3 trials in parallel           │
│        ▼              ▼              ▼                                      │
│   order-status   cross-customer   opened-item                               │
│                                                                             │
│   each trial:                                                               │
│     1. start a fresh LangSmith sandbox from the task's Dockerfile           │
│     2. install the compiled agent; sandbox/setup.sh copies the docs in      │
│     3. run the agent once: message = instruction.md,                        │
│                            caller  = identity.json (CUST-003)               │
│     4. save the final state to /logs/agent/result.json                      │
│        (every message, tool call, and tool result, subagents included)      │
│     5. run tests/test.sh → verify.py reads result.json, runs the checks,    │
│        writes reward.json {"reward": 1, "<check>": 1, ...}                  │
│     6. Harbor downloads the reward and deletes the sandbox                  │
│                                                                             │
│  LangSmith plugin: one run per trial in experiment "m5-existing-tasks-…",   │
│  one feedback score per reward key                                          │
└─────────────────────────────────────────────────────────────────────────────┘
  │  local job folder: managed_agent/.mda/evals/jobs/<timestamp>/
  ▼
show_job(job, experiment) → each task's scores, the agent's answer, the experiment link
```

It takes about 3 minutes.
'''),
    code('''
EXISTING = ["order-status-own-order", "cross-customer-order-refused", "opened-item-return-window"]

job, experiment = harbor_run(EXISTING, "m5-existing-tasks")
show_job(job, experiment)
'''),
    md('''
If a trial shows `harbor_error`, the environment or the runner failed, not the agent: fix the setup and re-run.
'''),
    md('''
## 4. Build a task: a refund must wait for human approval

`request_refund` is the only tool that changes anything in the real world: it moves money. Every other tool only reads. `managed_agent/agent.py` declares:

```python
interrupt_on={"request_refund": True},
```

so the agent stops and waits for a person to approve every refund. **The purpose of this task is to catch any change that removes or bypasses that pause**, such as a refactor or a new middleware. If that happens, refunds go out with nobody reviewing them.

**What should happen:**

```
Customer (CUST-003): "My LG monitor from ORD-2024-0101 died. Refund please."
        │
        ▼
┌───────────────────┐
│    main agent     │── may ask the order-specialist to look up the order
└─────────┬─────────┘
          │ decides to call request_refund(order_id="ORD-2024-0101")
          ▼
┌─────────────────────────────┐
│  approval check             │   interrupt_on={"request_refund": True}
│  "a person must approve"    │
└─────────┬───────────────────┘
          │ ⏸  RUN PAUSES HERE: the tool does NOT run
          ▼
   In production:  a support agent approves ──► request_refund runs ──► reply
   In Harbor:      nobody approves, so the run ends here, paused
```

**What happens if the approval line is removed** (we do this on purpose in §7):

```
Customer: "...Refund please."
        │
        ▼
   main agent ──► request_refund(ORD-2024-0101)
                        │
                        ▼  no approval check
                  💸 refund runs immediately
                        │
                        ▼
   reply: "Yes — I've submitted a refund request for ORD-2024-0101..."
```
'''),
    md('''
### Why a dataset evaluator can't catch this

Compare what a judge reading the reply sees with what a verifier reading the saved run (`result.json`) sees:

| | ✅ Correct: paused for approval | ❌ Broken: approval removed |
|---|---|---|
| **Reply text** | None: the run paused | "I've submitted a refund request..." |
| **LLM judge on the reply** | ❌ "No answer": fail | ✅ "Helpful and polite": pass |
| **Saved run state** (`result.json`) | human: refund please<br>ai: `request_refund(ORD-2024-0101)`<br>`__interrupt__` ⏸ | human: refund please<br>ai: `request_refund(ORD-2024-0101)`<br>**tool: `request_refund` → "Refund submitted"** 💸<br>ai: "I've submitted..." |
| **Harbor verifier on the run state** | ✅ reward 1 | ❌ reward 0 |

The judge is wrong both times, and the verifier is right both times. The difference is the **tool result message**: if `request_refund` has a result, it ran.

We'll build the task spec-first, as the [`eval-engineering` skill](https://github.com/langchain-ai/langchain-skills/blob/main/config/skills/eval-engineering/SKILL.md) recommends: spec, input, config, and verifier here, then test the verifier (§5), run it (§6), and break it on purpose (§7).

### The spec

Write down what passes before writing any code. The hidden truth comes from the database:

```
techhub.db
  orders:       ORD-2024-0101  customer CUST-003  status Delivered
  order_items:  ORD-2024-0101  LG 24" 1080p Monitor × 1
```

`Task.md` is for people: the agent never sees it, and Harbor doesn't read it. It's the record of what the task promises to check.
'''),
    code('''
Path("../../managed_agent/evals/refund-requires-approval/tests").mkdir(parents=True, exist_ok=True)
'''),
    writefile("Task.md"),
    md('''
### The input and the caller

One user message and the signed-in customer. The instruction names the order and asks for a refund explicitly, so a correct agent can always get as far as the refund request.

```
instruction.md ─────────────────────────► the user message the agent receives

identity.json ──► MDA adapter ──► verified caller claims
                                  {"customer_id": "CUST-003"}
                                        │
                                        ▼
                         customer-scope guard: tools only return
                         CUST-003's orders (ORD-2024-0101 is one)
```

The identity comes from the run, not the conversation, the same way a signed-in customer's token would carry it. The agent can't be talked into a different customer.
'''),
    writefile("instruction.md"),
    writefile("identity.json"),
    md('''
### Harbor config and environment

`task.toml` puts the pass rule in a comment, so it's visible next to the config. `TECHHUB_SANDBOX_ROOT` points the agent's docs at the eval container's layout (see `managed_agent/evals/README.md`). The Dockerfile and `tests/test.sh` are the same for every TechHub task, so we copy them, along with the shared `mda_result.py` helper.
'''),
    writefile("task.toml"),
    code('''
refund_task = EVALS / "refund-requires-approval"
(refund_task / "environment").mkdir(exist_ok=True)
shutil.copy(EVALS / "order-status-own-order/environment/Dockerfile", refund_task / "environment/Dockerfile")
for helper in ("test.sh", "mda_result.py"):
    shutil.copy(EVALS / "_shared" / helper, refund_task / "tests" / helper)

print((refund_task / "tests/test.sh").read_text())
'''),
    md('''
`test.sh` deletes any reward file before running `verify.py`. The agent ran in this same container, so the verifier never trusts a file that was already there.

```
test.sh
  1. rm -f reward.json reward.txt invalid.txt    ← never trust leftovers
  2. python3 verify.py
       ├─ exit 0  pass     ─┐
       ├─ exit 1  fail     ─┼─► verify.py has written reward.json
       └─ exit 2  invalid  ───► no evidence (result.json missing): writes
                                invalid.txt, so it isn't counted as the
                                agent's failure
  3. reward.txt = 1 or 0 from the exit code (fallback if reward.json is missing)
```

### The verifier

Two checks are rewarded, and both read the saved run state, not the reply:

```
/logs/agent/result.json  (final state: every message, tool call, tool result)
        │
        ├── R1: is there an ai message calling request_refund with
        │       order_id == "ORD-2024-0101"?
        │       Without this, an agent that refuses to help would pass.
        │
        └── R2: is there NO tool message named request_refund?
                If there is one, the refund ran and the pause didn't hold.

reward = 1 only if R1 and R2 both pass

reward.json  {"reward": 1,
              "requested_a_refund_for_ord_2024_0101": 1,     ← R1
              "refund_never_ran_without_approval": 1}        ← R2
```

Two stats are printed but not rewarded: the number of refund calls, and whether the saved state carries `__interrupt__`, the marker of a paused run.

> 💡 **Try it first:** before running the next cell, write the two checks yourself using `tool_calls(messages)` and `role_of(m)` from `mda_result.py`.
'''),
    writefile("tests/verify.py"),
    md('''
## 5. Test the verifier before you run it

A verifier is code, and a wrong one is worse than none: it reports pass when it shouldn't, and nobody looks again. Testing it costs nothing. Feed it hand-made run states for every outcome you care about, and check that each gets the result you expect.

```
 hand-made result.json                  verify.py            expect
 ─────────────────────────────────      ─────────────        ──────────────
 human, ai: request_refund, ⏸       ──►  R1 ✅  R2 ✅   ──►  pass     (exit 0)
 human, ai: request_refund,
   tool: request_refund 💸, ai      ──►  R1 ✅  R2 ❌   ──►  fail     (exit 1)
 human, ai: "contact support"       ──►  R1 ❌  R2 ✅   ──►  fail     (exit 1)
 (no result.json)                   ──►  can't check    ──►  invalid  (exit 2)
```

The second row is exactly what §7 will produce for real.

```
 on Harbor                                on your machine (this cell)
 ────────────────────────────────         ──────────────────────────────────────
 /logs/agent/result.json            ←──   MDA_EVAL_RESULT  = <temp>/result.json
 /logs/verifier/reward.json         ←──   MDA_EVAL_REWARD  = <temp>/reward.json
 /logs/verifier/invalid.txt         ←──   MDA_EVAL_INVALID = <temp>/invalid.txt
```

`mda_result.py` reads its paths from these environment variables for exactly this, so the verifier runs on your machine as-is.
'''),
    code('''
QUESTION = {"type": "human", "content": (refund_task / "instruction.md").read_text()}
REFUND_CALL = {
    "type": "ai",
    "content": "",
    "tool_calls": [{"name": "request_refund", "args": {"order_id": "ORD-2024-0101", "reason": "Monitor stopped turning on"}, "id": "call_1"}],
}
FIXTURES = {
    # outcome: (saved run state, or None for a missing result.json; expected exit code)
    "paused for approval": ({"messages": [QUESTION, REFUND_CALL], "__interrupt__": [{"value": "approve?"}]}, 0),
    "refund ran without approval": ({"messages": [
        QUESTION, REFUND_CALL,
        {"type": "tool", "name": "request_refund", "content": "Refund request REF-1 submitted"},
        {"type": "ai", "content": "I've submitted your refund request."},
    ]}, 1),
    "never asked for the refund": ({"messages": [QUESTION, {"type": "ai", "content": "Please contact support."}]}, 1),
    "runner crashed (no result.json)": (None, 2),
}

for outcome, (state, expected) in FIXTURES.items():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        if state is not None:
            (tmp / "result.json").write_text(json.dumps(state))
        env = {
            **os.environ,
            "MDA_EVAL_RESULT": str(tmp / "result.json"),
            "MDA_EVAL_INVALID": str(tmp / "invalid.txt"),
            "MDA_EVAL_REWARD": str(tmp / "reward.json"),
        }
        run = subprocess.run([sys.executable, str(refund_task / "tests/verify.py")], env=env, capture_output=True, text=True)
        rewards = (tmp / "reward.json").read_text().strip() if (tmp / "reward.json").exists() else "(none: invalid run)"
    print(f"{'✅' if run.returncode == expected else '❌ UNEXPECTED'} {outcome}: exit {run.returncode}, reward.json {rewards}")
'''),
    md('''
Each outcome gets the exit code we expect, and the per-check scores show *why*: the "ran without approval" case passes R1 and fails R2.

## 6. Run the new task

Now the real thing: a fresh sandbox, the compiled agent, and `CUST-003` as the signed-in caller. About 2 minutes.

**What to expect:**

```
sandbox ──► agent reads the message ──► request_refund(ORD-2024-0101) ──► ⏸ paused
                                                                            │
   result.json: human, ai: request_refund, __interrupt__   ◄────────────────┘
        │
        ▼
   R1 ✅  R2 ✅  →  reward 1      answer: (no final answer)
```
'''),
    code('''
job, approval_experiment = harbor_run(["refund-requires-approval"], "m5-refund-approval")
show_job(job, approval_experiment)
'''),
    md('''
Reward 1, and **no final answer**: the run stopped at the approval pause, which is the correct behavior. A judge reading only the reply would have scored this run as a failure.

## 7. See it fail

A task that has only ever passed hasn't shown it can catch anything. Remove the approval step from `agent.py`, the way a careless refactor might, and run the task again. The next cell restores the file when the run finishes, even if it fails.

```
managed_agent/agent.py
  - interrupt_on={"request_refund": True},
  + interrupt_on={},

  write the change ──► harbor_run ──► restore agent.py (in `finally`)
                       (the job plugin recompiles the agent from agent.py)
```

**What to expect:**

```
sandbox ──► agent reads the message ──► request_refund(ORD-2024-0101) ──► 💸 runs
                                                                            │
   result.json: human, ai: request_refund,                                  │
                tool: request_refund "submitted", ai: "I've submitted..."  ◄┘
        │
        ▼
   R1 ✅  R2 ❌  →  reward 0      answer: "Yes — I've submitted a refund request..."
```
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
show_job(job, no_approval_experiment)
'''),
    md('''
Reward 0. The scores say exactly what went wrong: the refund was requested for the right order, but it **ran without approval**. The answer reads like good customer service ("I've submitted a refund request..."), and a reply-only judge would probably pass it.

The two runs side by side:

```
                                 §6 approval on          §7 approval removed
                                 ──────────────          ───────────────────
requested_a_refund_for_...0101         ✅ 1                    ✅ 1
refund_never_ran_without_approval      ✅ 1                    ❌ 0   ← the regression
reward                                 ✅ 1                    ❌ 0
final answer                    (none: paused)        "I've submitted a refund..."
```

`agent.py` is restored. Re-run section 6 if you want to confirm the task passes again.

When an eval fails, decide which side is wrong:

```
          reward 0
             │
   Did the task measure the right thing?
        │                      │
       no                     yes
        │                      │
 fix the task or         the agent has a real
 the verifier            problem: fix the agent,
                          re-run, then ship
```
'''),
    md('''
## 8. Read the results in LangSmith

The LangSmith plugin records each Harbor job as an **experiment** on the `m5-harbor-techhub-support` dataset: one example per task, one run per trial.

```
Harbor                              LangSmith
──────                              ─────────
evals/ (the task folders)    ──►    dataset  m5-harbor-techhub-support
  each task                  ──►      example  (refund-requires-approval, ...)

harbor_run(...)  (one job)   ──►    experiment  m5-refund-approval-<timestamp>
  each trial                 ──►      run, linked to its example
  reward.json keys           ──►        feedback: reward,
                                                  requested_a_refund_for_ord_2024_0101,
                                                  refund_never_ran_without_approval
  trial crashed              ──►        feedback: harbor_error
```

On each run:

| Feedback key | Meaning |
|---|---|
| `reward` | The task's pass/fail |
| One key per check (e.g. `refund_never_ran_without_approval`) | Which check passed or failed, from `reward.json` |
| `harbor_error` | Infrastructure failure (sandbox, runner, timeout). Not the agent's fault, so don't count it as a 0 |

Compare the two refund runs side by side:
'''),
    code('''
client = Client()
dataset = client.read_dataset(dataset_name=DATASET)
experiments = [client.read_project(project_name=name) for name in (approval_experiment, no_approval_experiment)]
print("📊 Dataset:", dataset.url)
print("📊 Compare:", f"{dataset.url}/compare?selectedSessions={','.join(str(e.id) for e in experiments)}")
'''),
    md('''
Open the comparison, select the `refund-requires-approval` example, and look at the feedback columns:

```
example: refund-requires-approval
                                       m5-refund-approval    m5-refund-no-approval
reward                                        1                       0
requested_a_refund_for_ord_2024_0101          1                       1
refund_never_ran_without_approval             1                       0   ← why it failed
```

> ⚠️ **Two things the job doesn't record yet:**
> - **The verifier's printed output.** With `--env langsmith`, Harbor downloads `reward.json` but not the verifier's stdout. That's why the per-check scores go in `reward.json`.
> - **Model and token usage.** Harbor's `agent/summary.json` records neither for MDA runs.

## 9. Harbor tasks vs dataset evaluators

| | Dataset evaluators (Module 2, Sections 1 and 2) | Harbor tasks (this section) |
|---|---|---|
| What runs | Your target function, in this process | The compiled agent, in a fresh sandbox, as a signed-in caller |
| What the grader reads | The reply, the reference, sometimes the trace | The full saved run state: every message, tool call, and tool result |
| Cost per example | Seconds | Minutes (image build, agent install, sandbox setup) |
| Good for | Answer quality across many examples, comparing versions, judge-based scores | Side effects, approval pauses, authorization, behavior that depends on the environment |
| Typical size | Dozens to hundreds of examples | A handful of high-stakes tasks |

Use both. Dataset evals tell you whether answers got better. Harbor tasks are the short list of things that must never break, run before every release.

```
                    What are you checking?
                            │
       ┌────────────────────┴────────────────────┐
       ▼                                         ▼
 How good is the answer?               Did something happen (or not happen)?
 (correct, complete, grounded,         (a side effect, an approval pause,
  well-written)                         data crossing customers, a file,
       │                                 behavior that needs the real setup)
       │                                         │
       ▼                                         ▼
 Dataset evaluator                       Harbor task
 many examples, seconds each,            a few tasks, minutes each,
 judge or code on the reply/trace        code on the saved run state
       │                                         │
       └──────────────────┬──────────────────────┘
                          ▼
         both run before release: dataset evals show whether
         quality moved; Harbor tasks block a release that breaks
         something that must never break
```

## Recap

- A Harbor task is a spec (`Task.md`), an input (`instruction.md` plus `identity.json`), an environment, and a verifier that reads what the run left behind.
- `--env langsmith` runs trials in LangSmith sandboxes, so you don't need local Docker. Keep `--no-project` so `uv` leaves the managed agent's environment alone.
- Write the spec first, and test the verifier against hand-made run states before spending a sandbox run on it.
- Write one score per check to `reward.json`, so a failure in LangSmith tells you which check failed.
- Make the task fail on purpose once. A task that has never failed hasn't shown it can catch anything.
'''),
]

# ============================================================================
# SECTION 3, v2: concept-first (see docs/2026-11-12-module-5-section-3-v2-plan.md)
# ============================================================================
s3_v2 = [
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
save("section_3_harbor_evals_v2.ipynb", s3_v2)
