# PRD: Module 5 Sections 1–2 (baseline evaluation and eval-driven development on the deep agent)

Status: Draft for review (2026-11-12). Owner: Ariel Herrera. Branch: `feat/module-5-evals-201`.

## 1. Goal

Repeat Module 2's evaluation path on the Module 4 deep agent, so people taking the deep-agent path learn offline evaluation and eval-driven development on the agent they built:

- **Section 1, Baseline:** curate examples, create a dataset, evaluate the deep agent with correctness and tool-call evaluators, and analyze the errors in LangSmith.
- **Section 2, Eval-driven development:** fix the weakness the baseline exposes (the order specialist's rigid lookup tools), re-run the same evaluation, and compare the results.

## 2. Principles

- **Mirror Module 2.** Same outline, same headings, same images where the concept is the same, same evaluators. Change only what the different agent requires. Every deviation is listed in §6 with its reason.
- **Two parallel paths.** Most people take either Modules 1–2 (supervisor agent) or Modules 4–5 (deep agent). The notebooks don't compare themselves to Module 2. The README explains the two paths once (task T13).
- **Notebook style:** one concept per step, images and ASCII diagrams where they help, markdown tables for comparisons, plumbing in `utils/` or the agent factory rather than notebook cells.

## 3. Module 5 outline (updated)

| Section | Notebook | Status |
|---|---|---|
| 1. Baseline evaluation | `section_1_baseline_evaluation.ipynb` | This PRD |
| 2. Eval-driven development | `section_2_eval_driven_development.ipynb` | This PRD |
| 3. Aligning the judge | `section_3_align_llm_judge.ipynb` (mirrors `module_2/bonus_align_llm_judge.ipynb`) | Later PRD |
| 4. Jev as a judge | `section_4_jev_as_judge.ipynb` | Later PRD; Ariel has an unblock path for the Gateway secret |
| 5. Harbor evals | `section_5_harbor_evals.ipynb` (today `section_3_harbor_evals.ipynb`) | Built; renamed in T1 |

Section 2's remaining failures feed Section 3. In the spike, the unaligned judge failed answers for extra detail and for the deep agent masking a phone number.

## 4. Section 1 outline: `section_1_baseline_evaluation.ipynb`

Mirror of `module_2/section_1_baseline_evaluation.ipynb` (32 cells).

| # | Module 2 step | Module 5 step | Visual | Code |
|---|---|---|---|---|
| 0 | Title, "What is offline evaluation?", `offline_eval_process.png` | Same text, with the deep agent as the app under test | `images/offline_eval_process.png` | Setup: `load_dotenv()` |
| 1 | Curate examples (`baseline_dataset.json`), `final-response-eval.png` | Same | `images/final-response-eval.png` (Module 2 has this `<img>` commented out with a `#`, so it renders as a heading. Don't copy that bug) | Load `module_5/baseline_dataset.json`, print one example |
| 2 | Create a dataset in LangSmith (messages format) | Same | — | `client.create_dataset` + `create_examples`, name `techhub-deep-agent-baseline-<uuid>` |
| 3 | Initialize the agent: `create_supervisor_hitl_agent()`, mermaid graph, quick test | Initialize the agent: `create_deep_support_agent()`, the architecture image, quick test | **New** `images/deep_support_agent.svg`: main agent, `order-specialist` (rigid tools), `product-policy-specialist`, `request_refund` (approval), customer-scope guard. A mermaid graph of a deep agent is a single node, so it doesn't show the structure | `create_deep_support_agent()`; quick test "What's your return policy for opened electronics?" |
| 4 | Define evaluators: Correctness (LLM-as-judge, inline, plus the `openevals` shortcut), target function, single-example test; Total tool calls (`Run` evaluator, sample run walkthrough) | Same two evaluators with the same code, plus **order-specialist tool calls** | ASCII: where the order specialist's tool calls sit in the trace (main agent → `task` → order-specialist → tools) | Correctness inline (same prompt as `evaluators/evaluators.py`); target function **with identity** (see §6 D2); `count_total_tool_calls_evaluator` inline; `order_specialist_tool_calls_evaluator` |
| 5 | Run an experiment on the full dataset | Same | — | `client.evaluate(target_function, data=dataset_name, evaluators=[...], experiment_prefix="deep-agent-baseline", max_concurrency=5)` |
| 6 | Error analysis in the LangSmith UI | Same, with the deep agent's failure patterns to look for | Table: what to look for (rigid tool chains in the order specialist, no tool for the customer record, judge penalizing extra detail) | — |

## 5. Section 2 outline: `section_2_eval_driven_development.ipynb`

Mirror of `module_2/section_2_eval_driven_development.ipynb` (22 cells).

| # | Module 2 step | Module 5 step | Visual | Code |
|---|---|---|---|---|
| 0 | Title, `eval_process.png`, "The Problem" (excessive tool calls, missing aggregation) | Same; problem list from the Section 1 baseline | `images/eval_process.png` | — |
| 1 | Setup, `db_agent_improvement.png`, get the schema | Same | **New** `images/order_specialist_improvement.svg`: OLD order specialist with `get_order_status`, `get_order_items`, `get_product_info`, `get_order_item_price`, `get_customer_orders` → NEW with `query_my_orders()`. Same layout as `db_agent_improvement.png` | Schema for the prompt |
| 2 | Build SQL agent: `execute_sql` tool, system prompt, `create_agent` | **Build the scoped SQL tool**: `query_my_orders` (shown from `tools/database.py`) and why it can't be a raw `execute_sql` | ASCII: verified `customer_id` (run context) → temp views over that customer's rows → query | Print the tool source; no new agent object (the specialist is a subagent spec) |
| 2b | 🔒 Production security note (read-only user, keyword filtering) | Same note, plus the customer-scope point | Table: what each layer blocks (read-only connection, temp views, SQLite authorizer, row cap, time limit) | — |
| 3 | Quick demo on a question that failed in the baseline | Same | — | Call the tool with a context for CUST-003 on "items and prices in my order ...", then show a cross-customer query is refused |
| 4 | Integrate SQL agent with supervisor HITL; graph; quick test with email resume | Integrate: `create_deep_support_agent(order_tools="sql")`; image; quick test with `SupportContext` | `images/order_specialist_improvement.svg` (NEW panel) | `improved_agent = create_deep_support_agent(order_tools="sql")`; quick test "What's the status of my recent order?" as CUST-003 |
| 5 | Re-evaluate performance (import evaluators from `evaluators`) | Same | — | Same three evaluators imported from `evaluators`; same dataset; `experiment_prefix="deep-agent-sql"` |
| 6 | Compare results in LangSmith | Same | Table: expected direction (tool calls down, order-specialist tool calls down, correctness same or better); spike numbers as a reference | Comparison link |

## 6. Deviations from Module 2

| # | Deviation | Why |
|---|---|---|
| D1 | Agent picture is an image, not a mermaid graph | A deep agent's mermaid graph is one node; the structure lives in the subagents |
| D2 | The target function looks up the customer from the email in the question and passes `context=SupportContext(customer_id=...)` | The deep agent takes a verified customer ID from run context, the way an app does after sign-in, and redacts emails. Module 2's agent asked for the email with a HITL interrupt. Evaluating a harness means calling it the way the app does |
| D3 | Third evaluator: tool calls inside the order specialist | Total tool calls also counts the main agent's delegations and the docs searches; the improvement only changes the order specialist. Module 2's db agent had nothing else in it |
| D4 | One extra example: a cross-customer question (CUST-003 asks about another customer's order; reference: refuses) | Section 2 gives the model SQL. The eval should show that it still can't reach another customer's data |
| D5 | Section 2 shows a scoped tool instead of `execute_sql` | A raw SQL tool lets any customer read every order; the scope guard only checks `customer_id` and `order_id` arguments |
| D6 | Section 2 quick test passes `SupportContext`, not an email resume | No email-verification interrupt in the deep agent (see D2) |
| D7 | Section 2 finds the dataset by name prefix, not "most recent dataset" | Module 2 picks `max(created_at)` over all datasets; other sections (Harbor) create datasets too |

## 7. Decisions

| Decision | Choice | Status |
|---|---|---|
| Notebooks | Two, mirroring Module 2 Sections 1 and 2 | Decided 2026-11-12 |
| Per-section "what's different from Module 2" notes | None; README explains the two paths | Decided 2026-11-12 |
| Dataset | Module 2's 12 questions + 1 cross-customer example, in `module_5/baseline_dataset.json` | Decided 2026-11-12 |
| Evaluators | Correctness, total tool calls, order-specialist tool calls | Decided 2026-11-12 |
| Verifier-middleware experiment | Dropped (not in Module 2's outline) | Decided 2026-11-12 |
| Build method | Generated by `scripts/notebook_builders/build_module5.py`, like Sections 5 and Modules 4/6 (Module 2 is hand-written) | Decided 2026-11-12 |

## 8. Existing assets (verified 2026-11-12)

- `agents/deep_support_agent.py`: `create_deep_support_agent(order_tools="rigid"|"sql", use_checkpointer=...)`, `SupportContext(customer_id, role)`.
- `tools/database.py`: `query_my_orders(query, runtime)`: customer from run context, read-only connection, temp views over the customer's rows, SQLite authorizer, row cap, 2 s limit. `tests/test_query_my_orders.py`: 10 tests.
- `evaluators/evaluators.py`: `correctness_evaluator`, `count_total_tool_calls_evaluator`.
- `workshop_modules/module_2/baseline_dataset.json`: 12 examples, categories account_info, account_summary, analytics, order_history, policies, product_info.
- Images: `offline_eval_process.png`, `final-response-eval.png`, `eval_process.png`, `db_agent_improvement.png` (layout reference).
- Spike (2026-11-09, single run, unaligned judge): rigid 4/12 correct, 132 tool calls; SQL 7/12, 44 tool calls. Experiments `m5-spike-rigid-*`, `m5-spike-sql-*` on dataset `m5-spike-module2-baseline`. The spike script wasn't committed.

## 9. Tasks

Each task ends with a commit. Check each item off here as it lands.

**Housekeeping**
- [x] **T1** Rename `section_3_harbor_evals.ipynb` → `section_5_harbor_evals.ipynb`: builder output name, notebook title ("Module 5, Section 5"), and every reference (`grep -rn "section_3_harbor\|Section 3" docs managed_agent workshop_modules utils`). Update the outline in `docs/2026-11-09-module-5-build-plan.md` to the five sections in §3.

**Verify and spike**
- [x] **T2** Re-verify the spike code: run `tests/test_query_my_orders.py`; invoke `create_deep_support_agent(order_tools="sql")` once with `SupportContext(customer_id="CUST-003")`.
- [x] **T3** Spike the order-specialist evaluator: in one deep-agent trace, find how the order specialist's subtree is identifiable (subagent run name or the `task` tool call's `subagent_type`), and count tool runs under it. Write down the rule. **Result:** the specialist is a chain run named `order-specialist` under the main agent's `task` tool run; count tool runs with that ancestor. On a probe trace: 1 order-specialist tool call vs 2 total (the `task` delegation counts toward the total).

**Data, evaluators, images**
- [x] **T4** Create `workshop_modules/module_5/baseline_dataset.json`: Module 2's 12 examples unchanged, plus one cross-customer example. Use CUST-003's real email from the database, an order that belongs to another customer, and a reference answer that refuses without details. Metadata `category: "authorization"`, `example_number: 13`.
- [x] **T5** Add `order_specialist_tool_calls_evaluator(run)` to `evaluators/evaluators.py` and export it; a unit test in `tests/` on a hand-built `Run` tree (order-specialist subtree vs. other subtrees).
- [x] **T6** Draw `images/deep_support_agent.svg`: main agent → `task` → `order-specialist` (the five rigid tools: `get_order_status`, `get_order_items`, `get_product_info`, `get_order_item_price`, `get_customer_orders`) and `product-policy-specialist` (`search_product_docs`, `search_policy_docs` over the vectorstore); `request_refund` with the approval pause; customer-scope guard; caller identity from context. Same style as `images/harbor_eval_process.svg`. Check that it renders in JupyterLab.
- [x] **T7** Draw `images/order_specialist_improvement.svg`: OLD/NEW panels in the layout of `db_agent_improvement.png`, rigid tools → `query_my_orders()`.

**Notebooks**
- [x] **T8** Add `s1` to `build_module5.py` and generate `section_1_baseline_evaluation.ipynb` per §4.
- [x] **T9** Add `s2` to `build_module5.py` and generate `section_2_eval_driven_development.ipynb` per §5.

**Validate**
- [x] **T10** Run Section 1 end to end from a fresh kernel (13 examples). Record correctness, total tool calls, and order-specialist tool calls in §11.
- [x] **T11** Run Section 2 end to end from a fresh kernel against Section 1's dataset. Record the same numbers and the comparison link in §11. Confirm the cross-customer example is refused in both.
- [ ] **T12** Open both notebooks in JupyterLab (root at the repo) and check that every image renders.

**Docs**
- [x] **T13** README and `workshop_modules/README.md`: Module 5's five sections, and the two learning paths (Modules 1–2 or Modules 4–5). `CLAUDE.md`: Module 5 notes and gotchas. Update the project memory.

## 10. Acceptance criteria

- Both notebooks run top to bottom in a fresh kernel with only the README's setup (`uv sync`, `.env` with model access, the vectorstore built).
- Section 1 and Module 2 Section 1 have the same headings in the same order; the same holds for Section 2 and Module 2 Section 2. Any differences are listed in §6.
- Section 2's experiment uses the same dataset and evaluators as Section 1, and LangSmith's comparison view shows both.
- Total and order-specialist tool calls drop in Section 2. Correctness is the same or better. If a single run shows otherwise, the notebook text matches what actually happened.
- The cross-customer example never returns another customer's order details in either experiment.
- Every image renders in JupyterLab with the server rooted at the repo.
- `tests/` pass, including the new evaluator test.

## 11. Results (2026-11-12, one run each)

| | Section 1 (rigid) | Section 2 (scoped SQL) |
|---|---|---|
| Correctness | 6/13 | 10/13 |
| Total tool calls | 139 | 37 |
| Order-specialist tool calls | 112 | 13 |
| Cross-customer refused | Yes (judged correct) | Yes (judged correct) |
| Experiment links | [deep-agent-baseline-a4b02235](https://smith.langchain.com/o/58980ba0-8cc8-4407-acd7-0409ce9e7ca5/projects/p/2581484d-ed83-4252-ad4a-7452d7ee48fe) | [deep-agent-sql-11120cb7](https://smith.langchain.com/o/58980ba0-8cc8-4407-acd7-0409ce9e7ca5/projects/p/af755166-280b-4fcf-adc9-ba0f6c4f4a34) |

[Comparison view](https://smith.langchain.com/o/58980ba0-8cc8-4407-acd7-0409ce9e7ca5/datasets/79504cf8-de38-4ad2-bfed-0faa6b30e33a/compare?selectedSessions=2581484d-ed83-4252-ad4a-7452d7ee48fe,af755166-280b-4fcf-adc9-ba0f6c4f4a34).

Notes from the runs:
- Six baseline examples used exactly 15 order-specialist tool calls: the specialist's `tool_call_limit`, so it stopped before finishing. Section 1's error-analysis table now says so.
- Five examples flipped from wrong to right (spend comparisons, most expensive item, category counts, the account-type question). One flipped right to wrong: the Sony stock and warranty question. Still wrong in both: the phone-number question and the laptop return policy (judge material for Section 3).
- Bugs found and fixed while running: Section 2 imported `tools.database` before `load_dotenv()`, so `config.py` fell back to an Anthropic default the Gateway can't serve (Module 2 Section 2 has the same import order). The standalone SQL agent now uses `DEEP_AGENT_SMALL_MODEL`, the order specialist's model, since the configured `WORKSHOP_MODEL` (`gpt-5.6-luna`) only supports tools through the Responses API.
- After the runs, both setup cells gained warning filters (Pydantic serializer warnings from `SupportContext`, `list_runs` deprecation) and Section 2 §6 gained a line about checking regressions. Those changes weren't re-run.

## 12. Risks

- **Run-to-run variance.** The spike numbers come from one run each. Tool calls are the steadier signal; the notebook text should lean on them and describe correctness from the actual run.
- **The judge.** The unaligned judge penalizes extra detail and the deep agent's privacy masking. That's expected and sets up Section 3; Section 1's error-analysis table names it so it doesn't read as an agent failure.
- **Time and cost.** About 13 examples × 2 experiments on the deep agent, plus judge calls. Keep `max_concurrency=5` as in Module 2.
- **Product-policy specialist needs the vectorstore** (`build_vectorstore.py`). Setup says so, as Module 4 does.

## 13. Out of scope

- Sections 3 (align) and 4 (Jev): separate PRDs.
- Changes to the Harbor section beyond the rename (T1).
- The `with_verifier` (RubricMiddleware) experiment.
