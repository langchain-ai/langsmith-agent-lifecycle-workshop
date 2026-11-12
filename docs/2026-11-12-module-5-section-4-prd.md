# PRD: Module 5 Section 4 (Jev as a judge)

Status: Draft for review (2026-11-12). Owner: Ariel Herrera. Branch: `feat/module-5-evals-201`.

## 1. Goal

Teach when a cheap, fast decision model can grade an agent, and how to check that before trusting it. Section 4 grades the same human-labeled golden set as Section 3 with **Jev** (TypeSafe's decision model) and compares it with the unaligned and aligned LLM judges on agreement, consistency, latency, and cost. Then it shows the same evaluator in the LangSmith UI.

The question the section answers: *can a decision model replace the aligned LLM judge here, and how would you know?*

## 2. Principles

- Module 2 has no Jev section, so there's nothing to mirror. Section 4 reuses Section 3's structure and machinery: the same golden set (`module_5/golden_set.json`), the same `frozen_agent` target, the same `report()` with the hold-out, and the same "measure, read disagreements, fix one cause at a time" loop.
- Module 4 Section 3 already teaches Jev's question types (`Noul`, `Choice`, `Score`), routing, and the tool-safety gate. Section 4 recaps them in one cell and links back; it teaches **Jev as a judge** only.
- Notebook style as in Sections 1–3: one concept per step, images or ASCII where they help, tables for comparisons, plumbing in `utils/`.

## 3. Access: what we know (Slack thread, 2026-11)

| Fact | Source |
|---|---|
| Jev is reached through the LangSmith LLM Gateway (`typesafe/` model IDs). Raw TypeSafe keys aren't provided internally | IT Console |
| The Gateway reads the `TYPESAFE_API_KEY` provider secret from the **workspace the key belongs to**. Our workspace has none, so every call returns 424 (re-checked 2026-11-12) | `utils/jev.py`, our test |
| Raw keys have no governance: no spend limits, no expiry | Ryan Casupanan |
| Workable option: a **scoped, time-limited LangSmith API key with a model allowlist of only the TypeSafe model**, from a workspace that holds the TypeSafe secret, ideally under a Gateway spend cap | martha, Christine |
| Such a key was cut (ticket IT-4875) and confirmed working, both in code and in the UI | Stephen Armstrong, Christine |
| UI path: Evaluators → Decision Model Evaluator → configure prompt & model → **TypeSafe-compatible endpoint** → model `typesafe/jev-latest`, base URL `https://gateway.smith.langchain.com`, check **Append /v1/systemone**, no extra headers, the Gateway key as the secret | Christine |
| The SDKs can't create decision-model evaluators, but the REST API can: `POST /api/v1/runs/rules/decision-models` creates one and attaches it to a dataset or tracing project in one request (state as a prompt template like `Question: {{input}}\nAnswer: {{output}}`, plus `noul` / `choice` / `score` questions, each becoming a feedback key) | [Decision model evaluator docs](https://docs.langchain.com/langsmith/decision-model-evaluator) |
| In a decision-model evaluator the **state** carries no grading instructions; the criteria go in the questions | Same page |
| Data: TypeSafe offers zero data retention per org on request and no BAA. Synthetic data only | `utils/jev.py` |

**Update 2026-11-12 (Ask IT):** on LangChain-managed Macs, Jev already works through the Gateway with the IT-provisioned **`LC_GATEWAY_KEY`** (in launchd and in `/etc/lc_internal/gateway_env`); no ticket or TypeSafe key needed. Smoke-tested: `typesafe/jev-latest` (now resolving to `jev-1.14.0`) and the pinned `typesafe/jev-1.14.0` both answer. Our 424 came from `utils/jev.py` preferring `LANGSMITH_GATEWAY_API_KEY` (a workspace without the TypeSafe secret). A JupyterLab started from a terminal doesn't see the launchd variable.

The IT-4875 key was cut for a customer's workshop. We don't reuse it, and its share link never goes in the repo or docs.

### Prior art (checked 2026-11-12)

No LangChain workshop or notebook uses Jev as a judge yet. Module 4 Section 3 of this repo is the only notebook with Jev (routing and the tool gate). What exists:

| Source | What it is | How Section 4 uses it |
|---|---|---|
| [Decision model evaluator](https://docs.langchain.com/langsmith/decision-model-evaluator), [decision models for online evals](https://docs.langchain.com/langsmith/online-evaluations-decision-models), [compatible endpoints](https://docs.langchain.com/langsmith/compatible-decision-model-provider) | The UI and REST setup for Jev as a judge, question types, and feedback keys | §5 step 7, and possibly creating the UI evaluator from the notebook via REST |
| [Decision models in the LLM Gateway](https://docs.langchain.com/langsmith/llm-gateway-decision-models#use-typesafe-jev) | Calling Jev through the Gateway | Already followed by `utils/jev.py` |
| `langchain-skills` `langgraph-decision-models` skill | Routing with decision models: question wording matters more than thresholds, use `criteria` to say what each answer means, thresholds don't transfer between models | Question-design guidance for the spike (T4) |
| `openevals.graph` (experimental, added 2026-11-12; not in the installed `openevals`) with the `langsmith-graph-evaluator` skill | Evaluators built as a graph of `LLM` and `DecisionModel` nodes; `DecisionModel` accepts a `typesafe:` name or any decision model object | Don't depend on it yet: brand new and unreleased here. Revisit if it ships; it would replace the hand-written Jev evaluator |
| `open-swe` (`runtime_api/classifier.py`) | Jev as a classifier for routing | Not a judge; not used |

## 4. Access options for the workshop

| Option | How attendees get Jev | Pros | Cons |
|---|---|---|---|
| **A. Workshop key** | The host requests a scoped, time-limited, TypeSafe-allowlisted LangSmith key (an IT ticket like IT-4875), with a Gateway spend cap if one can be set. It's handed out through the workshop's secret channel (Instruqt env or 1Password) as **`JEV_API_KEY`** | Works for everyone; the same key works in code and in the UI evaluator | Needs IT for each workshop; no spend cap on the key itself, so it must be time-limited and revoked afterwards |
| **B. Own workspace** | The attendee's workspace adds a `TYPESAFE_API_KEY` provider secret | No shared key | Needs a TypeSafe account; not realistic in a workshop |
| **C. No access** | Jev cells skip themselves and the notebook shows recorded results from our run, as Module 4 Section 3 does | Runs anywhere | Attendees don't run Jev themselves |

**Proposed:** A as the default, with C as the automatic fallback.

`JEV_API_KEY` is a new variable, used only for Jev. The key is allowlisted to TypeSafe, so if it replaced an attendee's `LANGSMITH_GATEWAY_API_KEY`, their other model calls would fail. The attendee's own LangSmith key keeps doing the tracing.

## 5. Notebook outline: `section_4_jev_as_judge.ipynb`

| # | Step | Concept | Visual | Code |
|---|---|---|---|---|
| 0 | Title and intro | A decision model answers typed questions with probabilities instead of generating text; it's fast and cheap, but is it right? | ASCII: LLM judge (prompt → reasoning → verdict) vs decision model (state + typed questions → probabilities → threshold → verdict) | — |
| S | Setup and access check | Where Jev's access comes from (§4); the notebook skips Jev cells without it | Table: the three access options | Load `.env`, try one Jev call, set `JEV_AVAILABLE` |
| 1 | Jev in one cell | `Noul`, `Choice`, `Score`, recapped; link to Module 4 Section 3 | — | One `Noul` call |
| 2 | Jev as an evaluator | A judge is questions plus a threshold. State = question + reference + output; one `Noul` "Is the output correct?"; verdict = probability ≥ threshold | ASCII of the state layout | `jev_correctness_evaluator` |
| 3 | Measure against the golden set | Same `frozen_agent`, `report()`, and hold-out as Section 3 | Agreement + confusion matrix | `client.evaluate` on the Section 3 dataset |
| 3.1 | Analyze | Group disagreements by cause, as in Section 3 | Cause table | — |
| 4 | Fix: from one question to the rubric's questions | Jev's version of rubric rules: one `Noul` per rule from Section 3 (correct against the reference / answers what was asked / no invented actions); verdict = all pass. Each question becomes its own feedback score | Question table | `jev_rubric_evaluator`; re-measure |
| 5 | Pick the threshold, then cascade | A probability needs a cut-off: choose it on the rule items, check it on the hold-out, and look at how close the two groups sit. Send the uncertain middle to the aligned LLM judge | Sorted-scores printout; agreement vs threshold | Sweep thresholds over stored probabilities (no new calls); cascade over the gray zone |
| 6 | Compare the judges | Unaligned LLM judge, aligned LLM judge (Section 3), Jev: agreement, hold-out, run-to-run consistency, latency, cost | Comparison table | Repeated runs; latency from runs |
| 7 | The same evaluator in the UI | Decision Model Evaluator on the dataset, mapping the reference output into the state; TypeSafe-compatible endpoint setup (§3) | Steps table, docs links | — |
| 8 | When to use which | Decision model vs LLM judge: cost and latency vs explanations and nuance; pin the version; synthetic data only | Decision table | — |

The exact question design (§5 steps 2 and 4) is settled by the spike (T4), as Section 3's rules were.

## 6. Decisions

| # | Question | Proposed | Status |
|---|---|---|---|
| Q1 | Workshop access | Option A (workshop key as `JEV_API_KEY`) plus C (skip with recorded results) | Decided 2026-11-12 |
| Q2 | Key handling | `JEV_API_KEY` used only by `utils/jev.py`, taking precedence over the Gateway key chain; never committed or printed; time-limited and revoked after each workshop | Decided 2026-11-12 |
| Q3 | Jev model version | Pin `typesafe/jev-1.14.0` (what `utils/jev.py` pins), since thresholds don't transfer between versions; the UI steps use the same ID, not `jev-latest` | Decided 2026-11-12 |
| Q4 | Judges to compare | v0 (unaligned), v2 (aligned, `deep_agent_correctness_evaluator`), and Jev (single question and rubric questions) | Decided 2026-11-12 |
| Q5 | Out of scope | `JevToolGate` evaluation (covered in Module 4), online-evaluation automation (Module 3 territory), OpenAI's decision model (`gpt-6-luna`) beyond one mention | Decided 2026-11-12 |

## 7. Tasks

**Access (blocking)**
- [x] **T1** Access: internal presenters use `LC_GATEWAY_KEY` (Ask IT, 2026-11-12). External attendees still need option A (a workshop key as `JEV_API_KEY`) or C.
- [x] **T2** `utils/jev.py`: key chain `JEV_API_KEY` → `LC_GATEWAY_KEY` (environment, then the file named by `GATEWAY_ENV_FILE`) → the existing Gateway chain, used only for Jev. `verify_setup.py`: report which Jev key source is in use and that it works. Unit test for the key precedence.
- [ ] **T3** Check access in both paths: one Jev call in code (**done 2026-11-12**: 0.99 via `LC_GATEWAY_KEY` from `GATEWAY_ENV_FILE`), and the UI decision-model evaluator on one example (needs a workspace secret and model configuration in Ariel's workspace: Ariel's call, done during T8).

**Spike**
- [x] **T4** On the Section 3 golden set: single `Noul` vs rubric `Noul`s vs a `Choice` (correct / partially correct / incorrect). For each: agreement on rule items and hold-out, consistency over 3 runs, and latency per item. Pick the threshold on the rule items only. Record in §10.
- [x] **T5** Measure the LLM judges' latency per item on the same set (v0, v2) for the comparison table; record cost from LangSmith run usage where it's reported.

**Build**
- [x] **T6** `evaluators/`: `jev_correctness_evaluator` (the design chosen in T4, pinned model and threshold), raising a clear error when Jev isn't reachable. Unit test for the question set and the threshold logic, with no network.
- [x] **T7** Add `s4` to `build_module5.py` and generate `section_4_jev_as_judge.ipynb` per §5. Every Jev cell checks `JEV_AVAILABLE` and otherwise prints the recorded results from §10.

**Validate and document**
- [ ] **T8** Run end to end twice from a fresh kernel: with `JEV_API_KEY` (full run; check every experiment for errors before reading scores), and without it (every Jev cell skips cleanly).
- [ ] **T9** Docs: README "Model access" (`JEV_API_KEY`), `.env.example`, `workshop_modules/README.md` Section 4 entry, `CLAUDE.md` Module 5 notes, project memory, and the build plan's Jev status.

## 8. Acceptance criteria

- With a key, the notebook runs top to bottom with zero errored runs in every experiment. Without one, it runs top to bottom with every Jev cell skipped and the recorded results shown.
- The comparison table reports agreement (all, rule items, hold-out), consistency, and latency for every judge, from the same golden set as Section 3.
- The threshold is chosen on the rule items only, and the hold-out result is reported, whether or not it's flattering.
- No key or share link appears in the repo, notebook outputs, or docs.
- `tests/` pass.

## 9. Risks

- **Access.** Everything depends on T1. If no key can be provisioned, the section ships in option C (recorded results), which teaches the concepts but not hands-on.
- **Key governance.** Keys have no spend limit or expiry of their own (per the thread), so a workshop key must be time-limited, allowlisted to TypeSafe, and revoked afterwards.
- **Jev may lose.** The aligned LLM judge is at 97% on this set. If Jev is clearly worse, that's a valid result: the section's lesson is how to check, not that Jev wins. The text must match the numbers.
- **Threshold overfitting.** 27 rule items is small; the hold-out (6 items) is the check, and it's small too. Say so.
- **Long states.** Some outputs (order reports) are long; if one exceeds Jev's context, the `TypeSafe-Danger-Zone-Long-Context` header raises the limit (docs). Spike checks.
- **Data.** TypeSafe has no BAA. TechHub data is synthetic; the notebook says real customer data needs a security review first.

## 10. Results (T4–T5 spike, 2026-11-12; `typesafe/jev-1.14.0`, judge `openai:gpt-5-mini`; 3 runs each)

Jev's state is the question, the reference, and the agent's answer, with no grading instructions (per the docs). Agreement is with Ariel's labels on Section 3's golden set; the cut-off is chosen on the 27 rule items only.

| Judge | Cut-off | All | Rule items | Hold-out | Varies across runs by | Latency / item (median) | Tokens / item (in, out) |
|---|---|---|---|---|---|---|---|
| v0 LLM judge (unaligned) | — | 91–93% | 93–96% | 78–83% | an item or two | 4.4 s | 569, 347 |
| v2 LLM judge (aligned, Section 3) | — | 97% | 96% | 100% | an item or two | 4.4 s | 814, 410 |
| Jev, single question | 0.50 | 85% | 89% | 67% | ≤0.09 | 0.2 s | — |
| Jev, choice (correct / partial / incorrect) | 0.25 | 91% | 89% | 100% | ≤0.10 | 0.2 s | — |
| Jev, rubric (3 questions, all must pass), first wording | 0.15 | 91% | 93% | 83% | ≤0.06 | 0.2 s | — |
| **Jev, rubric, refusals fixed** | **0.15** | **97%** | **96%** | **100%** | ≤0.09 | **0.2 s** | 891, 56 |
| **Cascade: Jev rubric, gray zone 0.10–0.50 to the aligned LLM judge** | — | **97%** | — | — | — | 0.2 s for 29 items, plus 4.4 s for 4 | — |

Findings:
- **The rubric design wins** and gives one feedback score per question (`facts_agree`, `answers_question`, `possible_actions`). Its first wording failed correct refusals on `answers_question` (0.01–0.02); one sentence in the false criterion ("declining because the data belongs to another customer is not leaving it unanswered") fixed both, including the hold-out one.
- **Jev's one miss is arithmetic:** `sql-1`, whose breakdown doesn't add up to its total, passes `facts_agree` at 0.69. The aligned LLM judge's one miss was different (the mice). Decision models don't check sums.
- **The cut-off sits in a narrow gap.** Every incorrect answer's lowest score is ≤0.07 (except `sql-1`), and every correct one's is ≥0.17. Four correct answers sit at 0.17–0.36 (both refusals, `sql-6` without prices, `rigid-8` with extra policy detail). At 0.25, agreement drops to 89%. Hence the cascade: Jev decides confident items and sends the gray zone (here 4 of 33, 12%) to the aligned LLM judge, which labels all four correctly. Same 97%, without depending on one exact number.
- **Speed:** Jev about 20× faster (0.2 s vs 4.4 s) with about 7× fewer output tokens. Per-token prices aren't recorded here; check LangSmith run usage for cost.

## 11. Out of scope

- `JevToolGate` and Jev routing (Module 4 Section 3).
- Online evaluators on a tracing project and automation rules (Module 3), beyond a pointer: the same UI evaluator can run on a tracing project.
- Provisioning keys for customers.
