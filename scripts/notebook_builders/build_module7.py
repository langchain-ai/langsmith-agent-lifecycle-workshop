"""Build Module 7 notebooks (Monitoring, Governance & Self-Improvement) for the TechHub workshop.

Usage (from the repo root):
    uv run python scripts/notebook_builders/build_module7.py workshop_modules/module_7

Design: docs/2026-11-19-module-7-monitoring-governance-prd.md. Section 5 gives the four notebooks and the
Setup cell; sections 7 to 10 give the cells of Sections 1 to 4.

How this file is laid out:

- The skeleton every builder shares: `OUT`, `KERNEL`, `md`, `code`, `save`.
- A line `# === M7 SHARED ===`. Below it is everything more than one notebook uses: `NOTEBOOKS` (the
  file name of each section), `SETUP` (the shared Setup cell), `NAV_FULL` and `NAV_SHORT` (the
  navigation sentence for LangSmith UI steps), and source excerpts read from repo files at build time.
  A missing anchor in an excerpt fails the build, so a notebook can never show code or policy text
  that has drifted from the repo.
- A line `# === M7 SECTIONS ===`. Below it is one list per notebook (`s1`, `s2`, ...), each under a
  banner comment that names the PRD, and then all `save(...)` calls at the very end.

How a section list is added. Write the list in a file of its own that defines one name, `sN`, using
only `md`, `code` and the names of the shared part (`SETUP`, `NAV_SHORT`, ...), with the banner comment
above it. Build it alone with the scratch helper of the build project (`module-7-build/work/build_one.py`,
outside this repo):

    python build_one.py N <cells file> <output folder>

It runs this file's skeleton and shared part, then the cells file, and saves `NOTEBOOKS[N]`. When the
list is final, paste it above the `save(...)` calls and add `save(NOTEBOOKS[N], sN)`. Keep both marker
lines exactly as they are: the helper splits this file on them.

Prose style. Every markdown cell and every printed message is plain language, following the humanizer
guide of the build project (`module-7-build/style/humanizer-SKILL.md`, outside this repo): short, direct
sentences; say what a thing does before why; no "not X but Y" contrasts, no one-line closers, no run-ups
such as "let's dive in"; no em or en dashes in prose; bold only for a term being defined and for UI
labels; no inflated words (crucial, key, robust, leverage); use is, are and has. Code, commands, paths,
identifiers, numbers and names stay exactly as they are.

Every notebook runs with no LangSmith key and no network. Each keyed call sits in a branch on
`LANGSMITH_AVAILABLE` or `SEEDED`. Check a build offline with:

    env -i PATH="$PATH" HOME="$HOME" LANGSMITH_TRACING=false .venv/bin/python scripts/verify_module7_offline.py <notebook>
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


# === M7 SHARED ===

REPO = Path(__file__).resolve().parents[2]

# The notebook of each section (PRD section 5).
NOTEBOOKS = {
    1: "section_1_online_evals_and_alerts.ipynb",
    2: "section_2_insights.ipynb",
    3: "section_3_engine.ipynb",
    4: "section_4_gateway_and_governance.ipynb",
}


def source_lines(path: str, start: str, end: str | None = None) -> list[str]:
    """Lines of a repo file from the first line starting with `start` to the next line starting with `end`.

    `path` is relative to the repo root. Without `end`, only the `start` line is returned. A missing
    anchor raises `ValueError`, so the build fails instead of showing text that has drifted.
    """
    lines = (REPO / path).read_text(encoding="utf-8").splitlines()
    starts = [n for n, line in enumerate(lines) if line.startswith(start)]
    if not starts:
        raise ValueError(f"{path} has no line starting with {start!r}: update the excerpt in build_module7.py")
    i = starts[0]
    if end is None:
        return lines[i : i + 1]
    ends = [n for n in range(i, len(lines)) if lines[n].startswith(end)]
    if not ends:
        raise ValueError(f"{path} has no line starting with {end!r} after {start!r}: update the excerpt in build_module7.py")
    return lines[i : ends[0] + 1]


def require_text(path: str, text: str) -> str:
    """Return `text` after checking that the repo file `path` contains it. A missing text fails the build."""
    if text not in (REPO / path).read_text(encoding="utf-8"):
        raise ValueError(f"{path} no longer contains {text!r}: update build_module7.py")
    return text


# The return windows of TechHub's policy (Section 1 shows them next to the evaluator exercise).
RETURN_POLICY_PATH = "data/documents/policies/return_policy.md"
RETURN_POLICY_EXCERPT = "\n".join(source_lines(RETURN_POLICY_PATH, "**Unopened Electronics**", "- 14 days from delivery date"))

# The statuses the agent's retry middleware retries (Section 4 compares them with the Gateway's blocks).
FAULT_TOLERANCE_PATH = "agents/middleware/fault_tolerance.py"
TRANSIENT_STATUSES_LINE = source_lines(FAULT_TOLERANCE_PATH, "_TRANSIENT_STATUSES =")[0]

# Strings that notebook text repeats from the helpers. Each must still be in the file named here.
FLAGGED_FILTER = require_text("utils/monitoring_rest.py", 'and(eq(is_root, true), eq(feedback_key, "wrong_return_window"), gt(feedback_score, 0.5))')
QUEUE_NAME = require_text("utils/trace_upload.py", "techhub-deep-agent-return-window-review")
SEED_PROJECT = require_text("utils/trace_seeding.py", "techhub-deep-agent-production")

# The navigation sentence for LangSmith UI steps (research note gap-5 section 5). NAV_FULL goes once per
# notebook, where the learner first looks at LangSmith; NAV_SHORT starts every later `Step | In the UI` table.
NAV_FULL = (
    "In LangSmith, open **Tracing**. If the control at the top left shows your workspace name (an agent-based "
    "workspace), select the agent **TechHub support** in the agent switcher in the top bar, then set the environment "
    f"control to **Production**. If it shows the LangSmith logo (a project-based workspace), open the tracing project "
    f"`{SEED_PROJECT}` (or the name you set in `M7_PROJECT`). Set the time range to at least the last 2 days."
)
NAV_SHORT = (
    "**Tracing** > agent **TechHub support** > **Production**; in a project-based workspace, **Tracing** > project "
    f"`{SEED_PROJECT}`. Set the time range to at least the last 2 days"
)

# The Setup cell of every notebook (PRD section 5; research note 01 section 3.2).
SETUP = code('''
import json, os, sys, warnings
from pathlib import Path
from dotenv import load_dotenv

REPO_ROOT = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / "config.py").exists())
sys.path.insert(0, str(REPO_ROOT))
# Load .env before any workshop import: config.py picks the models from it at import time
load_dotenv(REPO_ROOT / ".env")
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", message=r".*is deprecated and will be removed after", category=DeprecationWarning)

from utils.langsmith_links import setup_langsmith
from utils.trace_seeding import describe, load_seed, print_trace
from utils.trace_upload import resolve_destination

LANGSMITH_AVAILABLE = setup_langsmith()            # one probe at most, one printed line
DEST = resolve_destination(LANGSMITH_AVAILABLE)    # project name, project id, navigation sentence
DATA = REPO_ROOT / "workshop_modules" / "module_7" / "data"
seed = load_seed()                                 # timestamps shifted so the newest run is 5 minutes old
''')

# === M7 SECTIONS ===

# ============================================================================
# SECTION 1: Online evals, alerts and routing
# (see docs/2026-11-19-module-7-monitoring-governance-prd.md, section 7)
# ============================================================================
s1 = [
    md('''
# Module 7, Section 1: Online Evals, Alerts and Routing

Module 4 Section 3 ends with four loops. The fourth is the hill-climbing loop: production traces drive improvements to the agent. This module runs that loop on one day of production traffic of the TechHub deep support agent.

**An online evaluator is a function that LangSmith runs on each new trace and that writes a score on it.** It needs no reference answer: it judges the run on its own.

In this section:
1. The data: one day of TechHub production traffic
2. Three signals (errors, user scores, reading traces) and what each one misses
3. An online evaluator that finds wrong return-window answers
4. Filters and sampling: what you pay for and what you miss
5. An alert threshold that the background errors cannot reach
6. Routing flagged runs to an annotation queue for review
'''),
    md('''
## Setup

This section calls no model. `uv sync` is all you need, and a LangSmith key is optional. Without a key, every cell runs on the data on disk, and the steps in LangSmith are described instead of done.

| Where you are | What to set |
|---|---|
| No LangSmith key | Nothing. The Setup cell prints one line that starts with ⏭️ and the notebook runs locally |
| Project-based workspace: the control at the top left of LangSmith shows the LangSmith logo | `LANGSMITH_API_KEY` in `.env`. The traces go to the project `''' + SEED_PROJECT + '''`; set `M7_PROJECT` to use another name |
| Agent-based workspace: the control at the top left shows your workspace name | `LANGSMITH_API_KEY` and `TECHHUB_AGENT_ID` in `.env`. The traces go to that agent's Production environment; `TECHHUB_AGENT_ENVIRONMENT` picks another one |

With a key, some cells also write to your workspace: the seeded day, its scores and a review queue. Each of those cells starts with a flag such as `UPLOAD_SEED`. Set it to `False` to skip that write. If a write fails, the cell prints one line and the notebook continues locally.
'''),
    SETUP,
    md('''
## 1. One day of TechHub production traffic

TechHub put the deep support agent into production in Workshop 9. Yesterday evening the team shipped version 1.5.0. You are on call this morning with one day of traffic: 200 conversations and 260 customer turns. Five things in that day are wrong or wasteful, and nobody has told the team.

This module follows the order an on-call engineer works in. You detect problems with online evals and alerts (this section), understand them with Insights (Section 2), fix them with Engine (Section 3) and prevent them with masking and Gateway policies (Section 4). One silent failure runs through Sections 1 to 3: the agent gives some customers the wrong return window.

The data is synthetic. Every run has the tag `seed:m7` and the metadata `synthetic: true`. The customer and order ids are real ids from `data/structured/techhub.db`.

One customer turn is one trace. When the main agent asks the order specialist for one lookup, the trace has 14 runs (each `model > ChatOpenAI` is two runs: the graph node and the model call inside it):

```text
deep_support_agent              the root run: one customer turn
├── model > ChatOpenAI          the main agent plans
├── tools > task                it hands the question to a specialist
│   └── order-specialist
│       ├── model > ChatOpenAI
│       ├── tools > get_order_status
│       └── model > ChatOpenAI
└── model > ChatOpenAI          the main agent writes the reply
```

The seeded traces carry these 14 runs. A live trace of the same agent has about 95, because each middleware step adds a run of its own.
'''),
    code('''
summary = describe(seed)
print()
print_trace(seed, "t-0042")
'''),
    md('''
### Put the same day in your workspace (optional)

With a key, the next cell uploads the 260 traces and their 170 user scores. That is 260 of the 5,000 traces a month that a free organization without a payment method gets. To find them:

> ''' + NAV_FULL + '''

The Setup cell printed the same path for your workspace, after "Seeded traffic goes to:".

The upload writes every user score with `extend_trace_retention=False`. With the SDK's default, a score moves its whole trace from base retention (14 days on LangSmith Cloud) to extended retention (180 days), which costs more.

Running the upload twice is safe. It first looks for traces tagged `seed:m7` from the last 7 days and sends nothing if it finds them.
'''),
    code('''
from utils.trace_upload import upload_seed

UPLOAD_SEED = LANGSMITH_AVAILABLE  # set to False to keep the seeded day out of your workspace
if UPLOAD_SEED:
    SEEDED = upload_seed(seed, DEST)
else:
    SEEDED = False
    print("⏭️  Skipped: nothing was uploaded. Every cell below analyses the same 260 traces locally.")
'''),
    md('''
## 2. Three signals, and what each one misses

| Signal | What it finds | What it misses |
|---|---|---|
| Error status of a run | Crashes and timeouts | Answers that are wrong and raise no error |
| User feedback (thumbs up or down) | Answers customers dislike | Wrong answers that customers like, and conversations nobody rates (30 of the 200 here) |
| Reading traces by hand | Anything you notice | Everything you have no time to read: 260 traces a day here, far more in a real product |
'''),
    code('''
from datetime import datetime, timezone
from utils.monitoring_local import error_windows

windows = error_windows(seed)  # the whole seed, so the failing tool inside each trace can be named
burst = windows["burst"]
now = datetime.now(timezone.utc)
for row in windows["errors"]:
    minutes_ago = (now - row["start_time"]).total_seconds() / 60
    where = "burst" if row["in_burst"] else "background"
    print(f"{row['start_time']:%H:%M:%S} UTC  {minutes_ago:5.0f} min ago  {row['trace_key']}  {row['failing_tool'] or '-':<20}  {where}")
print()
print(
    f"{len(windows['errors'])} errored traces. {burst['errors']} of them inside {burst['span_seconds'] / 60:.0f} minutes, "
    f"about {(now - burst['first']).total_seconds() / 60:.0f} minutes ago, tool {', '.join(burst['failing_tools'])}."
)
print("The same traces in the LangSmith search bar: status:error")
'''),
    code('''
import re
from collections import Counter
from utils.monitoring_checks import check
from utils.trace_seeding import load_labels, root_runs, runs_by_trace, trace_key, user_scores

roots = root_runs(seed)
by_trace = runs_by_trace(seed)
scores = user_scores(seed)  # trace key of a conversation's last turn -> 1 (thumbs-up) or 0 (thumbs-down)
version_of = {trace_key(run): run["extra"]["metadata"]["app_version"] for run in roots}
conversations = Counter({run["extra"]["metadata"]["thread_id"]: version_of[trace_key(run)] for run in roots}.values())

down = [key for key, score in scores.items() if score == 0]
down_by_version = Counter(version_of[key] for key in down)
print(f"{len(down)} thumbs-down: " + ", ".join(f"{100 * down_by_version[v] / conversations[v]:.1f}% on {v}" for v in sorted(conversations)) + ".")

NOT_FOUND = re.compile(r"Order \\S+ not found\\.")


def tool_results(key):
    return [str(((run["outputs"] or {}).get("output") or {}).get("content", "")) for run in by_trace[key] if run["run_type"] == "tool"]


after_not_found = [key for key in down if any(NOT_FOUND.fullmatch(text) for text in tool_results(key))]
after_error = [key for key in down if any(run["error"] for run in by_trace[key])]
print(f"{len(after_not_found)} follow an 'Order ... not found.' tool result. {len(after_error)} follow an errored run.")

# The label file holds the ground truth for every conversation. It exists only because the data is
# synthetic: a real project has no such file. Here it says which conversations got the wrong return window.
labels = load_labels()
wrong_window = [c for c in labels["conversations"] if c["incident"] == "A"]
down_on_wrong = sum(c["user_score"] == 0 for c in wrong_window)
print(f"The {len(wrong_window)} conversations with the wrong return window got {down_on_wrong} thumbs-down.")

ok, message = check("s1_signals", {
    "errored_root_runs": len(windows["errors"]),
    "thumbs_down_conversations": len(down),
    "thumbs_down_after_order_not_found": len(after_not_found),
    "thumbs_down_on_wrong_return_window": down_on_wrong,
})
print(message)
'''),
    md('''
The error count found the burst in `get_order_status`. The thumbs-down found the orders that the agent reported as missing. Neither signal finds a confident wrong answer: the 11 customers who got the wrong return window gave 9 thumbs-up and no thumbs-down. Reading all 260 traces would find them, but you cannot do that every day. You need a check that knows the policy and runs on every trace: an online evaluator.
'''),
    md('''
## 3. An online evaluator is a function of one run

<div align="center">
    <img src="../../images/online_eval_process.png" width="800">
</div>

A **code evaluator** is a Python function that LangSmith runs once for each run that passes the evaluator's filter. LangSmith passes the run as a dictionary and stores each key of the returned dictionary as feedback on that run.

| Rule | What it means here |
|---|---|
| Name and arguments | `perform_eval(run, example=None)`. LangSmith passes a second argument when you test the evaluator on a dataset example, so the function must accept one |
| Input | `run["inputs"]["messages"]` ends with the customer's message. `run["outputs"]["messages"]` is the conversation so far and ends with the reply. A failed run has empty outputs |
| Output | A dictionary of feedback key to score, such as `{"wrong_return_window": True}` |
| Packages | The standard library and a few packages that LangSmith lists. The function has no internet access |

In this evaluator `True` means the evaluator found a problem. A high share of `True` scores is bad news.

TechHub's return policy, from `''' + RETURN_POLICY_PATH + '''`:

```text
''' + RETURN_POLICY_EXCERPT + '''
```

> 💡 **Try it first:** write `perform_eval` in `workshop_modules/module_7/exercises/return_window_evaluator.py`, then check it from the repository root with `uv run python workshop_modules/module_7/exercises/check.py s1_evaluator`. The next two cells show a naive version and the reference version.
'''),
    code('''
from utils.monitoring_local import apply_evaluator, flagged_trace_keys
from utils.trace_seeding import question_text, reply_text, trace_runs


def naive_eval(run, example=None):
    """Flag every reply that mentions 30 days."""
    return {"wrong_return_window": "30 days" in reply_text(run)}


naive_flagged = flagged_trace_keys(apply_evaluator(naive_eval, roots))
condition = {key: (c.get("details") or {}).get("item_condition") for c in labels["conversations"] for key in c["trace_keys"]}
unopened = [key for key in naive_flagged if condition.get(key) == "unopened"]
print(f"Flagged {len(naive_flagged)} of {len(roots)}. {len(unopened)} of them are correct answers about unopened items.")

opened = next(key for key in naive_flagged if condition.get(key) == "opened")
for key in (unopened[0], unopened[1], opened):
    root = trace_runs(seed, key)[0]
    print()
    print(f"{key} (the item is {condition[key]})")
    print("  Customer:", question_text(root))
    print("  Agent:   ", reply_text(root))
'''),
    code('''
from evaluators import WRONG_RETURN_WINDOW_SOURCE, wrong_return_window_evaluator

rows = apply_evaluator(wrong_return_window_evaluator, roots)
flagged = flagged_trace_keys(rows)
print(f"Flagged {len(flagged)} of {len(roots)}.")
ok, message = check("s1_evaluator", wrong_return_window_evaluator)
print(message)

versions = sorted({version_of[key] for key in flagged})
with_policy_search = sum(any(run["name"] == "search_policy_docs" for run in by_trace[key]) for key in flagged)
up = sum(scores.get(key) == 1 for key in flagged)
thumbs_down = sum(scores.get(key) == 0 for key in flagged)
unrated = sum(key not in scores for key in flagged)
print(f"All on app_version {', '.join(versions)}. Traces with a search_policy_docs run: {with_policy_search}.")
print(f"Their user scores: {up} up, {thumbs_down} down, {unrated} without a score.")
'''),
    code('''
from utils.trace_upload import write_scores

# The documented replacement for the deprecated evaluate_run(): run the evaluator yourself and log
# each result as feedback with create_feedback().
WRITE_SCORES = SEEDED  # set to False to keep the scores out of your workspace
if WRITE_SCORES:
    write_scores(seed, DEST, wrong_return_window_evaluator)
    print("To see the flagged runs, paste this into the LangSmith search bar: feedback.wrong_return_window.score:>0.5")
else:
    print(f"⏭️  Skipped. On our runs: {len(flagged)} runs carry wrong_return_window = 1.")
'''),
    md('''
### 3.1 Attach it to live traffic

The notebook scored yesterday's traces itself. In LangSmith, an evaluator scores new traces as they arrive. With a key, do these steps yourself. Without one, the facilitator shows them. The labels come from the LangSmith docs and can differ a little in your workspace.

| Step | In the UI |
|---|---|
| 1. Open your TechHub traces | ''' + NAV_SHORT + ''' |
| 2. Start an evaluator | The **Evaluators** tab (**Online Evaluators** in an agent-based workspace) > **+ Evaluator** > **Code Evaluator** under **Create from scratch** |
| 3. Name it | `wrong_return_window`, the same as the key the function returns. The docs say the evaluator's name is also a feedback name, so one name for both avoids two keys |
| 4. Filter | **Run Name** is `deep_support_agent`, so only root runs are scored |
| 5. Sampling rate | 1.0: every matching run |
| 6. Past runs | Leave **Apply to past runs** off. The notebook has already scored yesterday |
| 7. Code | Paste the function that the next cell prints, click **Test Code**, then **Save** |
'''),
    code('''
from utils.trace_seeding import root_runs
from utils.trace_upload import build_live_traces, send_live_traces

print(WRONG_RETURN_WINDOW_SOURCE)

SEND_LIVE_TRACES = SEEDED  # set to False to send no fresh traces
if SEND_LIVE_TRACES:
    send_live_traces("quality", 4, DEST)
else:
    live_runs, _ = build_live_traces("quality", 4)  # built here and not sent
    live_flagged = flagged_trace_keys(apply_evaluator(wrong_return_window_evaluator, root_runs(live_runs)))
    print(f"⏭️  Skipped. With the evaluator attached, {len(live_flagged)} of the 4 new traces are scored wrong_return_window = 1.")
'''),
    code('''
from utils.trace_upload import live_scores

if SEEDED:
    live_scores(DEST)  # counts the fresh traces that already carry the score; it does not wait
else:
    print("⏭️  Skipped: no fresh traces were sent.")
'''),
    md('''
## 4. Filters and sampling: what you pay for and what you miss

Two settings decide which runs an evaluator scores: a filter and a sampling rate. A code evaluator costs no model tokens. An LLM-as-judge evaluator pays for every run it scores, and with retention extension on, every scored trace moves to extended retention.

| Lever | Effect on cost | Effect on coverage |
|---|---|---|
| Filter | Only matching runs are scored | Problems outside the filter are missed |
| Sampling rate | A random share of the matching runs is scored | Problems in the runs that are not drawn are missed |
| Weekly evaluator spend limit | LLM-as-judge evaluators stop at a set amount per week | Nothing is scored after the limit |
| Retention | Retention extension is on by default for new evaluators: each scored trace moves to extended retention | None |

Filter strings in the documented filter syntax:

| Filter | Selects |
|---|---|
| `eq(is_root, true)` | Every root run: one per customer turn |
| `and(eq(is_root, true), eq(metadata_key, "app_version"), eq(metadata_value, "1.5.0"))` | Root runs of release 1.5.0 |
| `eq(name, "product-policy-specialist")` | The product-policy specialist's run inside each trace |

To pick out the model calls of one agent, filter on the metadata key `lc_agent_name`. The run names `model` and `ChatOpenAI` occur in every agent, and the name of the model run changes with the provider.

The next cell compares three configurations for the evaluator of §3. The 25% sample is a fixed draw, so the exercise has one answer. LangSmith draws each run on its own, so a real 25% rate scores about a quarter of the runs, a different quarter every time.
'''),
    code('''
from statistics import median
from utils.monitoring_local import FILTERS, sample, select

caught = set(flagged)


def scored_and_caught(runs):
    return {"scored": len(runs), "caught": sum(trace_key(run) in caught for run in runs)}


configurations = {
    "all_root_runs": select("root_runs", seed),
    "app_version_1_5_0": select("root_runs_on_1_5_0", seed),
    "sample_25_percent": sample(roots, rate=0.25),
}
names = {"all_root_runs": "All root runs", "app_version_1_5_0": "Filter app_version 1.5.0", "sample_25_percent": "25% sample"}
for name, runs in configurations.items():
    result = scored_and_caught(runs)
    print(f"{names[name] + ':':<27} {result['scored']:>3} scored, {result['caught']:>2} caught")
print()
print("Filter strings:")
for name in ("root_runs", "root_runs_on_1_5_0"):
    print(f"  {FILTERS[name].filter}")

draws = [scored_and_caught(sample(roots, rate=0.25, seed=draw))["caught"] for draw in range(100, 120)]
print()
print(f"20 other 25% draws catch between {min(draws)} and {max(draws)} of the {len(caught)} (median {median(draws):g}).")

ok, message = check("s1_filter_sample", {name: scored_and_caught(runs) for name, runs in configurations.items()})
print(message)
'''),
    md('''
## 5. From scores to an alert

An alert watches one metric of a tracing project (or of one agent environment) and notifies you when the metric crosses a threshold.

| Part | Choices |
|---|---|
| Metric | Run Count, Cost, Errors, Feedback Score, Latency |
| Threshold | A number and a comparison such as `>=` |
| Aggregation window | 5 or 15 minutes |
| Channel | Slack, PagerDuty, Dynatrace or a webhook |

A threshold that is too low pages someone for background errors. A threshold that is too high misses a real burst.

> 💡 **Try it first:** in the error list of §2, what is the largest number of background errors in any 5 minutes? Which threshold can they never reach?
'''),
    code('''
from utils.monitoring_local import error_bars

print(f"Errors per {windows['minutes']}-minute window (windows with no error are left out):")
for line in error_bars(windows):
    print(line)
print("These windows start on the clock, so one burst can fall into two of them. The counts below hold wherever a window starts.")
print()
background = windows["background"]["max_in_any_window"]
print(
    f"Background errors: at most {background} in any {windows['minutes']} minutes. "
    f"Burst: {burst['errors']} in {burst['span_seconds'] / 60:.0f} minutes. "
    f"Smallest threshold the background cannot reach: {windows['smallest_safe_threshold']}."
)
ok, message = check("s1_alert", {
    "background_max_in_5_minutes": background,
    "burst_errors": burst["errors"],
    "threshold": windows["smallest_safe_threshold"],
    "failing_tool": burst["failing_tools"][0],
})
print(message)
'''),
    md('''
### The same alert in LangSmith

| Step | In the UI |
|---|---|
| 1. Open your TechHub traces | ''' + NAV_SHORT + ''' |
| 2. Start an alert | The **Alerts** icon in the top right-hand corner. The docs also call it **+ Alert** and **Alerts > Create Alert**; use the one you see |
| 3. Metric | **Errors**, as a count. It counts every run with an error status, and each failed trace of the seeded day holds 6 errored runs. To count failed traces, count root runs only (`eq(is_root, true)` as an API filter). Whether the alert form offers a root-run condition is UNVERIFIED |
| 4. Condition | Threshold 3 failed traces (errored root runs), **Aggregation Window** 5 minutes |
| 5. Preview | Read the historical preview: it marks the windows that would have fired |
| 6. Channel | A webhook or Slack. Click **Send Test Alert** (**Send Test Notification** for Slack) |

Two facts to know before you rely on an alert:

- **Send Test Alert** does not check the receiver's response. The UI reports success even when the receiver returned an error, so look at the receiver's own log.
- LangSmith sends the body you configure as written, with no template substitution, and adds 12 keys at the top level. The next cell prints them.

The seeded burst is close to an hour old (§2 printed its age), so it cannot trip a live 5-minute window. Whether the preview shows back-dated runs is UNVERIFIED. To see a real firing, set `TRIP_ALERT = True` in the next cell: it sends 5 errored runs dated now.
'''),
    code('''
payload = json.loads((DATA / "alert_webhook_payload.json").read_text(encoding="utf-8"))
keys = [key for key in payload if not key.startswith("_")]
print(f"The {len(keys)} keys LangSmith adds to an alert webhook body (the values are examples):")
for key in keys:
    print(f"  {key}: {payload[key]!r}")
print()

TRIP_ALERT = False  # set to True (with a key, after the upload) to send 5 errored runs dated now
if TRIP_ALERT and SEEDED:
    send_live_traces("errors", 5, DEST)
else:
    print("⏭️  Not sent. With a key and TRIP_ALERT = True, this cell sends 5 errored runs dated now.")
'''),
    md('''
## 6. Route what was flagged to people

<div align="center">
    <img src="../../images/data_flywheel.png" width="800">
</div>

A score marks a run as wrong. A person still has to confirm it and write the correct answer, which then becomes a test case. An **automation rule** sends runs to that person. It has an item type, a filter, a sampling rate and an action, such as adding the run to an annotation queue.

> 💡 **Try it first:** which filter selects the root runs that the evaluator scored `wrong_return_window` = 1? The filter syntax has the fields `feedback_key` and `feedback_score`.
'''),
    code('''
from utils.trace_upload import send_to_queue

route = FILTERS["flagged_wrong_return_window"]
selected = select("flagged_wrong_return_window", seed, rows)  # rows: the evaluator's scores from §3
print("Filter:", route.filter)
print(f"{len(selected)} runs selected.")
ok, message = check("s1_routing", selected)
print(message)

CREATE_QUEUE = SEEDED  # set to False to create no queue in your workspace
if CREATE_QUEUE:
    send_to_queue(DEST, [trace_key(run) for run in selected])
else:
    print("⏭️  Skipped: no queue was created, because nothing was uploaded.")
'''),
    md('''
### Automate it for new traffic, and review one item

The cell above routed yesterday's runs once. An automation does the same for every new run:

| Step | In the UI |
|---|---|
| 1. Open your TechHub traces | ''' + NAV_SHORT + ''' |
| 2. Start an automation | **+ New** > **New Automation**, then a name |
| 3. Item type | **Runs** |
| 4. Filter | Feedback key `wrong_return_window`, score above 0.5 |
| 5. Action | **Add to Annotation Queue**, queue `''' + QUEUE_NAME + '''` |
| 6. Past runs | Leave **Apply to Past Runs** off |

Then review one item, as in Module 3:

| Step | In the UI |
|---|---|
| 1. Open the queue | **Annotation Queues** in the left navigation, then `''' + QUEUE_NAME + '''`. A queue lists its items whatever their age, so it has no time range |
| 2. Validate | Read the customer's message and the reply. The customer opened the product and was told 30 days |
| 3. Add feedback | Score the run as the queue's instructions say |
| 4. Correct the output | Turn on **Classic Trace View** to edit the output, and change the window to 14 days |
| 5. Keep it as a test case | **Add to Dataset** > `techhub-deep-agent-regressions` |
'''),
    code('''
from utils.monitoring_rest import code_evaluator_rule, create_rule_once, queue_rule
from utils.trace_upload import QUEUE_NAME, new_client

# Optional: the evaluator of §3.1 and the automation above as two REST requests. Sending them is
# UNVERIFIED against a live workspace, so the flag is off. Printing a body sends nothing.
MONITORING_AS_CODE = False
project_id = DEST.project_id or "<project id>"
evaluator_body = code_evaluator_rule(project_id=project_id, code=WRONG_RETURN_WINDOW_SOURCE)
shown = {**evaluator_body, "code_evaluators": [{"code": "<WRONG_RETURN_WINDOW_SOURCE>", "language": "python"}]}
print("POST /api/v1/runs/rules  (attach the evaluator)")
print(json.dumps(shown, indent=2))
print("POST /api/v1/runs/rules  (route flagged runs to the queue)")
print(json.dumps(queue_rule(project_id=project_id, queue_id="<queue id>"), indent=2))
print()

if MONITORING_AS_CODE and SEEDED:
    try:
        client = new_client()
        bodies = [code_evaluator_rule(project_id=DEST.project_id, code=WRONG_RETURN_WINDOW_SOURCE)]
        queue = next(iter(client.list_annotation_queues(name=QUEUE_NAME)), None)
        if queue is None:
            print(f"No queue named {QUEUE_NAME}: run the routing cell of §6 first. Only the evaluator is sent.")
        else:
            bodies.append(queue_rule(project_id=DEST.project_id, queue_id=str(queue.id)))
        for body in bodies:
            rule = create_rule_once(client, body)  # lists the project's rules first and skips a duplicate name
            print(f"{body['display_name']}: " + ("created." if rule else "a rule of this name exists, nothing was sent."))
    except Exception as exc:  # noqa: BLE001 - any failure falls back to the UI steps
        print(f"⏭️  The request failed ({type(exc).__name__}). Use the UI steps of §3.1 and §6 instead.")
else:
    print("⏭️  Not sent. With a key and MONITORING_AS_CODE = True, this cell sends both requests.")
'''),
    md('''
### What you did in code, and where it is in LangSmith

| Step in this notebook | Same step in the UI |
|---|---|
| `upload_seed(seed, DEST)` | Traces arrive from your application. Nothing to click |
| `apply_evaluator(...)`, `write_scores(...)` | An online evaluator attached on the **Evaluators** tab (§3.1) |
| `select("root_runs_on_1_5_0", seed)`, `sample(roots, rate=0.25)` | The evaluator's filter and sampling rate |
| `error_windows(seed)` | An alert on **Errors** with a 5-minute window (§5) |
| `send_to_queue(DEST, ...)` | An automation with the action **Add to Annotation Queue** (§6) |

This section only described LLM-as-judge and thread evaluators. Both need a model provider key stored in the workspace. A thread evaluator also needs a `messages` key in the top-level inputs and outputs of every trace, and it runs only after a thread has been idle for the project's idle time (10 minutes by default, at least 2).

## Recap

- The error count and the thumbs-down missed the 11 wrong return-window answers: they raised no error and got no thumbs-down.
- A code evaluator is a function `perform_eval(run, example=None)` that returns feedback. It needs no model, so it can score every trace.
- The filter on app_version 1.5.0 scored 104 runs and caught all 11. The 25% sample scored 65 and caught 3.
- An alert with a threshold of 3 failed traces (errored root runs) in 5 minutes stays quiet for the background (at most 2) and fires on the burst of 8.
- An automation on the evaluator's feedback sends flagged runs to a review queue, where people turn them into test cases.

**Next:** Section 2 reads an Insights report of the same day and checks one of its claims with this evaluator.
'''),
]


# ============================================================================
# SECTION 2: Insights
# (see docs/2026-11-19-module-7-monitoring-governance-prd.md, section 8)
# ============================================================================
s2 = [
    md('''
# Module 7, Section 2: Insights

Section 1 found the wrong return window because you knew what to look for and wrote a check for it. An online evaluator answers a question you write down in advance. Insights finds the questions you had not thought to ask.

**Insights** is a LangSmith feature that reads a batch of traces, groups them into categories and subcategories, and writes a report with statistics for each group.

In this section:
1. How Insights builds a report
2. Reading a report top down: summary, categories, subcategories
3. Silent failures have a 0% error rate: checking one claim against the traces
4. Deciding what each finding should become
5. From a subcategory to an annotation queue to a dataset
6. Running a real report in the LangSmith UI
'''),
    md('''
## Setup

This section calls no model and needs no key. It reads a sample report that ships with the module, `workshop_modules/module_7/data/insights_report_techhub.json`. The sample is hand-built from the seed, so every number in it matches the traces, and it has the documented structure of a real report.

A real report has three requirements:

| Requirement | Detail |
|---|---|
| Plan | LangSmith Plus or Enterprise. A free Developer workspace cannot run Insights |
| Model | A model configuration for Insights, backed by a provider key stored as a workspace secret. The report's model calls are billed to that key |
| Time | Up to 30 minutes per report |

| Where you are | What to set |
|---|---|
| No LangSmith key, or no access to Insights | Nothing. The notebook reads the sample report |
| A key and a finished report on your TechHub traces | `M7_INSIGHTS_REPORT_ID` in `.env`: the report's id, which is the `clusterJobId` value in the report's URL. The report must belong to the project that the Setup cell names after "Seeded traffic goes to:" |

The checks always grade the sample report, because the answer key describes the seeded day. One cell can write to your workspace, and only when you set its flag: `CREATE_DATASET` in §5 adds one test case to a dataset.
'''),
    SETUP,
    md('''
## 1. How Insights works

Insights builds a report in three steps. The numbers on the left are those of the TechHub day:

```text
260 traces in 200 conversations
   │  1. Summarize: a cheaper model (the Summarization model) writes a short summary of each conversation
   ▼
200 summaries
   │  2. Cluster: a more capable model (the Thinking model) groups the summaries into categories and subcategories
   ▼
4 categories, 10 subcategories
   │  3. Report: an executive summary with key points and highlighted traces, and statistics for each group
   ▼
the report
```

Only what is in a summary can influence the categories. You can name the top-level categories yourself; the subcategories are always generated.

| Fact | Value |
|---|---|
| What it reads | Traces (root runs), at most 1,000 per report. In a project with threads it analyses whole conversations, and only the most recent root run of each thread fills the `run.*` variables of the summary prompt |
| How long it takes | Up to 30 minutes, according to the docs. No time is documented for a small set of traces |
| Who pays | The workspace's own provider key. The docs give about $1.00 to $2.00 per 1,000 threads with OpenAI models and $3.00 to $4.00 with Anthropic models |
| Who can do it | Viewing a report needs read access to the project. Starting one needs permission to create rules, which Editors and Admins have |

The TechHub traces have threads, so the sample report counts conversations: its groups add up to 200.
'''),
    code('''
from langsmith.schemas import InsightsReportResult
from utils.trace_seeding import load_insights_report
from utils.trace_upload import new_client

INSIGHTS_REPORT_ID = os.getenv("M7_INSIGHTS_REPORT_ID")  # the id of a finished report on your TechHub traces (optional)

# The sample is a dictionary in the REST shape of a report, with its times moved along with the seed.
# It loads into the same type that client.get_insights_report() returns.
sample = InsightsReportResult(**load_insights_report(seed))
report = sample
if LANGSMITH_AVAILABLE and INSIGHTS_REPORT_ID:
    if DEST.project_id is None:
        print(f"⏭️  The project {DEST.project_name} has no traces yet, so report {INSIGHTS_REPORT_ID} cannot be read there.")
    else:
        try:
            report = new_client().get_insights_report(id=INSIGHTS_REPORT_ID, project_id=DEST.project_id, include_runs=False)
            print(f"Reading your report {INSIGHTS_REPORT_ID}.")
        except Exception as exc:  # noqa: BLE001 - any failure falls back to the sample report
            print(f"⏭️  Could not read report {INSIGHTS_REPORT_ID} ({type(exc).__name__}).")
if report is sample:
    print("⏭️  Reading the sample report shipped with the module (hand-built from the seed, not real Insights output).")

print()
print(report.name)
print(f"Status: {report.status}. Finished: {report.end_time}.")
print(f"report.clusters holds {len(list(report.clusters))} groups in one flat list: the categories and their subcategories.")
'''),
    code('''
from utils.trace_seeding import root_runs, trace_key

summary = report.report
keys_by_run_id = {run["id"]: trace_key(run) for run in root_runs(seed)}  # run id -> seed trace key such as t-0169

print(summary.title)
print()
print("Key points")
for number, point in enumerate(summary.key_points, start=1):
    print(f"{number}. {point}")
print()
print("Highlighted traces")
for trace in sorted(summary.highlighted_traces, key=lambda t: t.rank):
    where = keys_by_run_id.get(str(trace.run_id), str(trace.run_id))
    print(f"#{trace.rank}  {trace.cluster_name}  (trace {where})")
    print(f"    {trace.highlight_reason}")
'''),
    md('''
## 2. Read it top down

Read a report in the order the UI shows it: the executive summary, the categories, the subcategories, then the traces behind them.

| Look at | What to look for |
|---|---|
| Executive summary | The claims the report makes, with their percentages. Each highlighted trace (#1, #2, ...) is an example the report picked for a claim |
| Categories | Where the traffic is: the share of conversations in each category |
| Subcategories | The outliers: the highest error rate, the highest cost, and a description that names a failure while the error rate is 0 |
| Traces | The evidence. Open a highlighted trace before you act on a claim |

Each group has a `stats` dictionary. This module uses three of its keys: `error_rate` (a fraction from 0 to 1), `latency_p50` (the median latency in seconds) and `cost_p50` (the median cost in dollars). In the sample report, `error_rate` is the share of conversations with an errored run. A real report also shows, per group, the feedback scores of your evaluators and any attributes you asked for; the docs do not name their keys.

A cluster whose `parent_id` is `None` is a top-level category, and every other cluster is a subcategory. The meaning of the `level` number is not documented, so the code below uses `parent_id`, which the REST schema defines.

> 💡 **Try it first:** write `summarise(report)` in `workshop_modules/module_7/exercises/read_the_report.py`. It receives the report as a dictionary, as `utils.trace_seeding.load_insights_report()` returns it, and returns the largest category and the subcategory with the highest error rate. Check it from the repository root with `uv run python workshop_modules/module_7/exercises/check.py s2_report`. To read the whole report in a terminal first, run `uv run python workshop_modules/module_7/exercises/show_report.py`.
'''),
    code('''
def stats_of(cluster):
    return cluster.stats or {}  # the schema allows stats to be None


def row(name, cluster, total):
    stats = stats_of(cluster)
    cost = f"${stats.get('cost_p50', 0.0):.4f}"
    return (f"{name:<36} {cluster.num_runs:>5} {cluster.num_runs / total:>6.0%} {stats.get('error_rate', 0.0):>7.1%} "
            f"{stats.get('latency_p50', 0.0):>7.1f}s {cost:>9}")


clusters = list(report.clusters)
categories = sorted((c for c in clusters if c.parent_id is None), key=lambda c: -c.num_runs)
total = sum(c.num_runs for c in categories)  # every conversation is in exactly one top-level category

print(f"{'Category':<36} {'convs':>5} {'share':>6} {'errors':>7} {'latency':>8} {'cost':>9}")
for category in categories:
    print(row(category.name, category, total))
print()
print(f"{total} conversations. 'errors' is the error rate; latency and cost are medians (p50).")
'''),
    code('''
from utils.monitoring_checks import check


def summary_of(report):
    """The two headline facts of a report: its largest category and its subcategory with the highest error rate."""
    clusters = list(report.clusters)
    tops = [c for c in clusters if c.parent_id is None]
    subs = [c for c in clusters if c.parent_id is not None]
    largest = max(tops, key=lambda c: c.num_runs)
    worst = max(subs, key=lambda c: stats_of(c).get("error_rate", 0.0))
    return {
        "largest_category": largest.name,
        "largest_category_conversations": largest.num_runs,
        "largest_category_share": round(largest.num_runs / sum(c.num_runs for c in tops), 2),
        "highest_error_rate_subcategory": worst.name,
        "highest_error_rate": stats_of(worst)["error_rate"],
    }


print(f"{'Category and subcategory':<36} {'convs':>5} {'share':>6} {'errors':>7} {'latency':>8} {'cost':>9}")
for category in categories:
    print(row(category.name, category, total))
    children = sorted((c for c in clusters if c.parent_id == category.id), key=lambda c: -c.num_runs)
    for child in children:
        print(row("  " + child.name, child, total))

headline = summary_of(report)
print()
print(f"Largest category: {headline['largest_category']} ({headline['largest_category_conversations']} conversations, {headline['largest_category_share']:.0%}).")
print(f"Highest error rate: {headline['highest_error_rate_subcategory']} ({headline['highest_error_rate']:.1%}).")
if report is not sample:
    print("The check below grades the sample report, because the answer key describes the seeded day.")
ok, message = check("s2_report", summary_of(sample))
print(message)
'''),
    md('''
## 3. Silent failures have a 0% error rate

Two subcategories show an error rate of 0.0%: "Return window questions" and "Order reported as not found". Nothing crashed in either, so an error-rate chart shows nothing for them. The report found them from what the conversations say.

The category names, the descriptions and the key points are model output. The metadata, the tool results and the replies in the traces are what happened. Check a claim against the traces before you act on it. The next cell checks the report's claim about return windows with the evaluator from Section 1.

The cell takes the 27 conversations of the subcategory from `seed_labels.json`. That label file exists only because the data is synthetic. With a real report you get the same list from the subcategory's traces table in the UI, or from `report.clusters["Return window questions"].load_traces()` on a report read with `client.get_insights_report`. The keys of the runs that call returns are not documented (UNVERIFIED).

> 💡 **Try it first:** write `flagged_in_subcategory(name, seed, labels, perform_eval)` in the same file, `read_the_report.py`. It counts the conversations of one subcategory that an evaluator flags. Check it with `uv run python workshop_modules/module_7/exercises/check.py s2_claim`.
'''),
    code('''
from collections import Counter
from evaluators import wrong_return_window_evaluator
from utils.monitoring_local import apply_evaluator, flagged_trace_keys
from utils.trace_seeding import load_labels, trace_runs

CLAIMED = "Return window questions"
# This cell reads the sample report even when your own report is loaded: the label file describes the seeded day.
claim = next(point for point in sample.report.key_points if CLAIMED in point)
cluster = next(c for c in sample.clusters if c.name == CLAIMED)

labels = load_labels()  # ground truth per conversation; it exists only because the data is synthetic
conversations = [c for c in labels["conversations"] if c["subcategory"] == CLAIMED]
roots_by_key = {trace_key(run): run for run in root_runs(seed)}
turns = [roots_by_key[key] for c in conversations for key in c["trace_keys"]]
flagged_keys = set(flagged_trace_keys(apply_evaluator(wrong_return_window_evaluator, turns)))
flagged = [c for c in conversations if flagged_keys & set(c["trace_keys"])]  # a conversation counts once

print("Report:", claim)
print(f"Report: {cluster.num_runs} conversations, error rate {stats_of(cluster)['error_rate']:.1%}.")
print(f"Traces: the Section 1 evaluator flags {len(flagged)} of {len(conversations)} conversations, "
      f"all on app_version {', '.join(sorted({c['app_version'] for c in flagged}))}.")
print()
print("What the 27 conversations were told, by product condition and version:")
answers = Counter((c["details"]["item_condition"], c["app_version"], c["details"]["answered_window_days"]) for c in conversations)
for (condition, version, days), count in sorted(answers.items()):
    right = 30 if condition == "unopened" else 14
    print(f"  {condition:<9} on {version}: {count:>2} told {days} days ({'right' if days == right else 'wrong'})")

top = min(sample.report.highlighted_traces, key=lambda t: t.rank)
evidence = trace_runs(seed, str(top.run_id))
names = {run["name"] for run in evidence}
print()
print(f"Highlighted trace #{top.rank}: {top.highlight_reason}")
print_trace(seed, str(top.run_id))
if "product-policy-specialist" in names and "search_policy_docs" not in names:
    print("product-policy-specialist answered without calling search_policy_docs.")
print()
ok, message = check("s2_claim", {
    "conversations": cluster.num_runs,
    "error_rate": stats_of(cluster)["error_rate"],
    "flagged": len(flagged),
})
print(message)
'''),
    md('''
## 4. What should each finding become?

A finding can go to one of five places:

| Choice | Fits a finding that |
|---|---|
| Alert | Shows in a metric LangSmith already records (errors, latency, cost, a feedback score) and needs someone to act within minutes |
| Online evaluator | Can be written down as a check on one trace, so every new trace can be scored |
| Annotation queue | Needs a person to read the traces and correct them |
| Engine issue | Needs a change to the agent, with a diagnosis and evidence, tracked until it is fixed |
| Nothing | Is the agent behaving as intended |

> 💡 **Try it first:** for each of the five key points of the report, choose one of the five. Some have two defensible answers. The next cell gives a worked answer; it is not graded.

| Key point | Your choice |
|---|---|
| 1. Errors in "Where is my order" after an order-service outage | |
| 2. 30 days given for opened electronics, with a 0.0% error rate | |
| 3. Orders reported as not found, with a 0.0% error rate | |
| 4. Compatibility questions cost about twice as much as spec lookups | |
| 5. Out-of-scope requests refused | |
'''),
    code('''
worked_answer = [
    ("Errors in 'Where is my order' after an order-service outage",
     "Alert",
     "An error count is a metric LangSmith already records. Section 1 found the threshold: 3 failed traces (errored root runs) in 5 minutes. "
     "The errors came from get_order_status timing out, so the first job is to tell someone while it happens.",
     None),
    ("30 days given for opened electronics, with a 0.0% error rate",
     "Online evaluator",
     "The answers raise no error and got 9 thumbs-up and no thumbs-down, so only a check that knows the policy finds new cases. "
     "Section 1 wrote that check and routed its flagged runs to an annotation queue.",
     "An Engine issue as well, to track the fix to the policy specialist's instructions. That is issue 1 in Section 3."),
    ("Orders reported as not found, with a 0.0% error rate",
     "Engine issue",
     "The agent needs a code change: normalise an order id typed in lower case or without dashes to the ORD-YYYY-NNNN form before the lookup. "
     "An Engine issue holds the diagnosis, the evidence and the pull request. That is issue 2 in Section 3, status fixing.",
     "An online evaluator that flags a reply saying an order does not exist after an 'Order ... not found.' tool result."),
    ("Compatibility questions cost about twice as much as spec lookups",
     "Engine issue, kept as a finding to watch",
     "The answers are correct, so only cost is affected. Engine records it as a finding and counts new cases while it is "
     "watched. That is issue 3 in Section 3.",
     "An alert on Cost, if the spend grows."),
    ("Out-of-scope requests refused",
     "Nothing",
     "The scope guard refused all 11 requests for another customer's data, as designed. The 15 unrelated requests need no change.",
     "An annotation queue with a small sample, if you want people to confirm the refusals from time to time."),
]
for number, (finding, choice, why, also) in enumerate(worked_answer, start=1):
    print(f"{number}. {finding}")
    print(f"   Choice: {choice}")
    print(f"   Why: {why}")
    if also:
        print(f"   Also defensible: {also}")
    print()
'''),
    md('''
## 5. From a subcategory to a queue to a dataset

A subcategory with a real failure ends up as test cases. The Academy recommends review first: people confirm in an annotation queue that the pattern is real and correct each answer, and only then add the traces to a dataset.

> ''' + NAV_FULL + '''

| Step | In the UI |
|---|---|
| 1. Open your TechHub traces | ''' + NAV_SHORT + ''' |
| 2. Open the report | The **Insights** tab, then the report |
| 3. Drill down | Click a category, then a subcategory (in the sample: **Returns and refunds**, then **Return window questions**). This opens the subcategory's traces table |
| 4. Select traces | Tick rows with the row checkboxes. One action adds at most 100 items |
| 5. Send them to review | **Add to Annotation Queue** at the bottom of the page. Under **What to add**, choose **Selected run** or **Entire thread**, then the queue `''' + QUEUE_NAME + '''` |
| 6. Review | In the queue, correct the answer to 14 days, then **Add to Dataset** > `techhub-deep-agent-regressions`, as at the end of Section 1 |

The docs describe steps 4 and 5 for any traces table. Whether the report view has its own control that adds a whole subcategory at once is UNVERIFIED.

The next cell builds the same test case in code, from highlighted trace #1: the customer's question and the corrected answer.
'''),
    code('''
from utils.monitoring_checks import CORRECTED_ANSWER
from utils.trace_seeding import question_text, reply_text

DATASET_NAME = "techhub-deep-agent-regressions"
root = evidence[0]  # the root run of highlighted trace #1, from §3
key = trace_key(root)
example = {
    "inputs": {"messages": [{"role": "user", "content": question_text(root)}]},
    "outputs": {"messages": [{"role": "assistant", "content": CORRECTED_ANSWER}]},
    "metadata": {"seed_trace_key": key, "subcategory": CLAIMED, "source": "module 7 section 2"},
}
print(f"Trace {key}. The agent answered: {reply_text(root)}")
print()
print("The test case:")
print(json.dumps(example, indent=2))
print()

CREATE_DATASET = False  # set to True (with a key) to add this example to the dataset
if CREATE_DATASET and LANGSMITH_AVAILABLE:
    try:
        client = new_client()
        if not client.has_dataset(dataset_name=DATASET_NAME):
            client.create_dataset(DATASET_NAME, description="TechHub deep agent: corrected answers from production traces (Module 7).")
        # Re-running adds nothing: an example built from the same seed trace is already there.
        if next(iter(client.list_examples(dataset_name=DATASET_NAME, metadata={"seed_trace_key": key}, limit=1)), None):
            print(f"{DATASET_NAME} already has an example from trace {key}. Nothing was added.")
        else:
            client.create_examples(dataset_name=DATASET_NAME, examples=[example])
            print(f"Added 1 example to {DATASET_NAME}.")
    except Exception as exc:  # noqa: BLE001 - the example above stays printed; the UI steps of §5 do the same
        print(f"⏭️  The dataset step failed ({type(exc).__name__}). Add the example with the UI steps above instead.")
else:
    print(f"⏭️  Not sent. With a key and CREATE_DATASET = True, this cell adds the example to {DATASET_NAME}.")
'''),
    md('''
## 6. Run a real report (in the UI)

With Plus or Enterprise and a provider key in the workspace, you can run a report on the seeded day yourself. It can take up to 30 minutes, so start it at the beginning of a session and read it at the end. The report's model calls are billed to the workspace's provider key (§1 gives the cost per 1,000 threads).

| Step | In the UI |
|---|---|
| 1. Open your TechHub traces | ''' + NAV_SHORT + ''' |
| 2. Start a report | **+ New** in the top right corner > **New Insights Report**, then a name |
| 3. Model | If Insights has no model yet, a Workspace Admin adds the provider key under **Settings > Integrations > Provider secrets** and picks the models for Insights under the model configurations. The settings pages were reorganised in November 2026, so check these labels in your workspace |
| 4. Guided questions | With **Auto** on, answer the questions about what the agent does, what you want to learn and how the traces are structured. For TechHub: the customer's message is the last item of `inputs.messages`, and a conversation has one or two turns. The exact question labels are UNVERIFIED |
| 5. Run | **Run job** |
| 6. Read it in this notebook | Open the finished report from the **Insights** tab. Copy the `clusterJobId` value from its URL into `.env` as `M7_INSIGHTS_REPORT_ID`, restart the kernel and run this notebook again |

This notebook does not call `client.generate_insights`, the SDK method that starts a report. It takes `chat_histories` (lists of messages) instead of an existing project, uploads them as traces into a new project, and, if you pass a model key and the workspace has none, stores your key as a workspace secret that the evaluators and the Playground of that workspace can then use. To report on an existing project, use the UI, the LangSmith CLI (`langsmith insights create --project <name> --config insights.json`) or the REST endpoint `POST /api/v1/sessions/{session_id}/insights`.
'''),
    md('''
### What you did in code, and where it is in LangSmith

| Step in this notebook | Same step in the UI |
|---|---|
| `InsightsReportResult(**load_insights_report(seed))`, or `client.get_insights_report(...)` with your report id | The **Insights** tab of the project, then the report |
| `report.report.key_points`, `report.report.highlighted_traces` | The executive summary, with numbered links to traces |
| Clusters with `parent_id is None`, then the clusters under each | The category bars, then a click into a category |
| `apply_evaluator(...)` on one subcategory's conversations | The subcategory's traces table, read trace by trace |
| The example of §5, sent with `create_examples(...)` | **Add to Annotation Queue**, review, **Add to Dataset** |

## Recap

- Insights summarizes each conversation, groups the summaries into categories and subcategories, and reports error rate, latency and cost for each group. A report needs Plus or Enterprise, a provider key in the workspace and up to 30 minutes.
- In the sample report the largest category is Order status and tracking (78 conversations, 39%), and Where is my order has the highest error rate (19.6%), from the order-service outage.
- Silent failures show an error rate of 0.0%. Return window questions has 27 conversations, and the Section 1 evaluator flags 11 of them, all on 1.5.0.
- Categories and key points are model output. Check a claim against the traces, then send the traces to an annotation queue, review them, and keep the corrected ones as dataset examples.

**Next:** Section 3 reads an Engine issue board for the same day. The wrong return window is its issue 1.
'''),
]


# ============================================================================
# SECTION 3: Engine
# (see docs/2026-11-19-module-7-monitoring-governance-prd.md, section 9)
# ============================================================================
s3 = [
    md('''
# Module 7, Section 3: Engine

Section 1 found the 11 wrong return-window answers with an online evaluator. Section 2 saw the same failure as an Insights subcategory with an error rate of 0%. This section follows the failure into LangSmith Engine, which turns it into an issue to fix.

**LangSmith Engine reads the traces of a tracing project on a schedule and files recurring problems as issues, each with a diagnosis, the traces that support it and a proposed fix.** The docs describe a loop of five steps:

1. Detect a recurring issue in the traces.
2. Diagnose the root cause against the traces and any connected source code.
3. Propose a fix, as a pull request when a code repository is connected.
4. Track the issue: add new traces that match it, and generate dataset examples that verify a fix.
5. Reopen the issue when it comes back after it was closed.

The docs separate Engine from Insights in two sentences: "Use Insights to understand how people use your agent. Use Engine to find out what is going wrong and what to change."

In this section:
1. What Engine reads, and whether the TechHub traces carry it
2. The issue board, and one issue checked against its evidence
3. Triage: the next action for each issue
4. A test case with two assertions, built from the evidence
5. The proposed fix, and what would prove it
6. The same steps in LangSmith
'''),
    md('''
## Setup

This section calls no model and needs no key. Engine is not on every plan, so the core path reads a sample issue board that ships with the module. The board is hand-built from the seeded day and is not real Engine output. Its issues use the field names of the documented API.

Who can use Engine depends on how you reach LangSmith:

| Where you are | Turn Engine on for the organization | Start a scan of a project | Read issues, open evidence, add offline examples |
|---|---|---|---|
| Your own free organization (Developer plan) | No. Engine is not on the Developer plan, and personal organizations cannot use it | No | No. Use this notebook |
| A new workshop organization in which you are the Organization Admin | Yes | Yes. The first issues take up to 20 minutes | Yes, on your own issues once the scan has finished |
| A workspace in the facilitator's organization, with the default Editor role | No. An Organization Admin turns it on once for the whole organization | Yes, once the organization has Engine. Every attendee's scans count against one organization spend limit | Yes on your own project, or read-only on a board the facilitator prepared |
| No LangSmith key | No | No | This notebook, on the sample board |

Opening a pull request from an issue also needs a GitHub or GitLab repository connected to Engine. The facilitator shows that step.

If your organization has Engine and it has scanned your TechHub project, set `M7_ENGINE_ENABLED=true` in `.env`. The issue list of §2 then also reads your own issues. The exercises keep using the sample board, because its evidence traces are in the seed.
'''),
    SETUP,
    md('''
## 1. What Engine reads

Engine looks for three kinds of trace: traces that raise errors, traces that behave unusually, and traces that look normal and hold a problem, such as a wrong answer that raises no error. Feedback is a signal too. Engine uses scores from online evaluators and annotation queues, ratings from your users, and traces that someone flagged for Engine. You set nothing up for this, and feedback added after a trace ran still counts.

Three things on a trace help Engine:

| On the trace | Why Engine uses it |
|---|---|
| `revision_id` in the metadata | It ties each trace to the commit that produced it, so Engine can compare the commits between two releases. The SDK reads it from the environment variable `LANGSMITH_REVISION_ID` |
| Feedback keys | A score such as `wrong_return_window = 1` points Engine at a failure that raises no error |
| A run name and a metadata value that every trace carries | They define which traces Engine scans |

You can narrow a scan to at most two conditions: one **Run Name** and one **Metadata** condition. You cannot scope a scan by feedback key, evaluator name or score threshold.

The next cell checks whether the seeded TechHub day carries these signals.
'''),
    code('''
from collections import Counter
from utils.trace_seeding import root_runs

roots = root_runs(seed)
runs = seed["runs"]
for name in ("revision_id", "environment", "app_version"):
    values = Counter(run["extra"]["metadata"].get(name) for run in runs if name in run["extra"]["metadata"])
    print(f"{name:<12} on {sum(values.values()):,} of {len(runs):,} runs. Values: {', '.join(str(value) for value in sorted(values))}")
commits = {run["extra"]["metadata"]["app_version"]: run["extra"]["metadata"]["revision_id"] for run in roots}
print("Release and commit: " + "; ".join(f"{version} is commit {commit}" for version, commit in sorted(commits.items())))
print()

feedback = Counter(row["key"] for row in seed["feedback"])
print("Feedback keys in the seed: " + ", ".join(f"{key} ({count} scores)" for key, count in feedback.items()))
print("Section 1 adds wrong_return_window, the online evaluator's score. Engine reads both with no setup.")
print()

root_names = Counter(run["name"] for run in roots)
environments = Counter(run["extra"]["metadata"]["environment"] for run in runs)
print("A trace scope for Engine that fits these traces:")
for name, count in root_names.items():
    print(f"  Run Name is {name}        (the root run of all {count} traces)")
for value, count in environments.items():
    print(f"  environment is {value}     (on {count:,} of {len(runs):,} runs)")
'''),
    md('''
## 2. Read the issue board

Each issue on an Engine board has these fields in the API:

| Field | What it holds |
|---|---|
| `name`, `description` | A title, and the diagnosis in a few sentences |
| `severity` | `0` urgent, `1` high, `2` medium, `3` low. The UI calls it priority and offers Low, Medium and High |
| `status` | `open`, `fixing`, `watching`, `completed` or `ignored` |
| `type` | `actionable` (something can be fixed) or `finding` (an observation only). The default is `actionable` |
| `tags` | The failure category, such as `Silent tool error` or `Hallucination` |
| `proposed_fix` | The fix Engine proposes, as text. It can be missing |
| `fixes` | One entry per fix opened for the issue, newest first, each with a `branch` and a `pr_number` |

The SDK reads a board with `Client.list_project_issues(project_name)`, which returns a list of dictionaries. Its docstring lists keys such as `title`, `priority`, `category` and `trace_ids`. The current API has none of them, so read the fields of the table above, with `.get(...)`. The method also takes a `priority` argument, which the endpoint does not filter on: it returns every issue. This notebook filters and sorts in Python on `severity` and `status` instead.
'''),
    code('''
from utils.trace_seeding import SEVERITY_LABELS, load_engine_issues
from utils.trace_upload import new_client

ENGINE_ENABLED = os.getenv("M7_ENGINE_ENABLED") == "true"  # set it in .env when Engine has scanned your TechHub project
BOARD = load_engine_issues(seed)  # the sample board; its timestamps move with the seed

issues = None
if LANGSMITH_AVAILABLE and ENGINE_ENABLED:
    try:
        issues = new_client().list_project_issues(DEST.project_name)  # no priority argument: the endpoint does not filter on it
    except Exception as exc:  # noqa: BLE001 - any failure falls back to the sample board
        print(f"⏭️  Reading the issues failed ({type(exc).__name__}). Continuing with the sample board.")
    if issues == []:
        print("⏭️  Engine has filed no issue for this project yet. A first scan takes up to 20 minutes. Continuing with the sample board.")
        issues = None
    elif issues:
        print(f"Your board: {len(issues)} issues for project {DEST.project_name}. The exercises below use the sample board.")
if issues is None:
    reason = "LangSmith is not available" if not LANGSMITH_AVAILABLE else "M7_ENGINE_ENABLED is not true" if not ENGINE_ENABLED else "No issues from Engine"
    print(f"⏭️  {reason}: reading the sample issue board shipped with the module (hand-built from the seed, not real Engine output).")
    issues = BOARD["issues"]
print()


def issue_line(issue):
    severity = SEVERITY_LABELS.get(issue.get("severity"), "no severity")
    pull_requests = "".join(f"  PR {fix['pr_number']}" for fix in issue.get("fixes") or [] if fix.get("pr_number"))
    tags = ", ".join(issue.get("tags") or [])
    return f"[{severity}] {issue.get('status', 'no status'):<8} {issue.get('name', '(no name)')}  ({issue.get('type', 'actionable')}; {tags}){pull_requests}"


for issue in sorted(issues, key=lambda issue: issue.get("severity") if isinstance(issue.get("severity"), int) else 4):
    print(issue_line(issue))
'''),
    md('''
### Check issue 1 against its evidence

Issue 1 says that the product-policy specialist answers without calling `search_policy_docs`. A reviewer checks a claim like this before acting on it. In LangSmith, **Open trace** on an evidence item opens the trace at the child run that caused the issue. Here the next cell prints the issue, then one evidence trace beside a trace from release 1.4.0 that answered the same kind of question correctly.

> 💡 **Try it first:** in the two trees, which tool run is in the correct trace and missing from the evidence trace? Under which run should it be?
'''),
    code('''
import textwrap
from utils.monitoring_checks import check
from utils.trace_seeding import load_labels, trace_runs

ISSUES = sorted(BOARD["issues"], key=lambda issue: issue["severity"])
issue_1 = ISSUES[0]


def show(text, indent="    "):
    print(textwrap.fill(text, width=100, initial_indent=indent, subsequent_indent=indent))


print(f"Issue 1: {issue_1['name']}")
print(f"  severity {issue_1['severity']} ({SEVERITY_LABELS[issue_1['severity']]}), status {issue_1['status']}, "
      f"type {issue_1['type']}, tags {', '.join(issue_1['tags'])}, {len(issue_1['fixes'])} fixes")
print("  Description")
show(issue_1["description"])
print("  Proposed fix")
show(issue_1["proposed_fix"])
print("  Evidence")
for item in BOARD["evidence"][issue_1["id"]]:
    show(f"{item['seed_trace_key']}: {item['comment']}")
print()

# The label file holds the ground truth of each conversation. It exists only because the data is
# synthetic. Here it finds a 1.4.0 conversation about an opened product, which got the right answer.
labels = load_labels()
evidence_key = BOARD["evidence"][issue_1["id"]][0]["seed_trace_key"]
correct_key = next(
    c["trace_keys"][0] for c in labels["conversations"]
    if c["topic"] == "return_window" and c["app_version"] == "1.4.0" and (c.get("details") or {}).get("item_condition") == "opened"
)
print("Evidence trace:")
print_trace(seed, evidence_key)
print()
print("A correct answer to the same kind of question:")
print_trace(seed, correct_key)
print()


def tools_by_specialist(key):
    """The tool runs inside each specialist run of one trace: {specialist name: [tool names]}."""
    members = trace_runs(seed, key)
    by_id = {run["id"]: run for run in members}
    found = {run["name"]: [] for run in members if by_id.get(run["parent_run_id"], {}).get("name") == "task"}
    for run in members:
        if run["run_type"] != "tool":
            continue
        parent = by_id.get(run["parent_run_id"])
        while parent is not None and parent["name"] not in found:
            parent = by_id.get(parent["parent_run_id"])
        if parent is not None:
            found[parent["name"]].append(run["name"])
    return found


correct_tools, evidence_tools = tools_by_specialist(correct_key), tools_by_specialist(evidence_key)
missing = [(agent, tool) for agent, tools in correct_tools.items() for tool in tools if tool not in evidence_tools.get(agent, [])]
for agent, tool in missing:
    print(f"{tool} runs under {agent} in {correct_key} and is missing from {evidence_key}.")
under_run, missing_tool = missing[0]
ok, message = check("s3_evidence", {"missing_tool": missing_tool, "under_run": under_run})
print(message)
'''),
    md('''
## 3. Triage

Every issue needs a decision from a person. This notebook uses four action codes:

| Action code | In LangSmith | When |
|---|---|---|
| `apply_fix_and_add_examples` | **Open PR**, or copy the fix for a coding assistant, then **Add offline examples** | The issue is a real problem and nobody has started on it |
| `review_pull_request` | **View PR** | A fix is in flight: the status is `fixing` and a pull request exists |
| `save_for_later` | **Watch** in the docs pages, **Save for later** in the changelog | The issue is a finding: the answers are correct and there is nothing to fix now |
| `close_incorrectly_flagged` | **Close** > **Incorrectly Flagged** | A person read the evidence and the agent behaved correctly. No field of an issue says that, so a rule on fields never picks it |

Severity sets the order in which you work through the issues and plays no part in the choice of action.

Your decisions also teach Engine. On each scan, Engine turns the reviewer's recent actions into rules in the **User Preferences** section of its agent overview. Closing an issue or marking it **Incorrectly Flagged** lowers the priority of that category. Changing the priority records the severity you meant. Opening a pull request records that the category is worth fixing. Engine does not learn from automation, such as a pull request that merges, or from actions taken through LangSmith Chat.

The labels are moving. The docs pages say **Watch** and **Close**. The changelog renamed **Watch** to **Save for later** and replaced the single close button with a **Close** menu (**Done**, **Not Important**, **Incorrectly Flagged**). Use the label you see.

> 💡 **Try it first:** write `next_action(issue)` in `workshop_modules/module_7/exercises/triage.py`. It returns one of the four codes from the issue's fields. Check it from the repository root with `uv run python workshop_modules/module_7/exercises/check.py s3_triage`. The next cell holds the reference rule.
'''),
    code('''
from utils.monitoring_checks import TRIAGE_CASES


def next_action(issue):
    """The next action for one issue, decided from its type, status and fixes."""
    if issue.get("type") == "finding":
        return "save_for_later"  # an observation: the answers are correct
    if issue.get("status") == "fixing" and issue.get("fixes"):
        return "review_pull_request"  # a fix is already in flight
    return "apply_fix_and_add_examples"  # a real problem that nobody has started on


for number, board_issue in enumerate(ISSUES, start=1):
    fixes = board_issue.get("fixes") or []
    print(f"Issue {number}: type {board_issue['type']}, status {board_issue['status']}, {len(fixes)} in fixes: {next_action(board_issue)}")
print()
print("Two extra cases the checker also runs:")
for what, extra_issue, expected, why in TRIAGE_CASES:
    print(f"  {what}: {next_action(extra_issue)}")
print()
ok, message = check("s3_triage", next_action)
print(message)
'''),
    md('''
## 4. Turn evidence into test cases

An issue's evidence can become test cases for a dataset. In LangSmith, **Add offline examples** at the top right of the **Evidence** list opens a dialog with the input, the wrong output the agent produced and a proposed expected output. **Add to Dataset** adds the examples directly. **Edit in annotation queue** lets a person review them first. In the queue, the reference output of each example is a list of named assertions. **An assertion is a short claim about what a correct answer should or should not include.** You edit them, add more with **+ Add assertion**, then click **Add to Dataset & Continue**. LangSmith attaches its Assertions evaluator when the examples are saved this way.

A useful assertion holds for the corrected answer and fails for the answer the agent recorded. An assertion that holds for both would not have caught the wrong answer. One that fails for the corrected answer would fail a correct agent.

> 💡 **Try it first:** the next cell prints the recorded answer, the corrected answer and six candidate assertions. Pick the two that hold for the corrected answer and fail for the recorded one, and write their keys in `MY_ASSERTIONS` before you run the cell.
'''),
    code('''
from utils.monitoring_checks import ASSERTION_CANDIDATES, assertion_case, assertion_table

case = assertion_case(seed, BOARD)  # the trace that the sample board proposes as an offline example for issue 1
print(f"Trace {case['trace_key']}")
print("Customer:          " + case["question"])
print("Recorded answer:   " + case["recorded_answer"])
print("Corrected answer:  " + case["corrected_answer"])
print()
print("Candidate assertions:")
for candidate in ASSERTION_CANDIDATES:
    print(f"  {candidate['key']:<28} {candidate['comment']}")
print()

MY_ASSERTIONS = None  # your two keys, for example ["key_one", "key_two"]. None lets the table below pick them
table = assertion_table(case)  # each candidate tried on both answers; a wording check stands in for a judge
picked = MY_ASSERTIONS if MY_ASSERTIONS is not None else [row["key"] for row in table if row["separates"]]
if MY_ASSERTIONS is None:
    print("MY_ASSERTIONS is None, so the cell picks the rows that hold for the corrected answer and fail for the recorded one.")
ok, message = check("s3_assertions", picked)
print(message)
print()
print(f"  {'assertion':<28} {'recorded':<10} {'corrected':<10}")
for row in table:
    print(f"  {row['key']:<28} {'holds' if row['holds_for_recorded'] else 'fails':<10} {'holds' if row['holds_for_corrected'] else 'fails':<10}")
print()

example = {
    "inputs": {"messages": [{"role": "user", "content": case["question"]}]},
    "outputs": {
        "messages": [{"role": "assistant", "content": case["corrected_answer"]}],
        "assertions": [{"key": c["key"], "comment": c["comment"]} for c in ASSERTION_CANDIDATES if c["key"] in picked],
    },
    "metadata": {"source": "module_7_section_3", "seed_trace_key": case["trace_key"], "synthetic": True},
}
print("The offline example:")
print(json.dumps(example, indent=2))
print()

DATASET_NAME = "techhub-deep-agent-regressions"
CREATE_DATASET = False  # set to True (with a key) to add the example to the dataset
if CREATE_DATASET and LANGSMITH_AVAILABLE and ok:
    try:
        client = new_client()
        if not client.has_dataset(dataset_name=DATASET_NAME):
            client.create_dataset(DATASET_NAME, description="TechHub deep agent: answers corrected by reviewers (Module 7).")
        # Re-running adds nothing, and neither does Section 2's example: both are matched on seed_trace_key.
        if list(client.list_examples(dataset_name=DATASET_NAME, metadata={"seed_trace_key": case["trace_key"]}, limit=1)):
            print(f"{DATASET_NAME} already has an example from trace {case['trace_key']}. Nothing was added.")
        else:
            client.create_examples(dataset_name=DATASET_NAME, examples=[example])
            print(f"Added the example to {DATASET_NAME}.")
    except Exception as exc:  # noqa: BLE001 - the example is printed above, so a failure loses nothing
        print(f"⏭️  Adding the example failed ({type(exc).__name__}). Add it in the UI with the steps of §6.")
else:
    print(f"⏭️  Not added. With a key and CREATE_DATASET = True, this cell adds the example to {DATASET_NAME}.")
'''),
    md('''
## 5. The proposed fix, and what would prove it

Release 1.5.0 added one sentence to the product-policy specialist's instructions, and issue 1 proposes to remove it. The next cell prints both. Who applies the fix depends on where it lives:

| Where the fix lives | What Engine does |
|---|---|
| Code, in a connected GitHub or GitLab repository | **Open PR** opens a pull request, and the button becomes **View PR**. Code fixes as pull requests are for agents built with Deep Agents, LangChain or LangGraph |
| Instructions or skills in a connected Context Hub repository | Engine stores the change as a proposal. It changes nothing until a signed-in user with write access to that repository applies it |
| No repository connected | The proposed fix is text. You can copy the fix context into a coding assistant |

Engine never merges. Every pull request goes through your own review and branch protection rules.

Before a fix ships, prove it offline. That is the job of Workshop 8: the Harbor task `managed_agent/evals/opened-item-return-window` asks about an opened keyboard delivered 20 days ago and passes when the answer cites the 14-day window and says no. This notebook does not run the agent again.

After the fix ships, Engine keeps linking new traces to the issue on its later scans, and reopens a closed issue when the failure comes back. You cannot force a scan: there is no run-now action. The online evaluator of Section 1 gives you an answer sooner, and its scores are one of the signals Engine reads.

**120-minute path:** the next cell runs that evaluator over two small follow-up sets of 10 traces each, the same 10 questions answered before and after the fix.
'''),
    code('''
from evaluators import wrong_return_window_evaluator
from utils.monitoring_local import apply_evaluator, flagged_trace_keys
from utils.trace_seeding import PLANTED_INSTRUCTION, load_followups

print("Release 1.5.0 added this sentence to the product-policy specialist's instructions:")
show(PLANTED_INSTRUCTION)
print("Issue 1 proposes:")
show(issue_1["proposed_fix"])
print()

# Two synthetic sets made by the seed generator. Release 1.5.1 and its commit id are invented, like the others.
followups = load_followups(seed)
for label, title in (("before_fix", "Before the fix"), ("after_fix", "After the fix")):
    part = followups[label]
    part_roots = root_runs(part["runs"])
    flagged = flagged_trace_keys(apply_evaluator(wrong_return_window_evaluator, part_roots))
    print(f"{title}: app_version {part['app_version']} (commit {part['revision_id']}), {len(part_roots)} traces, "
          f"{len(flagged)} flagged wrong_return_window = 1" + (f": {', '.join(flagged)}" if flagged else ""))
print()
print("One question about an opened product, answered after the fix:")
print_trace(followups["after_fix"]["runs"], "fa-01")
'''),
    md('''
## 6. In the product

If your organization has Engine, follow these steps on your own project. Otherwise the facilitator shows them on a prepared project. The labels come from the LangSmith docs and can differ a little in your workspace.

| Step | In the UI |
|---|---|
| 1. Open your TechHub traces | ''' + NAV_SHORT + ''' |
| 2. Open Engine | **Engine** in the sidebar, or the **Engine** tab of the tracing project. An Organization Admin first turns on **Enable Engine** under **Settings** > **Engine** |
| 3. Pick the project | **+ Set up another project**, then your TechHub project under **Choose a project to analyze**. Connecting a code repository is optional |
| 4. Analysis level | **Reduced**, **Standard** (the default) or **Expanded** |
| 5. Scope | Under **Focus on specific traces**: `Run Name is deep_support_agent` and `environment is production`, the two conditions of §1 |
| 6. Start | **Start Analyzing**. Engine first writes an agent overview document; review it, then click **Accept & Continue** |
| 7. Read an issue | Open it. Read the diagnosis, **Feedback cited by Engine**, **Evidence** and **Proposed Fix**, then **Open trace** on an evidence item |
| 8. Make test cases | **Add offline examples**, then **Add to Dataset** or **Edit in annotation queue** |
| 9. Point Engine at a trace | On any trace, **Flag for Engine**, with a note. Engine reviews flagged traces on its next scan |

Facts to know before you turn it on:

- An Organization Admin enables Engine once for the organization. It is on the Plus and Enterprise plans.
- The first scan takes up to 20 minutes, and there is no action that starts a scan now.
- Engine bills in LangChain Standard Units (LSUs). One LSU costs 1 US dollar, and one run uses about 7 to 45 LSUs. An organization that has never set a limit is capped at 750 LSUs a month. Set a spend limit under **Spend limit** in the Engine settings, and use **Pause** to stop the scans of a project.
- On LangSmith Cloud, Engine uses LangChain-managed models. A self-hosted installation can use LangChain-managed models only on AWS in the US; with your own model providers it runs on any cloud.
- Trace content sent to Engine can include user messages, tool outputs and personal data. The docs recommend masking sensitive data in the client before it is traced, which is the first lab of Section 4.
- Whether Engine analyses traces uploaded with past timestamps, such as the seeded day, is UNVERIFIED.
'''),
    md('''
### What you did in code, and where it is in LangSmith

| Step in this notebook | Same step in the UI |
|---|---|
| Counting `revision_id`, `environment` and the root run name | **Focus on specific traces** in the setup panel |
| `client.list_project_issues(DEST.project_name)`, or the sample board | The **Engine** page, with **Filter issues** and **Sort issues** |
| `print_trace(...)` on an evidence trace and a correct one | **Open trace** on an evidence item |
| `next_action(issue)` | **Open PR**, **View PR**, **Watch** (**Save for later**) or **Close** |
| `MY_ASSERTIONS` and the offline example | **Add offline examples** > **Edit in annotation queue** > **+ Add assertion** |
| `apply_evaluator(...)` on the follow-up sets | The online evaluator of Section 1, whose scores Engine reads |

## Recap

- Engine reads traces and their feedback, files recurring failures as issues with evidence and a proposed fix, and reopens an issue when the failure comes back. An Organization Admin turns it on, on a Plus or Enterprise plan.
- Issue 1's evidence holds up: in the 1.5.0 trace the product-policy specialist answers without calling `search_policy_docs`, and the correct 1.4.0 trace calls it.
- Triage reads `type`, `status` and `fixes`: issue 1 needs the fix and test cases, issue 2 has pull request 42 to review, and issue 3 is a finding to save for later. Severity only sets the order.
- The test case keeps the two assertions that separate the answers, `states_14_day_window` and `no_30_day_claim`. The Section 1 evaluator flags 4 of 10 follow-up traces before the fix and 0 after it.

**Next:** Section 4 finds the email address stored in one seeded trace, masks it before upload, and reads the LLM Gateway's policy blocks.
'''),
]


# ============================================================================
# SECTION 4: LLM Gateway and governance
# (see docs/2026-11-19-module-7-monitoring-governance-prd.md, section 10)
# ============================================================================
s4 = [
    md('''
# Module 7, Section 4: LLM Gateway and Governance

Sections 1 to 3 found problems after they happened. This section is about controls that stop some of them from happening at all. The LangSmith docs describe this part of governance as what agents do at runtime: spend and data protection policies on model calls, block and approval policies on tool calls, sandboxed execution for agent code, and human approval before sensitive actions.

Module 4 Section 2 added `PIIMiddleware` to the deep support agent and ended with this warning:

> ⚠️ **Traces are a separate control.** `PIIMiddleware` rewrites the conversation state, but the raw run input and each span's raw output are still recorded in LangSmith. To keep PII out of traces, add LangSmith's trace masking (hide or anonymize inputs and outputs) as well.

This section measures that gap and closes it.

In this section:
1. An email address that a customer typed, still in yesterday's traces
2. Three controls for personal data, and where each one runs
3. Proof of what leaves the process, with masking off and on
4. The LLM Gateway, and how a model call finds it
5. What a policy block looks like to the agent
6. Which control stops which of the day's five incidents
7. Who did what: traces, the audit log, roles and Custom Apps
8. Where to go next
'''),
    md('''
## Setup

Everything in this section runs with no key and calls no model. The agents in §3 use a scripted model, and their traces go to a recorder on this machine. One optional cell in §7 calls the LLM Gateway for real; it is off unless you turn it on.
'''),
    SETUP,
    md('''
## 1. An email address in yesterday's traces

In one conversation of the seeded day, a customer typed an email address into the chat. `PIIMiddleware` was on, as it is by default in the deep support agent. The next cell searches the inputs and outputs of every root run for an email address.

With a key, and with the day uploaded in Section 1, you can open the same trace in LangSmith:

> ''' + NAV_FULL + '''
'''),
    code('''
import re
from utils.monitoring_checks import check
from utils.trace_seeding import EMAIL_PATTERN, load_labels, question_text, root_runs, trace_key

EMAIL = re.compile(EMAIL_PATTERN)
roots = root_runs(seed)
in_inputs = [run for run in roots if EMAIL.search(json.dumps(run["inputs"]))]
in_outputs = [run for run in roots if EMAIL.search(json.dumps(run["outputs"] or {}))]
leaked = {trace_key(run) for run in in_inputs + in_outputs}
print(f"{len(leaked)} root run contains a raw email address: {len(in_inputs)} in its inputs, {len(in_outputs)} in its outputs.")

labels = load_labels()
topic = {key: c["topic"] for c in labels["conversations"] for key in c["trace_keys"]}
for run in in_inputs:
    key = trace_key(run)
    saved = run["outputs"]["messages"][0]["content"]  # the same customer message, as the conversation state kept it
    print()
    print(f"{key} (topic {topic[key]}, app_version {run['extra']['metadata']['app_version']})")
    print("  inputs.messages[0].content: ", question_text(run))
    print("  outputs.messages[0].content:", saved)
    print(f'  In the LangSmith search bar: and(eq(metadata_key, "seed_trace_key"), eq(metadata_value, "{key}"))')
print()

ok, message = check("s4_leak", {
    "root_runs_with_raw_email": len(leaked),
    "in_inputs": len(in_inputs),
    "in_outputs": len(in_outputs),
})
print(message)
'''),
    md('''
## 2. Three controls, three places

The middleware did its job: the model and the saved conversation only ever saw `[REDACTED_EMAIL]`. The root run's inputs are recorded before the middleware runs, so the trace still holds what the customer typed. Three controls deal with personal data, and each one protects a different copy of it.

| | `PIIMiddleware` (LangChain) | Gateway data policy (LangSmith) | Client-side trace masking (LangSmith SDK) |
|---|---|---|---|
| Where it runs | In your agent process, around each model call | In the LLM Gateway, between your process and the model provider | In your process, just before a trace is uploaded |
| Who sets it up | The developer, in code | An organization admin, in the UI, with no code change | The developer, with `Client(anonymizer=...)`, `hide_inputs` or an environment variable |
| What it protects | What the model sees, and the saved conversation | What the model provider sees, and what the `gateway` trace stores | What LangSmith stores in your application's traces |
| Does the model see the original? | No | No: it gets placeholders, and the Gateway restores the values in the response | Yes |
| Does your own LangSmith trace keep the original? | Yes: the root input, the middleware's own spans and the raw model output | Yes: your application receives the restored values | No |
| Gaps | One PII type per middleware instance. Subagents do not inherit it | Scans requests, not responses. Skips system prompts. Needs a PII redaction entitlement that is off by default | Run names, tags and attachments are not masked |

A fourth control exists on the Enterprise plan: the permissions `runs:read-inputs` and `runs:read-outputs`, and an access policy that hides inputs and outputs in projects with a given tag. The data is stored, and selected users cannot read it.
'''),
    md('''
## 3. Prove what leaves the process

The next cells trace a small agent into a **capture client**: a LangSmith client whose HTTP layer records each upload and answers it on this machine. Nothing leaves the machine, and no key is needed. `utils/offline_capture.py` has the code.

The agent is built with `create_agent`, the same function the deep support agent is built on, with no tools and a scripted model that returns one prepared reply. The customer's message holds an email address and an order id. The order id is the control string: it is not personal data, so masking must leave it alone.

Run 1 has `PIIMiddleware` for email on input and output, as in the deep support agent, and no masking in the client.
'''),
    code('''
from langchain.agents import create_agent
from langchain.agents.middleware import PIIMiddleware
from langsmith import tracing_context
from utils.monitoring_checks import MASKING_CONTROL, MASKING_EMAIL, MASKING_QUESTION, MASKING_REPLY
from utils.offline_capture import count_payloads_containing, offline_client, scripted_model, uploaded_payloads


def email_middleware():
    return PIIMiddleware("email", strategy="redact", apply_to_input=True, apply_to_output=True)


def run_once(middleware, **client_kwargs):
    """Run the agent once, traced into a capture client. Returns the final state and the capture."""
    agent = create_agent(scripted_model([MASKING_REPLY]), tools=[], middleware=middleware)
    client, capture = offline_client(**client_kwargs)
    with tracing_context(enabled=True, client=client):
        state = agent.invoke({"messages": [{"role": "user", "content": MASKING_QUESTION}]})
    client.flush()
    return state, capture


def leak_line(label, capture):
    total = len(uploaded_payloads(capture))
    return f"{label}: {count_payloads_containing(capture, MASKING_EMAIL)} of {total} uploaded payloads contain {MASKING_EMAIL}."


state, run1 = run_once([email_middleware()])
print("Final conversation state:")
for message in state["messages"]:
    print(f"  {message.type}: {message.content}")
print()
print(leak_line("Run 1, middleware only", run1))
where = sorted({(payload.get("name"), part) for payload in uploaded_payloads(run1)
                for part in ("inputs", "outputs") if MASKING_EMAIL in json.dumps(payload.get(part))})
for name, part in where:
    print(f"  {name}: {part}")
'''),
    md('''
The model and the conversation state saw `[REDACTED_EMAIL]`, yet most uploaded payloads still hold the address. The list shows where: the root run's inputs (`LangGraph`), the inputs of the middleware's own `before_model` and `after_model` spans, and the raw model output before the middleware rewrote it. Each run is uploaded twice, once when it starts and once when it ends, so one run can count twice. On our runs this was 8 of 10. The exact count depends on the installed LangChain version.

An **anonymizer** is a function that the LangSmith client applies to the inputs, outputs, metadata and error of every run just before upload. `langsmith.anonymizer.create_anonymizer` builds one from a list of rules of the form `{"pattern": <regular expression>, "replace": <text>}`.

> 💡 **Try it first:** write `build_anonymizer()` in `workshop_modules/module_7/exercises/masking.py` so that no uploaded payload contains an email address and the order id survives. Check it from the repository root with `uv run python workshop_modules/module_7/exercises/check.py s4_masking`. The next cell shows the reference version.
'''),
    code(r'''
from langsmith.anonymizer import create_anonymizer


def build_anonymizer():
    """Replace every email address with <email> and leave all other text alone."""
    email = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
    return create_anonymizer([{"pattern": email, "replace": "<email>"}])


# Run 2: the same middleware, and a client that masks before upload.
state2, run2 = run_once([email_middleware()], anonymizer=build_anonymizer())
print(leak_line("Run 2, middleware and anonymizer", run2))
control_before = count_payloads_containing(run1, MASKING_CONTROL)
control_after = count_payloads_containing(run2, MASKING_CONTROL)
print(f"  The order id {MASKING_CONTROL} is in {control_before} payloads in run 1 and {control_after} in run 2: unchanged.")

# Run 3: the anonymizer alone, no middleware.
state3, run3 = run_once([], anonymizer=build_anonymizer())
print(leak_line("Run 3, anonymizer only", run3))
print("  What the model received:", state3["messages"][0].content)
print()

ok, message = check("s4_masking", build_anonymizer)
print(message)
'''),
    code('''
from langchain_core.runnables import RunnableLambda
from utils.offline_capture import hide_inputs_in_subprocess

# Trap 1: LANGSMITH_HIDE_INPUTS, one new Python process per spelling, because the SDK caches the first value it reads.
hidden = {value: hide_inputs_in_subprocess(value)["uploaded_inputs"] == {} for value in ("true", "True", "1")}

# Trap 2: tracing_context(enabled="local") still uploads the runs of a LangChain runnable.
probe = RunnableLambda(lambda inputs: {"answer": "It shipped."}, name="probe")
uploads = {}
for setting in ("local", False):
    client, capture = offline_client()
    with tracing_context(enabled=setting, client=client):
        probe.invoke({"question": "Where is order ORD-2025-0050?"})
    client.flush()
    uploads[setting] = len(uploaded_payloads(capture))

# Trap 3: calling an anonymizer on your own dictionary changes that dictionary.
note = {"note": f"Copy {MASKING_EMAIL} on order {MASKING_CONTROL}."}
result = build_anonymizer()(note)

rows = [
    ("LANGSMITH_HIDE_INPUTS=true, =True, =1", "Inputs hidden for all three",
     "Hidden for " + ", ".join(v for v, h in hidden.items() if h) + "; not hidden for " + ", ".join(v for v, h in hidden.items() if not h)),
    ('tracing_context(enabled="local")', "Nothing is uploaded",
     f'{uploads["local"]} payloads uploaded ({uploads[False]} with enabled=False)'),
    ("anonymizer(my_dict)", "Returns a masked copy",
     f"Returns the same object: {result is note}; my_dict is now {note}"),
]
print(f"{'Setting':<40} {'What you expect':<28} What happens")
for setting, expected, happened in rows:
    print(f"{setting:<40} {expected:<28} {happened}")
'''),
    md('''
The three traps:

- The SDK compares the variable with the exact string `true`. `True` and `1` hide nothing and raise no warning.
- `"local"` keeps a `@traceable` function on the machine, but LangChain runnables still attach their tracer and upload. With a real key, an agent wrapped in `tracing_context(enabled="local")` sends every run. Use `enabled=False` to trace nothing, or an anonymizer to trace with masking.
- Inside the client the anonymizer works on a copy, so this is harmless there. To try an anonymizer on your own data, pass a copy.

## 4. The LLM Gateway: one control layer

The **LLM Gateway** is a LangSmith endpoint in front of the model providers. Your application sends a LangSmith API key, and LangSmith holds the provider keys as workspace secrets. The Gateway is in beta, so labels and behaviour can still change.

For each request, the Gateway:

1. Authenticates the caller from the LangSmith API key and checks the `gateway:invoke` permission.
2. Resolves the route from the endpoint and the model ID, including fallback models.
3. Loads the provider credential (a workspace provider key, or Gateway Credits).
4. Applies the policies: spend, rate and model access policies can block the request, and a data policy redacts it.
5. Translates the request if the provider uses another API format.
6. Sends the request to the provider.
7. Translates the response back and restores redaction placeholders where it applies.
8. Returns the response and records usage, cost, the policy decisions and a trace in the project `gateway`.

LangChain uses direct model access, which skips steps 5 and 7.

There are three routes to the Gateway, and they name models differently:

| Route | What you set | Base URL | Model name |
|---|---|---|---|
| A. LangChain and Deep Agents switch | `LANGSMITH_GATEWAY=true` and `LANGSMITH_API_KEY` (or `LANGSMITH_GATEWAY_API_KEY`) | `https://gateway.smith.langchain.com/openai/v1` for `ChatOpenAI`, `https://gateway.smith.langchain.com/anthropic` for `ChatAnthropic` | Native: `openai:gpt-5.4` |
| B. Standard endpoint, for any OpenAI- or Anthropic-compatible client | The base URL, with the LangSmith key as the client's API key | `https://gateway.smith.langchain.com/v1` | `<provider>/<model>`, such as `openai/gpt-5.4-mini` |
| C. The `langsmith:` provider of `init_chat_model` | `init_chat_model("langsmith:openai/gpt-5.4")` | `https://gateway.smith.langchain.com/v1` | `<provider>/<model>` |

This repo uses route A in `config.py` and route C in `managed_agent/model.py`. The next cell builds two models under five environments and prints where each would send its calls. It never calls them.
'''),
    code('''
from unittest import mock
from langchain.chat_models import init_chat_model

DUMMY = {  # placeholder values, so the cell can tell which variable a model took its key from
    "LANGSMITH_API_KEY": "dummy-langsmith-key",
    "LANGSMITH_GATEWAY_API_KEY": "dummy-gateway-key",
    "OPENAI_API_KEY": "dummy-openai-key",
    "ANTHROPIC_API_KEY": "dummy-anthropic-key",
}
ENVIRONMENTS = {
    "LANGSMITH_GATEWAY=true, LANGSMITH_API_KEY": {"LANGSMITH_GATEWAY": "true", "LANGSMITH_API_KEY": DUMMY["LANGSMITH_API_KEY"]},
    "... plus LANGSMITH_GATEWAY_API_KEY": {"LANGSMITH_GATEWAY": "true", "LANGSMITH_API_KEY": DUMMY["LANGSMITH_API_KEY"],
                                           "LANGSMITH_GATEWAY_API_KEY": DUMMY["LANGSMITH_GATEWAY_API_KEY"]},
    "LANGSMITH_GATEWAY=true and provider keys": {"LANGSMITH_GATEWAY": "true", "LANGSMITH_API_KEY": DUMMY["LANGSMITH_API_KEY"],
                                                 "OPENAI_API_KEY": DUMMY["OPENAI_API_KEY"], "ANTHROPIC_API_KEY": DUMMY["ANTHROPIC_API_KEY"]},
    "LANGSMITH_GATEWAY=<EU host>": {"LANGSMITH_GATEWAY": "https://eu.gateway.smith.langchain.com", "LANGSMITH_API_KEY": DUMMY["LANGSMITH_API_KEY"]},
    "No LANGSMITH_GATEWAY, provider keys": {"OPENAI_API_KEY": DUMMY["OPENAI_API_KEY"], "ANTHROPIC_API_KEY": DUMMY["ANTHROPIC_API_KEY"]},
}


def key_source(secret):
    value = secret.get_secret_value() if secret else None
    return next((name for name, dummy in DUMMY.items() if dummy == value), "none")


routes = {}
for label, environment in ENVIRONMENTS.items():
    with mock.patch.dict(os.environ, environment, clear=True):  # only these variables, and only inside this block
        openai_model = init_chat_model("openai:gpt-5.4")
        anthropic_model = init_chat_model("anthropic:claude-haiku-4-5")
    routes[label] = str(openai_model.root_client.base_url).rstrip("/")
    print(label)
    print(f"  openai:gpt-5.4              -> {routes[label]}  (key from {key_source(openai_model.openai_api_key)})")
    print(f"  anthropic:claude-haiku-4-5  -> {anthropic_model.anthropic_api_url.rstrip('/')}  (key from {key_source(anthropic_model.anthropic_api_key)})")
print()

ok, message = check("s4_routes", routes["LANGSMITH_GATEWAY=true and provider keys"])
print(message)
'''),
    md('''
With `LANGSMITH_GATEWAY=true` set, calls go to the Gateway with the Gateway key even when provider keys are set too. The repo README says "provider keys win if several are set", and `config.py` then reports the credential source as `environment`. For this case both are wrong: to know where a model sends its calls, read the base URL of the model you built.

## 5. What a policy block looks like

There are five policy types. All are created on tabs of the **LLM Gateway** page, and creating any of them needs the permission `organization:gateway:manage`, which Organization Admins and Organization Operators have. That is why the facilitator creates policies and you read the blocks.

| Policy | Where it is created | Scopes | When it blocks | What the caller gets |
|---|---|---|---|---|
| Spend limit | **Cost Controls** | Organization, workspace, user or API key | Recorded spend in the window (month, week, day or hour) reaches the cap | `402` |
| Rate limit | **Rate limiting** | Same | Requests or tokens in a rolling minute or hour exceed the limit | `429` with a `Retry-After` header |
| Model access | **Model Access** | Same | The provider or model is not on the list | `403`, and the model is missing from `GET /v1/models` |
| Data policy | **Data Policy** | Same | Never, except when a scan times out and **On timeout** is **Block request** | Normally nothing: the request is redacted on the way to the provider |
| Header-based | A condition on one of the policies above | A value of an `X-Gateway-*` request header | As that policy | As that policy |

Every block body contains `request blocked by gateway policies: <policy name>`, and the blocked request is still traced in the project `gateway`.

> 💡 **Try it first:** the next cell replays three saved Gateway responses through `ChatOpenAI`. Before you run it, say which policy type each status code comes from, and which of the three the agent's retry middleware retries.
'''),
    code('''
import ast
from utils.offline_capture import gateway_replay

# What each status means, from the policy table above (LangSmith docs).
POLICY_BY_STATUS = {402: "spend_limit", 429: "rate_limit", 403: "model_access"}

blocks = {}
for kind in ("spend", "rate", "model_access"):
    try:
        gateway_replay(kind).invoke("ping")  # a ChatOpenAI whose HTTP layer returns the saved response; nothing is sent
    except Exception as exc:  # noqa: BLE001 - every replay ends in the exception LangChain raises for that status
        policy = re.search(r'request blocked by gateway policies: [^"]+', exc.response.text).group(0)
        retry_after = exc.response.headers.get("Retry-After")
        print(f"{exc.status_code}  {type(exc).__name__:<22} Retry-After: {retry_after or '-':<3} {policy}")
        blocks[str(exc.status_code)] = {"policy_type": POLICY_BY_STATUS[exc.status_code], "exception": type(exc).__name__}
print()

# The line of agents/middleware/fault_tolerance.py that decides what ModelRetryMiddleware retries (copied when the notebook was built).
TRANSIENT_LINE = ''' + repr(TRANSIENT_STATUSES_LINE) + '''
transient = ast.literal_eval(TRANSIENT_LINE.split("=", 1)[1].strip())
print("agents/middleware/fault_tolerance.py:", TRANSIENT_LINE)
retried = sorted(int(status) for status in blocks if int(status) in transient or int(status) >= 500)
print("Of the three blocks, the agent retries:", ", ".join(str(status) for status in retried))
print()

ok, message = check("s4_blocks", {**blocks, "retried_statuses": retried})
print(message)
'''),
    md('''
### A spend cap is not a pre-check

The Gateway records a request's cost after the request completes. The request that crosses the cap still succeeds, and only later requests are blocked, so spend in a window can end up above the cap.

What the TechHub deep agent does on each block, from the source of `agents/middleware/fault_tolerance.py` and the OpenAI SDK (not run against a live Gateway, so UNVERIFIED end to end):

- `429`: the OpenAI SDK retries it twice by default before it raises. Then `ModelRetryMiddleware` retries it (408, 409, 429 and every 5xx status count as transient), and after that `ModelFallbackMiddleware` tries the fallback models.
- `402` and `403`: no retry. The agent goes straight to the fallback models.
- Fallback models called with the same key or in the same workspace fall under the same policy, so they are blocked too, and the run ends with the error.

A rate-limit block never reaches the provider, so it does not start a Gateway fallback chain either, even though `429` is one of the default fallback triggers.

A policy scoped to an API key caps the whole agent. To cap one end customer, the backend sends a header such as `X-Gateway-Customer-Id` after it has authenticated the customer, and a spend limit is separated by that header. The Gateway trusts these headers, so only your backend may set them.

The next cell (120-minute path) estimates who spent what in the seeded day and plays the day's model calls against a daily cap.
'''),
    code('''
from statistics import median
from utils.monitoring_local import cost_of, spend_by
from utils.trace_seeding import ILLUSTRATIVE_PRICES_PER_1M, runs_by_trace

PRICES = dict(ILLUSTRATIVE_PRICES_PER_1M)  # dollars per 1 million tokens; round numbers invented for this lab, not a price list
print("Illustrative prices per 1M tokens:", ", ".join(f"{model} {p['input']:g} in / {p['output']:g} out" for model, p in PRICES.items()))

spend = spend_by(seed, "customer_id", PRICES)
total = sum(spend.values())
print(f"Estimated spend for the day: ${total:.2f}")
print("Top customers:", ", ".join(f"{customer} ${amount:.2f}" for customer, amount in list(spend.items())[:3]))

trace_cost = {key: sum(cost_of(run, PRICES) for run in runs) for key, runs in runs_by_trace(seed).items()}
per_conversation = {}
for conversation in labels["conversations"]:
    per_conversation.setdefault(conversation["subcategory"], []).append(sum(trace_cost[key] for key in conversation["trace_keys"]))
by_median = sorted(per_conversation.items(), key=lambda item: -median(item[1]))
print("Median cost per conversation:", ", ".join(f"{name} ${median(costs):.3f}" for name, costs in by_median[:3]))
print(f"Top spender: {next(iter(spend))}. Costliest subcategory: {by_median[0][0]}.")
print()

# Every model call is one Gateway request. This sketch puts the whole day in one daily window and
# records each request's cost before the next request starts.
requests = sorted((run for run in seed["runs"] if run["run_type"] == "llm"), key=lambda run: run["end_time"])
CAP = round(total / 2, 2)  # a daily spend limit on the agent's API key, set at half of the day's spend
recorded = 0.0
for number, run in enumerate(requests, start=1):
    cost = cost_of(run, PRICES)
    if recorded + cost >= CAP:
        break
    recorded += cost
print(f"Daily cap on the agent's API key: ${CAP:.2f} (half of the day's ${total:.2f}).")
print(f"Requests 1 to {number - 1} record ${recorded:.4f}, below the cap. All succeed.")
print(f"Request {number} ({run['extra']['metadata']['ls_model_name']}) starts below the cap and succeeds. It costs ${cost:.4f}, so recorded spend is now ${recorded + cost:.4f}, over the cap.")
print(f"Requests {number + 1} to {len(requests)} ({len(requests) - number} model calls) get a 402 until the window resets at midnight UTC.")
'''),
    md('''
## 6. Which control stops which incident?

Section 1 listed five things that went wrong in the seeded day:

| | Incident |
|---|---|
| A | Release 1.5.0 tells customers with opened electronics that they have 30 days to return them (the policy says 14) |
| B | A burst of 8 errors in `get_order_status` inside 3 minutes |
| C | Orders typed in lower case or without dashes are reported as not found |
| D | Compatibility questions are delegated twice, so they cost about twice as much |
| E | A customer's email address is stored in a trace |

> 💡 **Try it first:** for each incident, pick the control that fits best: an alert, an online evaluator, an Engine issue, a Gateway spend limit, trace masking, or none of them. Then run the next cell.
'''),
    code('''
answers = [
    ("A", "online evaluator",
     "No governance control prevents a wrong answer. The online evaluator detects it on every trace, and a dataset example of the corrected answer keeps it from coming back."),
    ("B", "alert",
     "An alert with a threshold of 3 failed traces (errored root runs) in 5 minutes fires on the burst and stays quiet for the background errors."),
    ("C", "Engine issue",
     "The tool result has status success, so only a code fix helps. Engine tracks the issue and its pull request."),
    ("D", "Gateway spend limit",
     "A spend limit caps the bill. It does not fix the cause: the duplicate delegation needs a change to the agent."),
    ("E", "trace masking",
     "Client-side masking keeps the address out of the upload. A Gateway data policy scans requests to the provider, not your application's traces."),
]
for incident, control, why in answers:
    print(f"{incident}  {control:<20} {why}")
'''),
    md('''
Two choices are also defensible. For C, the thumbs-down on 16 of the 19 conversations would let an alert on Feedback Score notice the problem; the fix is still a code change. For D, Insights found the cost by subcategory and Engine has it as a finding; the spend limit is the only one of the three that stops the spending.

## 7. Who did what: traces, the audit log, roles and Custom Apps

"Audit logging" covers two different records:

| Question | Where the answer is | Plan |
|---|---|---|
| Who called which model, when, at what cost, and was the call blocked? | The Gateway's traces in the project `gateway`, with `gateway.api_key_id` and `gateway.user_id`, and the Gateway's **Usage** tab | Traces on any plan with the Gateway; **Usage** on Plus or Enterprise |
| Who created, changed or deleted a Gateway policy, a provider secret, an API key or a role? | The organization audit log: **Organization Settings > Audit logs**, kept up to 400 days, with operations such as `create_gateway_policy` | Enterprise; Organization Admin or Organization Operator |
| Which tool did an agent call through the Tool Gateway? | The audit log operations `invoke_mcp_gateway` and `invoke_mcp_server` | Enterprise |

The audit log lists no operation for a single LLM Gateway model call. Model calls are in the Gateway's traces.

Roles decide who may do what. To call models through the Gateway, a key needs `gateway:invoke` and `workspaces:read` in its workspace. To create policies, a person needs `organization:gateway:manage`. On plans other than Enterprise every workspace member is a Workspace Admin; custom roles and access policies are Enterprise features.

A **Custom App** is a UI that runs inside LangSmith and calls the LangSmith API with the permissions of the person viewing it, so each viewer sees only the data they may see. Apps are on the Plus and Enterprise plans, and you build one by chatting with LangSmith or with the `langsmith apps` command line. A review screen for the annotation queue of Section 1 is a typical first app. See the [Custom Apps docs](https://docs.langchain.com/langsmith/custom-apps).

The next cell is the only cell in this module that can spend model tokens. It sends two requests to the Gateway: one to list the models your key may call, and one short chat request. It runs only when you set `GATEWAY_LIVE = True` and a Gateway key is available.
'''),
    code('''
GATEWAY_LIVE = False  # set to True to call the LLM Gateway; this spends a few model tokens
GATEWAY_BASE_URL = "https://gateway.smith.langchain.com/v1"  # US; the EU host is eu.gateway.smith.langchain.com
gateway_key = os.getenv("LANGSMITH_GATEWAY_API_KEY") or (os.getenv("LANGSMITH_API_KEY") if LANGSMITH_AVAILABLE else None)

if GATEWAY_LIVE and gateway_key:
    import httpx

    headers = {"Authorization": f"Bearer {gateway_key}"}
    try:
        listed = httpx.get(f"{GATEWAY_BASE_URL}/models", headers=headers, timeout=30)
        print("GET /v1/models:", listed.status_code)
        if listed.status_code == 200:
            ids = [model["id"] for model in listed.json().get("data", [])]
            print(f"  {len(ids)} models this key may call, for example: {', '.join(ids[:5])}")
        reply = httpx.post(
            f"{GATEWAY_BASE_URL}/chat/completions",
            headers=headers,
            json={"model": "openai/gpt-5.4-mini", "messages": [{"role": "user", "content": "ping"}]},
            timeout=60,
        )
        print("POST /v1/chat/completions:", reply.status_code)
        print("  Retry-After:", reply.headers.get("Retry-After"))
        print("  X-LangSmith-Gateway-Metadata:", reply.headers.get("X-LangSmith-Gateway-Metadata"))
        print("  Body:", reply.text[:500])
    except httpx.HTTPError as exc:
        print(f"⏭️  The request failed ({type(exc).__name__}). The saved blocks of §5 show the same responses.")
elif GATEWAY_LIVE:
    print("⏭️  Skipped: no Gateway key. Set LANGSMITH_GATEWAY_API_KEY, or a working LANGSMITH_API_KEY, in .env.")
else:
    print("⏭️  Skipped: GATEWAY_LIVE is False. The saved responses of §5 show what a blocked call returns.")
'''),
    md('''
## 8. Where to go next

| Topic | Where |
|---|---|
| Spend, rate, model access and data policies | [Spend](https://docs.langchain.com/langsmith/llm-gateway-spend-policies), [rate limit](https://docs.langchain.com/langsmith/llm-gateway-rate-limit-policies), [model access](https://docs.langchain.com/langsmith/llm-gateway-model-access-policies) and [data](https://docs.langchain.com/langsmith/llm-gateway-data-policy) policies; [header-based policies](https://docs.langchain.com/langsmith/llm-gateway-header-policies) |
| Model fallbacks in the Gateway | [Model fallbacks](https://docs.langchain.com/langsmith/llm-gateway-fallbacks) |
| The Gateway's traces | [View LLM Gateway traces](https://docs.langchain.com/langsmith/llm-gateway-traces) |
| Masking data in traces | [Prevent logging of sensitive data in traces](https://docs.langchain.com/langsmith/mask-inputs-outputs) |
| Audit logs | [Audit logs](https://docs.langchain.com/langsmith/audit-logs) |
| Custom Apps | [Custom Apps](https://docs.langchain.com/langsmith/custom-apps) |
| Engine, end to end | The LangChain Academy course [Autonomous Agent Improvement with LangSmith Engine](https://academy.langchain.com/courses/langsmith-engine) |
| Online evaluation, annotation queues and automation rules on the Module 1 agent | [Module 3, Section 1](../module_3/section_1_production_data_flywheel.ipynb) |
| Offline evaluation of the deep agent, and the Harbor task for the return window | [Module 5, Section 1](../module_5/section_1_baseline_evaluation.ipynb) and [Module 5, Section 5](../module_5/section_5_harbor_evals.ipynb) |
'''),
    md('''
### What you did in code, and where it is in LangSmith

| Step in this notebook | Same step in LangSmith |
|---|---|
| The email search over root runs (§1) | The search bar of your TechHub traces |
| `offline_client(anonymizer=build_anonymizer())` (§3) | Nothing to click: masking is set in the client of your application, before upload |
| `init_chat_model(...)` under five environments (§4) | **LLM Gateway** > **Simulator** shows a request's route |
| `gateway_replay(kind)` (§5) | A blocked request in **LLM Gateway** > **Traces**, with `gateway.request.outcome` set to `blocked` |
| `spend_by(seed, "customer_id")` (§5) | The **Usage** tab with **Breakdown by** **User** or **API key**, or **Custom Dimension** for a header |

## Recap

| Layer | What it blocks | Who configures it |
|---|---|---|
| `PIIMiddleware` | Personal data in what the model sees and in the saved conversation | The developer, in the agent's code |
| Client-side trace masking (`Client(anonymizer=...)`) | Personal data in what LangSmith stores in your traces | The developer, in the client or with environment variables |
| Gateway data policy | Personal data and secrets in requests to the model provider | An organization admin, on the **Data Policy** tab, with the PII entitlement |
| Gateway spend, rate and model access policies | Spend over a cap (`402`), too many requests (`429`), models not on the list (`403`) | An organization admin, with `organization:gateway:manage` |
| Roles and the audit log | Changes by people without the right role; the audit log records who changed what | An organization admin; Enterprise for custom roles and the audit log |

- With `PIIMiddleware` alone, the email was in most uploaded payloads of the trace. An anonymizer brought that to 0 and left the order id alone.
- `LANGSMITH_GATEWAY=true` sends calls to `https://gateway.smith.langchain.com/openai/v1` even when `OPENAI_API_KEY` is set.
- A spend block is a `402` (`APIStatusError`), a rate block a `429` with `Retry-After` (`RateLimitError`), a model access block a `403` (`PermissionDeniedError`). The agent retries only the `429`.
- A spend limit caps the bill after the request that crosses it. It does not fix a costly agent.

This is the last section of Module 7. Across the four sections you detected the day's incidents with online evaluators and alerts, understood them with Insights, fixed them with Engine, and prevented two of them with masking and Gateway policies.
'''),
]


save(NOTEBOOKS[1], s1)
save(NOTEBOOKS[2], s2)
save(NOTEBOOKS[3], s3)
save(NOTEBOOKS[4], s4)
