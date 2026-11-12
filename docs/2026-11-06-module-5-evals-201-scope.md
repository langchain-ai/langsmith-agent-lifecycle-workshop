# Module 5 (Evals 201): scope draft

Status: draft for Ariel to review (2026-11-06). Nothing is built yet.

> Superseded in part on 2026-11-12: the module is now five sections (see the note at the top of `docs/2026-11-09-module-5-build-plan.md`).

## Where this comes from

- **Notion: [Advanced Workshop Content (L200+) Draft](https://app.notion.com/p/3e3808527b17816d82caf22119d43c8c), §9 "Evals 201: Offline, Harbour, and Jev".** Ariel owns Test/Evals. The exercises evaluate the same TechHub support agent before deployment: answers, tool calls, trajectories, and files/artifacts. Online evals belong to Evie's Monitor/Govern bucket; Ariel contributes evaluator design there.
- **Open question in that page:** is Harbor a standalone Evals 201 workshop or a module inside a broader advanced-evals workshop? This doc assumes it's one section of Module 5 (see Decisions).
- **Slack, #team-customer-enablement (Oct 20):** Ariel asked to add align evals to the Evals 201 Harbor + Jev section.
- **Slack DM with Tanmaiyii (Nov 4):**
  - Deep agents content stays separate from Module 2.
  - The order specialist in Module 4 keeps its 4 rigid tools on purpose, so there's something to improve.
  - "When you do evals 201 you can show the next version similar to the specialist one": run Module 2's eval-driven fix again, this time on the deep agent.
- **Module 6, Section 2, §5 on `main`** already sends readers to "Module 5 (evaluation)" for judge alignment, trajectory evals, and experiments.

## What already exists on `main` to build on

| Asset | Where | What Module 5 does with it |
|---|---|---|
| Deep support agent | `agents/deep_support_agent.py` | The system under test. Order specialist + product/policy specialist, `request_refund` behind HITL, optional `JevToolGate`, `RubricMiddleware` |
| Module 2 dataset and evaluators | `workshop_modules/module_2/baseline_dataset.json`, `golden_set.json`, `evaluators/` | Starting dataset and evaluators. Module 4 S3 already reuses the 12 questions as a support inbox |
| Aligned LLM judge | `workshop_modules/module_2/bonus_align_llm_judge.ipynb` | The baseline judge that Jev is compared against |
| Jev client | `utils/jev.py` (`TypeSafeClassifier` through the LangSmith Gateway, pinned `typesafe/jev-1.14.0`) | Reuse as-is for code-defined Jev evaluators |
| Jev in the harness | Module 4 S3 §4: ticket triage (`Choice`/`Noul`) vs an LLM, a 0.7 confidence cascade, and `JevToolGate` (`agents/middleware/jev_tool_gate.py`) | Module 4 already teaches Jev as a harness component, including the `Noul`/`Choice`/`Score` types. Module 5 teaches Jev as an evaluator and can evaluate the triage and gate decisions, but shouldn't teach either again |
| Harbor tasks | `managed_agent/evals/` (3 tasks, `harbor-job.json`, README run recipe) | Introduced in Module 6 S2 §4. Module 5 goes deeper: writing tasks, verifiers, the LangSmith plugin, reading results |

## Proposed shape

Three sections. Each one can be run on its own, like the other modules.

### Section 1: Evaluating a deep agent

Goal: run Module 2's measure → find the problem → improve → re-measure cycle on the deep agent.

- Baseline experiment of `create_deep_support_agent()` on the Module 2 dataset, using the existing `correctness` and `total_tool_calls` evaluators.
- Trajectory evals for a multi-agent harness:
  - Was the right specialist used?
  - How many subagent dispatches were there?
  - Did `request_refund` stop for approval?
- Improve the order specialist from 4 rigid tools to `execute_sql`, Module 2's fix, and re-run. Compare the two experiments in LangSmith. This is the "next version" Tanmaiyii suggested.
- Optional: measure what `RubricMiddleware` adds in quality against what it costs in tokens and latency. This is evals used to decide harness choices.

### Section 2: Jev as a judge, checked against an aligned judge

Goal: when a decision model is a good evaluator, and how to check that before trusting it.

- Jevaluators in LangSmith: Noul, Choice, and Score questions. Set one up in the UI using the Gateway path Christine posted on Oct 29 (`typesafe/jev-latest`, base URL `https://gateway.smith.langchain.com`, append `/v1/systemone`, Gateway key as the secret). Also show the same evaluator written in code with `utils/jev.py`.
- Score the Section 1 experiment with three graders: Jev, the aligned LLM judge from the Module 2 bonus, and the human labels. Report agreement, variance across repeated runs, cost, and latency. This is the "align evals" step.
- Evaluate the `JevToolGate` itself: a small labeled set of tool calls (side effect or not), then precision and recall at the 0.7 threshold.
- Accuracy notes the instructor must say:
  - The public benchmark is one narrow test ("promising, but early").
  - A cheap evaluator that is consistently wrong produces bad feedback at scale.
  - Use synthetic data only. Jev has no default ZDR, and security has cleared it for experimentation only.

### Section 3: Harbor evals

Goal: evaluate inside a reproducible environment, for checks that a dataset row can't express.

- How a task is built: `instruction.md`, `Task.md` (the reviewed spec), `identity.json`, a Dockerfile, and `tests/verify.py` scoring from `/logs/agent/result.json`. Cover invalid vs failed runs.
- Walk through the three existing tasks, then write a new one in the workshop. Candidates:
  - A refund request that must pause for approval.
  - A file/artifact check, such as a drafted email written to the workspace.
- Run with `--plugin langsmith`, so each job becomes an experiment, the tasks sync as a dataset, and verifier rewards come in as feedback. Read the results in LangSmith next to the Section 1 experiments.
- When to use which: dataset-based experiments vs Harbor tasks.

## Decisions to make

1. **One module with three sections, or Harbor as a standalone workshop** (the open Notion question)? **Decided 2026-11-09: a section of Module 5**, written to stand alone so it can also be delivered by itself. Module 6 S2 §4 stays the short intro for the managed agent, and Module 5 S3 is where Harbor is taught hands-on. Harbor's results arrive in LangSmith as an ordinary experiment (dataset, experiment, `reward` feedback, cost, tokens), so the lesson is the comparison with Sections 1–2: which questions need a sandbox and a verifier, and which a dataset row covers. A standalone Harbor workshop would have to rebuild that context.
2. **Target length.** Three sections is about 2–2.5 hours hands-on. If the slot is 1 hour, cut Section 1's trajectory evals and the optional rubric comparison.
3. **Notebook vs UI balance.** Decided (2026-11-06): notebooks, with links out to the LangSmith UI (experiments, comparison view, Jevaluator setup, the Harbor experiment). Reuse `langsmith_links.py` the way Module 2 does.

## Harbor facts that shape Section 3 (from [docs.langchain.com/langsmith/harbor-integrations](https://docs.langchain.com/langsmith/harbor-integrations))

- **`--agent langgraph`** runs any project with a `langgraph.json` inside the trial. Section 3 can evaluate the Module 4 deep agent directly. It doesn't have to go through MDA (that path is `managed_agent/evals/`).
- **`--env langsmith`** runs each trial in a LangSmith sandbox instead of local Docker. If it works for our tasks, the Docker-in-Instruqt problem goes away.
- **`--plugin langsmith`** turns a job into a LangSmith dataset plus experiment, with one feedback key per verifier reward and a `harbor_error` key for broken trials. Notebooks can link straight to it.

## Smoke test: Harbor on LangSmith sandboxes (2026-11-09)

One task (`order-status-own-order`) through the MDA adapter, run in a LangSmith sandbox on a Mac with no Docker installed. **Passed: reward 1.0, 2 min 24 s, built from the task's own Dockerfile.** LangSmith got a dataset (`m5-harbor-smoke`) and an experiment with `reward` feedback and the agent's answer in the run outputs.

Follow-up run, same day: `cross-customer-order-refused` and `opened-item-return-window` together (`-n 2`), **both passed (reward 1.0), 2 min 27 s total.** All three existing tasks now pass on LangSmith sandboxes. The cross-customer answer refused without naming any detail of the other order, and the return-policy answer cited the 14-day opened-electronics window.

Command that worked (from `managed_agent/`, after `uv sync --python 3.14` and `uv run mda evals init`):

```bash
HARBOR_LANGSMITH_DATASET=m5-harbor-smoke \
PYTHONPATH=.mda/evals/harbor-adapter \
uv run --no-project --env-file ../.env --python 3.12 --with 'harbor[langsmith]==0.21.0' harbor run \
  --config evals/harbor-job.json --yes \
  -p evals -i 'order-status-own-order' \
  --env langsmith --ek delete_after_stop_seconds=600 \
  --plugin mda_harbor.job_plugin:MDAJobPlugin \
  --plugin mda_harbor.langsmith_plugin:LangSmithPlugin
```

Findings:

- **Bug in Module 6's documented command** (Module 6 S2 §4 and `managed_agent/evals/README.md`): `uv run --python 3.12` inside `managed_agent/` deletes the project's 3.14 venv and rebuilds it on 3.12. That removes the `mda` binary that `.mda/evals/runtime.json` points to, so the adapter can't compile the agent. Fix: add `--no-project`. Separate PR.
- **`--env langsmith` works with the existing tasks unchanged**, so local Docker isn't required. Add it to Module 6 as the no-Docker option.
- `-i` (task filter) needs `-p evals` as well, even though the job config already lists the dataset.
- Gaps to look at for Module 5: the run recorded no `model` or token `usage` (both null in `agent/summary.json`), and the verifier's stdout wasn't downloaded ("No files in '/logs/agent' matched"), so a failing run would only show reward 0 without the reason.

## Risks and things to verify first

- **No `harbor run` has been done end to end yet.** The README says the tasks were validated on the host without Docker on 2026-10-30. Try `--env langsmith` first (no local Docker), then local Docker as a fallback.
- **Instruqt:** Tanmaiyii asked Instruqt on Oct 29 whether they support Jev, and asked IT for a TypeSafe key for the Gateway. Confirm both, plus whether Docker is available in the Instruqt track for Harbor.
- **`langchain-typesafe==0.0.1a3` is alpha.** Thresholds don't carry over between Jev versions (see the comment in `utils/jev.py`).
- **Harbor inside LangSmith is changing.** Nick Hollon's `smith-harbor` package / LangSmith Simulations (#team-simulations, Oct–Nov) may change how Harbor runs are kicked off. Check its status before writing the run instructions, so the module doesn't teach a path that is about to change.
- **MDA build time** (2–4 min) matters only if Section 3 runs against the managed agent. The Harbor adapter installs the compiled agent per trial.

## Next steps

1. Delete the empty `feat/evals-201` branch (it's 14 commits behind and has no commits of its own). Start `feat/module-5-evals-201` from `main`.
2. Run the Harbor Docker job end to end and note the setup friction.
3. Prototype Section 1's baseline and the `execute_sql` re-run on the deep agent to confirm there's a measurable improvement.
4. Settle the three decisions above, then update the Notion §9 and the README's Module 5 line.
