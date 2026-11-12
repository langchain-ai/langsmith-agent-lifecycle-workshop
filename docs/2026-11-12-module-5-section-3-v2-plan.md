# Module 5 Section 3 v2: Harbor evals, concept-first

A new notebook, `workshop_modules/module_5/section_3_harbor_evals_v2.ipynb`, built next to v1 (`section_3_harbor_evals.ipynb`, unchanged) so the two can be compared. After review, one of them is kept and the other deleted.

## Why a v2

v1 works end to end, but a walkthrough showed the goal wasn't clear. Compared with the closest existing material, [modular-workshops Module 4 §3b "Environment evals"](https://github.com/langchain-ai/modular-workshops/blob/main/modules/04_langsmith.ipynb), v1:

- opens with what dataset evals can't do instead of saying what Harbor is, and never defines task, environment, verifier, trial, and job;
- puts a 94-line helper cell (progress panel, Harbor output parsing) near the top;
- re-creates a committed task with `%%writefile`, which makes the "build" look real when it isn't;
- tells the same pass/fail story in six diagrams;
- hides Harbor's own summary table, the view people see when they run Harbor themselves.

v2 is organized around concepts. Each section teaches one idea, shows one picture of it, and runs the smallest code that proves it.

## Concept arc

| # | Section | The concept | Visual | Code in the notebook |
|---|---|---|---|---|
| 0 | Intro | **An environment eval runs the agent in a fresh sandbox and grades what the run left behind.** It's the same loop as offline evals with different parts | `images/offline_eval_process.png`, then a new matching `images/harbor_eval_process.svg` (Task → Sandbox → Verifier → Experiment) | None |
| 1 | Vocabulary | Task, environment, verifier, trial, job, reward, and how each maps to a LangSmith object | Table: Harbor term → what it is → LangSmith object (dataset example, experiment, run, feedback) | None |
| 2 | Why | Some properties live only in the run state: side effects, approval pauses, data crossing customers. A reply judge gets the refund case wrong in both directions | Judge-vs-verifier table (from v1) | None |
| 3 | Anatomy | A task is a folder; a verifier is plain Python over `result.json` | Folder tree; the `instruction.md`, `identity.json`, and `verify.py` of `order-status-own-order`, printed | Print files |
| 4 | Run a job | One command runs N trials in parallel sandboxes and records them as an experiment | Run-flow diagram (from v1, trimmed); live progress panel; **Harbor's own summary table**; a per-task × per-check table | `harbor_run(...)`, `harbor_summary(job)`, `results_table(experiment)` |
| 5 | Three outcomes | **Reward 0 (agent failed) vs `harbor_error` (infrastructure failed) vs invalid (no evidence)**: only the first is the agent's fault | Small table | None |
| 6 | Design a task | Spec first: hidden truth, pass rule, what counts as invalid. Then input, identity, verifier | The refund task's two flows (paused vs ran) from v1; R1/R2 checks diagram | Print `Task.md`, `instruction.md`, `identity.json`; exercise: write R1/R2 before revealing `verify.py` |
| 7 | Trust the verifier | Test the verifier on known-good and known-bad run states before trusting its scores. Optional: the **oracle** run does the same in the real sandbox | Fixture table (2 rows: paused, ran) | 2 fixtures, run `verify.py` locally |
| 8 | Run it, then break it | A task that has never failed hasn't shown it can catch anything | Side-by-side of the two runs (from v1) | `harbor_run` with and without `interrupt_on`, restoring `agent.py` in `finally` |
| 9 | Read it in LangSmith | Each trial is a run with phase child runs; each check is a feedback column; compare experiments | Harbor → LangSmith mapping (from v1) | Dataset and comparison links |
| 10 | Where this goes | A verifier's reward is a training signal too (RL, rejection sampling); when to pick Harbor vs a dataset evaluator | Decision diagram (from v1) | None |

Concepts v1 had and v2 keeps: per-check scores in `reward.json`, `test.sh` never trusting leftover reward files (one sentence, no diagram), restoring `agent.py` in `finally`, and that the adapter recompiles the agent per job.

New in v2: the eval-loop pictures, the vocabulary table, Harbor's summary table, the per-task × per-check table, the three outcomes, the optional oracle, and evaluation-to-training.

Dropped from the notebook (kept in docs or utils): `test.sh` exit-code diagram, env-var mapping diagram, §6/§7 "what to expect" diagrams, the §8 comparison sketch, and two of the four fixtures.

One line on why the managed agent: the Module 6 agent runs through the MDA adapter because the tasks need a verified caller identity, which `identity.json` provides through the adapter. A plain Deep Agent could use Harbor's built-in `--agent langgraph` (as modular-workshops does).

## Files

| File | New / changed | Purpose |
|---|---|---|
| `utils/harbor_runs.py` | New | `harbor_run` (command, live panel, log file), `harbor_summary(job)` (prints Harbor's tables from the log), `results_table(experiment)` (per-task × per-check table read from LangSmith, with the agent's answer) |
| `images/harbor_eval_process.svg` | New | Harbor counterpart of `offline_eval_process.png`: same four columns, same colors (blue, orange, green, black) |
| `scripts/notebook_builders/build_module5.py` | Changed | Adds `s3_v2`; v1's list stays as-is |
| `workshop_modules/module_5/section_3_harbor_evals_v2.ipynb` | New | Generated |
| `managed_agent/evals/refund-requires-approval/solution/solve.sh` | New, only if the oracle spike works | Writes a known-good paused run state to `/logs/agent/result.json` |

v1's inline helpers stay in v1 so the two notebooks stay independent.

## Verified facts this plan relies on (2026-11-12)

- Each Harbor trial in LangSmith has `outputs.agent_output` (the answer), `outputs.rewards` (all check scores), feedback per check, and child runs `environment-start`, `agent-start`, `verification-start`. So `results_table` can read from LangSmith alone, the way modular-workshops does.
- `outputs.tokens` and `cost_usd` are null for MDA runs, so v2 says token usage isn't recorded yet.
- `Client.list_runs` is deprecated (removal after 2027-01-31); use `client.runs.query`.
- Harbor's oracle agent uploads `solution/` and runs `solve.sh` in the environment.

## Spikes before building

1. **Oracle on an MDA task:** `harbor run -p evals -i refund-requires-approval -a oracle --env langsmith` with a `solve.sh` that writes a paused `result.json`. Expect reward 1. If `/logs/agent` isn't writable, or the job config can't be skipped, drop the oracle and mention it in one line.
2. **Harbor summary table:** print it from the run log (we already save it) at the notebook's width. Harbor truncates column names (`Refund_Never_Ran_Wit…`), so the per-task table is the readable one. The second table (`Reward | Count`) lists reward values per check without labels; explain it or omit it.
3. **The SVG:** check that it renders in JupyterLab and on GitHub in light and dark themes.

## Validation

Run v2 end to end on LangSmith sandboxes (4 Harbor jobs, about 10 minutes), check that `agent.py` is unchanged afterwards, and compare v1 and v2 side by side in JupyterLab.

## Out of scope

- Switching to `--agent langgraph` on the Module 4 agent.
- Sections 1 and 2.
- Deleting v1, which happens after the comparison.
