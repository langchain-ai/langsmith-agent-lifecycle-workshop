# PRD: Module 7 (Monitoring, Governance & Self-Improvement, the code and material for Workshop 10)

Status: Draft for review (2026-11-19). Nothing in this document is built yet. Owner: the Workshop 10 owner named in the build brief. Branch: `feat/module-7-monitoring-governance`.

Build plan (work breakdown, ids, checks): `module-7-build/plan.md` in the local project folder (see "Terms").

## 0. How to read this document

**Terms and paths**

- **ADLC repo**: this repository (`langsmith-agent-lifecycle-workshop`). Paths without a prefix are relative to its root.
- **PROJECT**: the local project folder that holds the research and the non-repo deliverables, on the build machine `~/Documents/LCAE-Exam-Gap-Comparison`. `PROJECT/module-7-build/` holds the brief (`BRIEF.md`), the research notes (`research/`), the three proposals (`proposals/`) and the build plan (`plan.md`).
- **Note NN §x**: section x of the research note whose file name starts with `NN-` in `PROJECT/module-7-build/research/`. **Gap-1** to **gap-6** are the files `09-gap-1-…` to `09-gap-6-…`. Every product fact below cites a note; the notes carry the `https://docs.langchain.com` URLs and the fetch date (2026-11-19).
- **TechHub**: the synthetic customer-support example of this repo. **Deep support agent**: the Module 4 agent built by `create_deep_support_agent(...)` in `agents/deep_support_agent.py`. Its root run is named `deep_support_agent` (gap-2 §1).
- **Run**: one span of a trace. **Trace**: one end-to-end execution of the agent (a tree of runs). **Root run**: the top run of a trace. **Thread** or **conversation**: the traces that share a `thread_id`.
- **Seed**: a JSON file of synthetic production traces shipped with the module. **Fixture**: a JSON file that stands in for an API response (an Insights report, an Engine issue list, a Gateway error body, an alert webhook body).
- **Keyless**: no usable LangSmith API key. **Keyed**: a working key is present.
- **UNVERIFIED**: not confirmed by documentation, installed source or an offline run. Section 22.2 lists every such item and how the design avoids depending on it.

**Where this design comes from.** Three independent proposals (A "lab-first, key-optional", B "on-call shift", C "modular, reuse-first") were scored by three judges. Two judges ranked A first and one ranked C first. This PRD starts from A, takes the Monday plan, the slide discipline and the evaluator packaging from C, and takes the deterministic keyed steps, the incident framing and the answer-key hygiene from B. Section 17.2 records each point where the judges disagreed and what was decided.

**Internal links.** This repository is public. Notion and Instruqt management URLs, the name of the team's demo workspace and people's names are kept out of this file; they are in `PROJECT/module-7-build/BRIEF.md` and in the Notion draft under `PROJECT/module-7-build/notion/`.

**Checked for this PRD on 2026-11-19** (ADLC `.venv`, environment stripped to `PATH` and `HOME`, no network): langsmith 0.14.12 has `Client.batch_ingest_runs(create, update)`, `create_feedback(..., session_id, start_time, extend_trace_retention)`, `read_project`, `has_project`, `create_annotation_queue`, `list_annotation_queues`, `list_project_issues(project_name, *, status, priority)`, `get_insights_report(id, report, project_id, include_runs)`, `request_with_retries`, `create_dataset`, `has_dataset`, `create_examples`, `client.runs.query(...)` (async, with `min_start_time`, `project_ids`, `selects`, `filter`, `tree_filter`), `client.annotation_queues.items.create(queue_id, items=...)`, `client.agents.retrieve` and `create`, `client.evaluators.list(resource_id=...)`, `langsmith.uuid.uuid7_from_datetime`, `langsmith.anonymizer.create_anonymizer`, `langsmith.configure`, `langsmith.tracing_context`. `client.annotation_queues.items.retrieve_count` needs a required `status` argument, which Proposals B and C left out, so this design does not call it. `nbclient`, `nbconvert`, `jsonschema`, `yaml`, `httpx` and `jupyter-execute` are installed; `pandas`, `matplotlib` and `pytest` are not. The 28 existing unit tests pass. `tools/database.py::get_order_status` returns `Order <id> not found.` for an unknown id and is case-sensitive: the database has `ORD-2025-0050` (customer `CUST-003`) and no row for `ord-2025-0050`. `agents/middleware/fault_tolerance.py` line 33 reads `_TRANSIENT_STATUSES = {408, 409, 429}`. `managed_agent/evals/opened-item-return-window/` exists. The docs pages `online-evaluations-code` and `alerts` were re-fetched and agree with note 03 §2.3 and §11, except that the code-evaluator page as fetched today states no time limit (note 03 gives 30 seconds), so no time limit is printed on a slide.

## 1. Goal and non-goals

### 1.1 Goal

Give Workshop 10 ("Monitoring, Governance & Self-Improvement", Level 200, 60 or 120 minutes, instructor-led) everything it needs, on the TechHub deep support agent that Workshops 7 to 9 use:

1. **A module in this repo** (`workshop_modules/module_7/`, four notebooks from one builder) in which every attendee, with or without a LangSmith key, writes a code online evaluator, compares a filter with a sampling rate, sets an alert threshold, routes flagged runs to an annotation queue, reads an Insights report and checks one of its claims, triages an Engine issue board and picks assertions for a test case, masks a trace, and reads Gateway policy blocks. Each exercise has one answer that a script verifies.
2. **A slide deck** in the format of the master deck, with a 60-minute core and a 120-minute extension.
3. **An Instruqt track** in the team's Coding Agent style (Claude Code template), four challenges in its first version.
4. **The Notion catalog page content**, including the talk track, drafted as Markdown for the owner to paste.

### 1.2 Non-goals

- No live model call anywhere on the default path, and no dependence on a deployed agent, a vector store, a paid LangSmith plan, an Organization Admin or a waiting period (rule P1 in section 3).
- No attendee-run Insights report, Engine scan or Gateway policy creation as a required step. They are instructor demos with fallbacks (section 4).
- No re-teaching of tracing, cost categories or offline evals (prerequisite: Workshop 4).
- No change to `simulations/` (it feeds the team's demo workspace on a schedule, note 01 §7.2) and no change to Module 3.
- No webhook receiver in the Instruqt sandbox (the team's tracks request no external ingress, gap-6 §1.4).
- Not taught, one speaker-note line at most: tuned, composite and decision-model evaluators, Tool Gateway, fix validation, Red Teaming, "Online Insights" (changelog only, note 04 §13), header-based policies as a lab.

## 2. Audience and prerequisites

- **Audience**: AI engineers and platform owners on the "Road to production" path (Workshops 7 Deep Agents 201, 8 Evals 201, 9 Deploying, 10 Monitoring). They can call the deployed deep agent and run offline experiments. They have probably never created an online evaluator, an automation rule or an alert, because Module 3 is on the other learning path (note 02 key finding 2 and §1).
- **Prerequisite workshop**: Workshop 4 (Offline Evals).
- **To run the notebooks**: `uv sync` only. No `.env` is needed. A `LANGSMITH_API_KEY` is optional; with one, the same cells also write to the learner's workspace.
- **Catalog wording that this design keeps literally true**: "None required. A LangSmith API key per attendee is recommended: without one the labs still run, but traces print in the notebook instead of linking to LangSmith." (brief; note 07 §1.5).

## 3. Principles

- **P1. The core path of every notebook reads the seed and fixtures from disk and calls no service.** No model, no LangSmith, no vector store. This is new for the repo: every Module 4 to 6 notebook calls a model in its first agent cell (note 01 §7.3). It is what makes the module fully executable and checkable offline.
- **P2. One Setup helper decides the LangSmith state once.** `LANGSMITH_AVAILABLE = setup_langsmith()` from `utils/langsmith_links.py`, as prototyped and tested in four credential states (gap-3 §2 and §3). Without a usable key it calls `langsmith.configure(enabled=False)`, so the `LANGSMITH_TRACING="true"` line of `.env.example` cannot produce upload-failure log lines (gap-3 §1.3, §1.7). No bare LangSmith call sits outside an `if LANGSMITH_AVAILABLE:` (or `if SEEDED:`) branch; the other branch prints the repo's "⏭️ Skipped … On our runs: …" wording (note 01 §4.3).
- **P3. Seeded history is handled by deterministic SDK calls; UI objects are for new traffic.** With a key, yesterday's traces, their scores and the queue items are written with documented SDK calls (`batch_ingest_runs`, `create_feedback`, `annotation_queues.items.create`). The evaluator, automation and alert that the learner creates in the LangSmith UI are attached **without** backfill and are proven on a handful of fresh traces dated now. No checked answer depends on back-dated runs appearing in a chart, on backfill, or on evaluator timing, all of which are UNVERIFIED (note 08 U1 to U3; gap-6 §4 items 5, 6, 14).
- **P4. Every answer is computed locally, and with a key it is also visible in LangSmith.** The local value is the answer; `data/answers.json` is the single source of truth and one checker serves the notebooks, the unit tests and the Instruqt **Check** button.
- **P5. Anything that writes to a workspace is behind a flag** in the `LABEL_IN_QUEUE = False` convention (note 01 §3.5). Flags that only use verified SDK calls default to `LANGSMITH_AVAILABLE` (`UPLOAD_SEED`, `WRITE_SCORES`, `CREATE_QUEUE`, `SEND_LIVE_TRACES`). Flags that use UNVERIFIED requests or create extra objects default to `False` (`MONITORING_AS_CODE`, `TRIP_ALERT`, `CREATE_DATASET`, `GATEWAY_LIVE`).
- **P6. Filters are taught on keys that real traces carry** (run name, `app_version`, `lc_agent_name`, feedback keys), never on a planted topic label. Ground-truth topics live in `data/seed_labels.json` and are never uploaded: real traces have no topic label, which is why Insights exists.
- **P7. Local helpers compute on seed data; they do not imitate the product.** There is no local interpreter for the trace-query language and no simulated Engine. Filter strings are printed in the documented syntax and paired with a plain Python predicate; a test checks that the keyed calls send the same strings unchanged.
- **P8. House style of Modules 4 to 6** (note 01 §3): builder-generated notebooks without outputs, numbered `## N.` sections, "💡 **Try it first**" callouts, opt-in flags, `Step | In the UI` tables, a `Step in this notebook | Same step in the UI` mapping table, `## Recap`. UI steps always start with the navigation sentence for both workspace types (gap-5 §5) and name the time range.
- **P9. UI labels stay off slide faces until one person has clicked through the live product.** Feature and metric names that the docs state (for example the alert metrics Run Count, Cost, Errors, Feedback Score, Latency) may appear; click paths and button labels go in speaker notes and notebook step tables, with both wordings where the docs disagree (note 03 "Unverified" items 5, 6, 16; note 05 key finding 9; gap-5 §5).

## 4. Learning outcomes, mapped to the catalog topics

"Hands-on" means the learner produces a result that a script checks. "Follow-along" means the learner runs prepared cells and reads the result. "Demo" means the instructor shows it on a prepared workspace, with the stated fallback. "Mentioned" means one slide and speaker notes.

| # | Catalog topic | Measurable outcome (the learner can …) | 60 min | 120 min | Why this treatment |
|---|---|---|---|---|---|
| LO1 | Online evals | Write `perform_eval(run, example=None)` that flags exactly the 11 wrong return-window answers among 260 root runs, after seeing a naive check flag 23 | Hands-on (S1) | Hands-on | Code evaluators need no model, are on the free plan and cost nothing (note 03 §2.3; gap-4 §1.2 row 4) |
| LO2 | Online evals (sampling, filters) | State, for three configurations, how many runs are scored and how many of the 11 are caught (all runs 260 and 11; version filter 104 and 11; 25% sample 65 and 3) | Hands-on (S1) | Hands-on | The catalog's own reason: "sampling and filters keep cost down". Filter syntax from note 03 §12.3 |
| LO3 | Online evals (in the product) | With a key: attach the evaluator in the LangSmith UI with a filter and a sampling rate, and see it score fresh traffic | Hands-on for keyed learners; demo otherwise | Same | Included on every plan and needs only `rules:create` (gap-4 §1.3). The lab does not wait for it (P3) |
| LO4 | Online evals (alerts) | Choose the smallest error-count threshold that background errors cannot reach (3) and name the failing tool (`get_order_status`); explain why a green test alert is not proof of delivery | Follow-along (S1) | Hands-on (S1) plus UI steps | Alerts have no SDK method and no documented list endpoint (note 03 §11; gap-6 §1.2). The preview on back-dated runs is UNVERIFIED (gap-6 §4 item 6) |
| LO5 | Annotation-queue routing ("also in the deck") | Select the 11 flagged root runs and put them in a queue; with a key, correct one into a dataset example | Follow-along (S1) | Hands-on (S1) | Queues can be created and filled from the SDK; rules only by UI or REST (note 03 §13) |
| LO6 | Insights | From a report object, name the largest category and the subcategory with the highest error rate, and confirm the report's silent-failure claim with the S1 evaluator (11 of 27 conversations) | Follow-along (S2), 3 minutes | Hands-on (S2) | A real report needs Plus or Enterprise, a workspace provider key and up to 30 minutes (note 04 key findings 2, 3). Reading a saved report offline is verified (note 04 §14.2 A; gap-3 §4.5) |
| LO7 | Online evals, Insights, Engine | Decide, for five findings, between an alert, an online evaluator, an annotation queue and an Engine issue | Mentioned (slide) | Self-check (S2) | Docs contrast in note 04 §12 and note 05 §1 |
| LO8 | Engine | Read an issue (severity, status, type, evidence, proposed fix); find the tool call the agent skipped; choose the next action for three issues; pick the two assertions that separate the wrong answer from the corrected one | Follow-along (S3), 3 minutes | Hands-on (S3) | Engine is not on the Developer plan, needs an Organization Admin, takes up to 20 minutes for a first scan and has no "run now" (note 05 key findings 3 to 5, §11). The paper triage is the notebook exercise note 05 §12 recommends |
| LO9 | LLM Gateway and governance | Tell from a constructed model's base URL which route it uses; map a `402`, `429` and `403` block to its policy type and to the exception LangChain raises; say which block the agent retries | Mentioned plus demo | Hands-on offline (S4) | Policy creation needs `organization:gateway:manage`; the Gateway hands-on is the weakest on every provisioning path (note 06 key finding 3; gap-4 §1.1 finding 7) |
| LO10 | Trace masking ("also in the deck"); PII redaction | Bring the number of uploaded payloads that contain a raw email from more than 0 to 0 with a client anonymizer, without hiding a control string; say what `PIIMiddleware` alone does not protect | Hands-on (S4), masking only | Hands-on (S4) | Fully demonstrable with no key and no model, measured offline (note 06 §4.6) |
| LO11 | Governance (audit logging) | Distinguish "who called which model" (Gateway traces) from "who changed a policy" (organization audit log) | Mentioned | Mentioned; demo only if the demo organization is Enterprise | Audit logs are Enterprise only (note 06 §3) |
| LO12 | Custom Apps ("also in the deck") | Say what a Custom App is and whose permissions it runs with | Mentioned (one slide) | Demo, 2 minutes, if the presenter's workspace allows | Plus and Enterprise only; building with chat needs a workspace model key (note 06 §5) |

Demoed only, never required: LLM-as-judge and thread evaluators (need a provider key stored in the workspace and at least a 2-minute idle wait, note 03 §2.1, §2.2), backfill, a live Insights report, the Engine board with **Open PR**, Gateway policy creation and PII redaction (entitlement "off by default", note 06 key finding 5).

## 5. Module 7 outline

Module number and name: **Module 7**, "Module 7: Monitoring, Governance & Self-Improvement", folder `workshop_modules/module_7/`. Modules 4, 5 and 6 back Workshops 7, 8 and 9 and the branch is already named for Module 7 (note 01 key finding 1 and §8). The catalog's guess "part of `workshop_modules/module_3`" is not followed.

Builder: `scripts/notebook_builders/build_module7.py`, same skeleton as `build_module6.py` (helpers `md`, `code`, `save`; stable cell ids; one list per section under a banner comment that names this PRD; all `save(...)` calls at the end; note 01 §2.1). Build command: `uv run python scripts/notebook_builders/build_module7.py workshop_modules/module_7`.

| Section | Notebook | Title cell | Catalog topic | Cells (about) |
|---|---|---|---|---|
| 1 | `section_1_online_evals_and_alerts.ipynb` | `# Module 7, Section 1: Online Evals, Alerts and Routing` | Online evals; routing to annotation queues | 29 |
| 2 | `section_2_insights.ipynb` | `# Module 7, Section 2: Insights` | Insights | 17 |
| 3 | `section_3_engine.ipynb` | `# Module 7, Section 3: Engine` | Engine | 17 |
| 4 | `section_4_gateway_and_governance.ipynb` | `# Module 7, Section 4: LLM Gateway and Governance` | LLM Gateway and governance; trace masking; Custom Apps | 23 |

Each notebook stands alone (note 01 §3.4): its Setup cell loads the seed again. Four notebooks, one per catalog topic, is the split note 01 §8 suggests, so the catalog references (S1) to (S4) map one to one.

**Shared Setup cell** (constant `SETUP` in the builder; it reproduces note 01 §3.2):

```python
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
```

| State | What the learner sees | Network |
|---|---|---|
| No key, the `.env.example` placeholder, or a rejected key | `⏭️  LangSmith unavailable: <reason>. The labs still run; traces print here instead of linking to LangSmith.` (wording measured in gap-3 §2) | At most the one probe; uploads switched off |
| Working key, project-based workspace | The workshop project link, then `Seeded traffic goes to: Tracing > project 'techhub-deep-agent-production'` | Normal |
| Working key, agent-based workspace (`TECHHUB_AGENT_ID` set in `.env`) | The link, then `Seeded traffic goes to: Tracing > agent 'TechHub support' > environment Production` | `client.agents.retrieve(...)`, and `client.agents.create(id=..., name="TechHub support", source_type="EXTERNAL")` on a 404 (gap-5 §2.1, §2.2). UNVERIFIED live; any error falls back to local mode with one printed line |

## 6. The scenario and the seeded data

### 6.1 The story

TechHub put the deep support agent into production in Workshop 9. Yesterday evening the team shipped version **1.5.0**. The learner is on call this morning with one day of traffic: 200 conversations, 260 customer turns. Five things are wrong or wasteful in that day, and nobody has told the team. The session follows the order an on-call engineer works in: detect (online evals, alerts), understand (Insights), fix (queues, Engine), prevent (masking, Gateway policies). The same silent failure, a wrong return window, is the running example through online evals, Insights and Engine.

All data is synthetic and says so: every run has the tag `seed:m7` and the metadata `synthetic: true`. Customer and order ids are real ids from `data/structured/techhub.db`, so answers can be cross-checked in the database.

### 6.2 What the seed contains

All values are **design constants**. The generator builds them by construction and asserts them; `data/answers.json` is written by the generator and a unit test fails if the generator, the committed seed and the answer key disagree. A builder may change a constant only by changing it here, in the generator and in the slides together.

| Property | Value | Basis |
|---|---|---|
| Conversations (threads) | 200: 140 with one turn, 60 with two | Insights analyses whole conversations in threaded projects ("Only the most recent root run from each thread is used", note 04 §2), so the sample report counts conversations and totals 200 |
| Traces (root runs) | 260 | One upload uses 260 of the 5,000 traces a month that a free organization gets (note 03 §9) |
| Runs | About 3,300; committed file under 5 MB | Lite tree (next row). A real trace has 95 runs and about 600 KB (gap-2 §1 item 3) |
| Tree shape | The "lite tree" of gap-2 §2.1: 3 runs for a direct answer, 14 for one delegation with one tool call. As built (section 21): 10 runs when the specialist answers without a tool or its first tool fails, 13 when the scope guard refuses a lookup (no tool run exists), 33 for a compatibility question (two delegations one after the other, each with its own main-agent model call and two searches). Root `deep_support_agent`; specialists `order-specialist`, `product-policy-specialist`, `general-purpose` under a `task` tool run | Verified by offline capture of the real agent (gap-2 §1, §2.1). Template: `research/09-gap-2-trace-template.json`, sketch: `research/09-gap-2-spike/lite_trace_sketch.py` |
| Tools | Order specialist: `get_order_status`, `get_order_items`, `get_product_info`, `get_order_item_price`, `get_customer_orders`. Product-policy specialist: `search_product_docs`, `search_policy_docs`. Main agent: `task`, `request_refund` | The Module 4 agent's default ("rigid") tools, the configuration that was captured (gap-2 §6.1) |
| Time | 20 hours of original timestamps. `load_seed()` and the uploader shift everything so the newest root run starts 5 minutes before "now" | The Academy technique (note 08 §3.3). 20 hours, not 24, keeps the oldest run inside a one-day window for a whole 120-minute session; the new query calls look back one day by default (note 03 key finding 1), so every query also passes `min_start_time` |
| Versions | `app_version` `1.4.0` for the first 12 hours (120 conversations, 156 root runs), `1.5.0` for the last 8 hours (80 conversations, 104 root runs). `revision_id` `a1b2c3d` and `e4f5a6b` (invented, labelled in the generator). A conversation never spans two versions | `revision_id` is the signal Engine asks for (note 05 §2) |
| Metadata on every run | `thread_id`, `customer_id`, `customer_segment`, `app_version`, `environment` (`production`), `revision_id`, `lc_agent_name`, `seed_trace_key` (stable key such as `t-0042`, because run ids are regenerated on upload), `synthetic`; `ls_agent_type: "subagent"` inside specialists | Real traces carry caller metadata on all runs (gap-2 §4) |
| LLM runs | Name `ChatOpenAI`; `ls_provider: "openai"`, `ls_model_name` `gpt-5.4` (main agent) or `gpt-5.4-mini` (specialists), `ls_model_type: "chat"`; token counts in the four places a real upload has them | gap-2 §3.2. Whether these names are priced in a workspace is UNVERIFIED (note 08 U6), so cost in the lab is computed locally from tokens and a printed, illustrative price table |
| Root inputs and outputs | Inputs `{"messages": [<the new user message>]}`; outputs `{"messages": [<conversation so far>], "files": {}}`. The 13 root runs that failed have `error` set and outputs `{}` (section 21), so 247 root runs have `messages` in their outputs | The format thread evaluators need (gap-2 §3.1). Empty outputs on a failed run are what the LangChain tracer records (measured offline on the build machine) |
| Topics, in `data/seed_labels.json` only, per conversation | `where_is_my_order` 46, `order_not_found` 19, `order_contents` 13, `return_window` 27, `refund_approval` 16, `refund_timing` 9, `compatibility` 25, `spec_lookup` 19, `other_customer_data` 11, `unrelated` 15 | The category tree and counts of the validated sample report (gap-3 §4.4): 78, 52, 44 and 26 per category |
| Seeded feedback | `user_score` (1 thumbs-up, 0 thumbs-down) per conversation, on its last root run: 145 up, 25 down, 30 without a score | Stands in for end-user ratings. Written with `session_id` and `extend_trace_retention=False` (note 03 key finding 2, §9) |
| Not seeded | `wrong_return_window`. The learner's evaluator creates it | |

Topic by version (conversations), fixed so every count below is consistent:

| Topic | 1.4.0 | 1.5.0 | Total |
|---|---|---|---|
| `where_is_my_order` | 26 | 20 | 46 |
| `order_not_found` | 13 | 6 | 19 |
| `order_contents` | 8 | 5 | 13 |
| `return_window` | 11 | 16 | 27 |
| `refund_approval` | 10 | 6 | 16 |
| `refund_timing` | 6 | 3 | 9 |
| `compatibility` | 16 | 9 | 25 |
| `spec_lookup` | 12 | 7 | 19 |
| `other_customer_data` | 7 | 4 | 11 |
| `unrelated` | 11 | 4 | 15 |
| Total | 120 | 80 | 200 |

### 6.3 The planted incidents

Design rule (note 08 §4): each incident shows in one signal and the other signals stay flat; every answer is a value in the seed, never the wording of a model.

| | Incident | How it is planted | Signal that finds it | Signals that stay flat |
|---|---|---|---|---|
| **A** | **Wrong return window** (silent, release 1.5.0) | Of the 27 return-window conversations, 15 are about opened electronics: the 4 on `1.4.0` answer "14 days" after a `search_policy_docs` call; the 11 on `1.5.0` answer "30 days" and their `product-policy-specialist` has no `search_policy_docs` tool run. The 12 about unopened items (7 on `1.4.0`, 5 on `1.5.0`) answer "30 days", correctly. `data/documents/policies/return_policy.md` lines 7 to 13: unopened 30 days, opened 14 days. No other reply in the seed contains "30 days". Story: 1.5.0 added the sentence "Customers have 30 days from delivery to return any item." to the policy specialist's instructions | The code evaluator (S1); the Insights subcategory (S2); Engine issue 1 (S3) | Errors (0), latency, cost, and `user_score`: the 11 conversations have 9 thumbs-up, 2 without a score and 0 thumbs-down. Customers are pleased with the wrong answer |
| **B** | **Order-service error burst** (loud) | 8 root runs with `error` set and an errored `get_order_status` tool run (`OrderServiceUnavailable: get_order_status timed out`), all inside one 3-minute span, 52 to 49 minutes before the newest run. Background: 5 more errored root runs, one pair 2 minutes apart (about 9 hours before the end, tools `get_customer_orders` and `get_order_items`, a database lock) and 3 singles each more than 30 minutes from any other error. 13 errored root runs in total | Error count per window (S1); the highest error rate in the report, "Where is my order", 9 of 46 = 19.6% (S2) | The evaluator, cost |
| **C** | **Order reported as not found** (silent tool result, both versions) | 19 conversations where the customer types the order id in lower case or without dashes. `get_order_status` returns `Order <id> not found.` with status success, exactly what the real tool does for `ord-2025-0050`, and the agent says the order does not exist although it belongs to that customer | Thumbs-down (16 of the 19) in S1; the Insights subcategory (S2); Engine issue 2, status `fixing` with one pull request (S3) | Errors (0), version |
| **D** | **Double delegation on compatibility questions** (costly) | The 25 compatibility conversations each contain two `task` → `product-policy-specialist` branches for the same question. Answers are correct. Corporate customer `CUST-010` asks 9 of them and is the top spender | Cost by subcategory in the report (S2); Engine issue 3, a `finding` in status `watching` (S3); spend by `customer_id` (S4) | Errors, user scores |
| **E** | **An email address stored in a trace** | One `unrelated` conversation in which the customer types `jordan.lee@example.com`. The raw address is in the root run's `inputs.messages[0].content`; the same message in the root outputs and in the LLM inputs reads `[REDACTED_EMAIL]` | A regular expression over root inputs (S4) | Everything else |

Notes on the plants:

- **E follows the measured path.** With `PIIMiddleware` on, an email the user types stays raw in the root run's inputs and is redacted everywhere the model and the saved conversation see it (gap-2 §5, row 1, "the normal case"). No card number and no PII in a `task` argument or an agent reply is planted: gap-2 §5 calls that the worst case, and the agent's own middleware masks card numbers in model output (`agents/deep_support_agent.py`, `_pii_middleware`).
- **Refusals are not errors.** The 11 `other_customer_data` conversations carry the tool message "Access denied: order … does not belong to this customer." and no errored run, as in a real trace (gap-2 §3.4). No exercise depends on them.
- **User scores are flat by version**: 15 thumbs-down in the 120 conversations on `1.4.0` and 10 in the 80 on `1.5.0`, 12.5% each. By cause: 16 in `order_not_found` (12 and 4), 6 in the error burst (all `1.5.0`), 3 others (`1.4.0`).
- **Fresh traces.** `utils/trace_upload.py::send_live_traces(kind, n)` builds a handful of lite traces dated now, tagged `live:m7`, with no model call: `kind="quality"` sends 4 return-window turns of which 2 give the wrong window; `kind="errors"` sends 5 errored root runs (the pattern run offline in gap-6 §2.7, with the root name `deep_support_agent`).

### 6.4 How the seed is generated, loaded and uploaded

1. **Generated, never recorded.** `uv run python scripts/module7_seed.py build` calls `utils.trace_seeding.generate_seed(rng_seed=7)` and writes the files in `workshop_modules/module_7/data/` (section 11). No model, no network, fixed base time, byte-reproducible (`scripts/module7_seed.py verify` regenerates and compares). This follows note 08 §3.8 ("Generate, do not record"; "Put the answer key in the generator").
2. **Keyless learners never upload.** The notebooks load the committed file; `load_seed()` shifts timestamps in memory.
3. **Keyed learners upload from Section 1** (flag `UPLOAD_SEED`) or with `uv run python scripts/module7_seed.py upload`. Steps, from note 08 §3.3 with the fixes of §3.7: shift timestamps; give every run a new id with `langsmith.uuid.uuid7_from_datetime(start_time)` (a root run's id is its `trace_id`); append a per-upload suffix to every `thread_id`; rebuild `dotted_order` breadth first; send `Client.batch_ingest_runs(create=[...])` then `Client.batch_ingest_runs(update=[...])` in batches of 250; `Client.flush()`; resolve the project id with `Client.read_project(project_name=...).id`; write the user scores with `Client.create_feedback(run_id=..., trace_id=..., key="user_score", score=..., session_id=<project id>, start_time=..., extend_trace_retention=False)`.
4. **Safe to re-run.** The uploader first asks for one root run tagged `seed:m7` (`await client.runs.query(project_ids=[...], is_root=True, filter='has(tags, "seed:m7")', min_start_time=<7 days ago>, page_size=1, selects=["ID"])`) and stops with a message if one exists. It never deletes a project and never calls `create_project` on a guessed name (gap-5 §6).
5. **Destination.** `resolve_destination()` returns the project name (`M7_PROJECT`, default `techhub-deep-agent-production`), the project id and the navigation sentence. In an agent-based workspace the learner sets `TECHHUB_AGENT_ID` and the helper uses the Production environment's `tracer_session_name` (the documented compatibility route, gap-5 §2 case A2).
6. **A failed upload never stops the lab.** `upload_seed(...)` returns `SEEDED` (`True` or `False`). Any exception prints one line (`⏭️  Upload failed (<type>). Continuing in local mode.`) and later keyed cells branch on `SEEDED`.

UNVERIFIED until one live run, and therefore never part of a checked answer: that back-dated lite traces are accepted and charted at their own time, that cost is shown for these model names, that seeded feedback behaves like evaluator feedback in filters, the agent-based route (note 08 U1, U2, U6; gap-5 Part 3 items 2 to 4).

### 6.5 The saved Insights report and Engine issue board

Both start from the validated fixtures in `PROJECT/module-7-build/research/09-gap-3-fixtures/` and are **rewritten by the generator from the seed**, so that no number and no sentence contradicts the traces (the judges found three contradictions in the unchanged fixtures: the tool name `query_my_orders`, a thumbs-down on a wrong return-window trace, and a `search_policy_docs` call in one). The structure, key names and labelling ("hand-built sample, not real output") stay as validated; `research/09-gap-3-fixtures/validate_fixtures.py` is re-run on the regenerated files.

- `insights_report_techhub.json`: 4 categories, 10 subcategories, 200 conversations. `num_runs` are the topic counts above. `stats.error_rate` is the share of conversations with an errored root run: "Where is my order" 0.196 (9 of 46), "What is in my order" 0.077, "Refund requests awaiting approval" 0.063, "Single-product spec lookups" 0.053, "Compatibility between products" 0.04, all others 0.0; "Order status and tracking" 0.128. `stats.cost_p50` and `latency_p50` are computed from the seed; "Compatibility between products" has the highest `cost_p50`, about twice "Single-product spec lookups". The five key points are rewritten to match (largest topic and the error burst; the wrong return window with no error; orders reported as missing with no error; the double delegation; out-of-scope requests refused). Highlighted traces carry seed trace keys.
- `engine_issues_techhub.json`: the same three issues. Issue 1 (high, `open`, `actionable`, no fix): its three evidence comments describe three of the 11 seeded traces, each without a `search_policy_docs` call, and the third says the customer gave a thumbs-up and that the online evaluator's `wrong_return_window` score is the cited feedback. Issue 2 (medium, `fixing`, pull request 42) names `get_order_status` and the `Order <id> not found.` result. Issue 3 (low, `watching`, `finding`): `recurrences_since_watching` is computed as the number of compatibility conversations after `watching_since`. All timestamps are on the seed's clock and are shifted by the loader with the seed, so issue 1 is first seen after 1.5.0 shipped.
- Both files stay labelled as hand-built. They are structurally validated, not behaviourally (gap-3 §6 item 12). If a person with a Plus or Enterprise workspace produces real output over the uploaded seed before 2026-12-02, the files are replaced and the notebook cells do not change (gap-3 §4.3, §7 question 3).

### 6.6 The single verifiable answer for each exercise

`check(exercise_id, obj)` in `utils/monitoring_checks.py` returns `(ok, message)` with a specific message on failure. "Graded" means the checker compares with `answers.json` (or its hashes, section 14.3).

| Checker id | Section | Question | Answer | Also visible in LangSmith (keyed) |
|---|---|---|---|---|
| `s1_signals` | S1 §2 | How many root runs errored, how many conversations got a thumbs-down, and how many thumbs-down did the wrong return-window answers get? | 13; 25 (16 of them after an `Order … not found.` tool result); 0 | Errors filter; `user_score` feedback column |
| `s1_evaluator` | S1 §3 | Which root runs give the wrong return window? | 11 trace keys, all `app_version` 1.5.0, none with a `search_policy_docs` run. The naive check flags 23 | Feedback filter on `wrong_return_window` after the scores are written (`feedback.wrong_return_window.score:>0.5`, syntax from note 03 §12.1) |
| `s1_filter_sample` | S1 §4 | Runs scored and wrong answers caught: all root runs; root runs on `app_version` 1.5.0; a fixed 25% sample | 260 and 11; 104 and 11; 65 and 3 (the sampling seed constant is chosen so that 3 holds) | Not applicable |
| `s1_alert` | S1 §5 | Largest number of background errors in any 5-minute window; errors in the burst; smallest threshold the background cannot reach; failing tool in the burst | 2; 8 (inside 3 minutes); 3; `get_order_status` | The alert's historical preview (UNVERIFIED for back-dated runs; not required) |
| `s1_routing` | S1 §6 | How many items does the routing filter select? | 11 | The queue page shows 11 items |
| `s2_report` | S2 §2 | Largest category; subcategory with the highest error rate | "Order status and tracking" (78 conversations, 39%); "Where is my order" (19.6%) | A live report, if one exists |
| `s2_claim` | S2 §3 | In "Return window questions", how many conversations, what error rate, and how many does the S1 evaluator flag? | 27; 0.0; 11 | Not applicable |
| `s3_evidence` | S3 §2 | Which tool call is in a correct trace and missing in the evidence trace, and under which run? | `search_policy_docs`, under `product-policy-specialist` | The trace tree |
| `s3_triage` | S3 §3 | Next action for each issue, one of `apply_fix_and_add_examples`, `review_pull_request`, `save_for_later`, `close_incorrectly_flagged` | Issue 1 `apply_fix_and_add_examples` (open, actionable, no fix yet); issue 2 `review_pull_request` (status `fixing`, one entry in `fixes`); issue 3 `save_for_later` (type `finding`, answers correct) | Not applicable |
| `s3_assertions` | S3 §4 | Which two of six candidate assertions hold for the corrected answer and fail for the recorded one? | `states_14_day_window`, `no_30_day_claim` | Not applicable |
| `s4_leak` | S4 §1 | How many root runs contain a raw email, and where? | 1; in `inputs` only (0 in outputs) | The seeded trace's input |
| `s4_masking` | S4 §3 | Payloads that contain the raw email with the middleware alone, then with the learner's anonymizer; is the control string unchanged? | More than 0; 0; yes. On our runs: 8 of 10, 0 of 10, and 0 of 6 with the anonymizer alone (note 06 §4.6). The check asserts "more than 0, then 0" because the count depends on the installed LangChain version | Three traces side by side (opt-in) |
| `s4_routes` | S4 §4 | Where does `init_chat_model("openai:gpt-5.4")` send calls when `LANGSMITH_GATEWAY=true` and `OPENAI_API_KEY` are both set? | `https://gateway.smith.langchain.com/openai/v1` (note 06 §1.2, verified offline) | Not applicable |
| `s4_blocks` | S4 §5 | Policy type and LangChain exception for each saved response; which status the agent's retry middleware retries | `402` spend limit, `APIStatusError`; `429` rate limit with `Retry-After`, `RateLimitError`; `403` model access, `PermissionDeniedError`; only `429` (note 06 §2.1, §2.7; `fault_tolerance.py` line 33) | Not applicable |

Self-checks with a worked answer in the next cell, not graded: the five-findings decision table (S2 §4), "which control stops which incident" (S4 §6), top spender `CUST-010` (S4, 120-minute cell).

## 7. Section 1 outline: `section_1_online_evals_and_alerts.ipynb`

"Keyed" and "Keyless" say what happens in each state. A cell with "same" behaves identically.

| # | Kind | Heading or purpose | What the cell does and what the learner sees | Calls | Keyed | Keyless |
|---|---|---|---|---|---|---|
| 0 | md | `# Module 7, Section 1: Online Evals, Alerts and Routing` | Ties back to the "hill-climbing loop" row of Module 4 Section 3 (note 02 §7). One bold definition of an online evaluator. Agenda of six steps | none | same | same |
| 1 | md | `## Setup` | "This section calls no model. `uv sync` is all you need; a LangSmith key is optional." A `Where you are / What to set` table: no key; project-based workspace; agent-based workspace (`TECHHUB_AGENT_ID`), with the top-left-control test (note 03 §1.1) | none | same | same |
| 2 | code | Setup | The shared `SETUP` cell | `setup_langsmith` (one `read_project` probe at most); `resolve_destination` | Link and destination line | Skip line |
| 3 | md | `## 1. One day of TechHub production traffic` | The story (6.1). ASCII sketch of the 14-run tree. One sentence: seeded traces carry the 14 meaningful runs; a live trace of the same agent has about 95 because of middleware spans (gap-2 §1) | none | same | same |
| 4 | code | Meet the data | `describe(seed)` then `print_trace(seed, "t-0042")`: "200 conversations, 260 traces, about 3,300 runs, last 20 hours; versions 1.4.0 and 1.5.0", then the tree and the metadata keys of the root run | `utils.trace_seeding` | same | same |
| 5 | md | Put the same day in your workspace (optional) | The full navigation sentence for both workspace types (gap-5 §5). "Set the time range to at least the last 2 days." Why `extend_trace_retention=False` (note 03 §9) | none | read | skip |
| 6 | code | Upload | `UPLOAD_SEED = LANGSMITH_AVAILABLE`; `SEEDED = upload_seed(seed, DEST) if UPLOAD_SEED else False` | `Client.batch_ingest_runs(create=…)`, `(update=…)`, `Client.flush()`, `Client.read_project`, `Client.create_feedback(…, session_id=…, extend_trace_retention=False)`, `await client.runs.query(…, min_start_time=…)` for the re-run guard | `Uploaded 260 traces and 170 user scores. 📊 <project link>` | `⏭️  Skipped: no LangSmith key. Every cell below analyses the same 260 traces locally.` |
| 7 | md | `## 2. Three signals, and what each one misses` | Table: error status; user feedback; reading traces by hand | none | same | same |
| 8 | code | Errors | Lists errored root runs with their failing tool and time: "13 errored traces. 8 of them inside 3 minutes, about 50 minutes ago, tool `get_order_status`." | `utils.monitoring_local.error_windows` | Also prints the search-bar query `status:error` (note 03 §12.1) | same |
| 9 | code | User scores | Thumbs-down by version and by the last tool result: "25 thumbs-down: 12.5% on 1.4.0, 12.5% on 1.5.0. 16 follow an `Order … not found.` tool result, 6 follow an errored run." `check("s1_signals", …)` | local | same | same |
| 10 | md | What just happened | Errors found the burst, thumbs found the missing orders. Neither can find a confident wrong answer; reading 260 traces by hand does not scale. You need a criterion | none | same | same |
| 11 | md | `## 3. An online evaluator is a function of one run` | Image `../../images/online_eval_process.png`. The contract: Python, one `run` dictionary, returns `{feedback key: score}`, define it as `perform_eval(run, example=None)`, standard library plus a few packages, no internet (note 03 §2.3). The polarity warning: here `True` means a problem (note 03 §2.4). The policy text. `> 💡 **Try it first:**` write it in `workshop_modules/module_7/exercises/return_window_evaluator.py` and run `uv run python workshop_modules/module_7/exercises/check.py s1_evaluator` | none | same | same |
| 12 | code | A naive version | Flags every root run whose reply contains "30 days": "Flagged 23 of 260. 12 of them are correct answers about unopened items", with three examples | `apply_evaluator` | same | same |
| 13 | code | The reference version | `from evaluators import wrong_return_window_evaluator, WRONG_RETURN_WINDOW_SOURCE`; applies it; `check("s1_evaluator", …)`: "Flagged 11 of 260. ✅ Verified: exactly the 11 planted traces. All on app_version 1.5.0. None has a search_policy_docs run. Their user scores: 9 up, 0 down." | `utils.monitoring_checks.check` | same | same |
| 14 | code | Write the scores | `WRITE_SCORES = SEEDED`. Runs the evaluator locally over the uploaded root runs and logs each result. The text says this is the documented replacement for `evaluate_run()` (note 03 §1.2) | `Client.create_feedback(run_id=…, trace_id=…, key="wrong_return_window", score=…, session_id=DEST.project_id, extend_trace_retention=False)` | "Wrote 260 scores. 11 runs carry wrong_return_window = 1." plus the search-bar filter to paste | `⏭️  Skipped. On our runs: 11 runs carry wrong_return_window = 1.` |
| 15 | md | `### 3.1 Attach it to live traffic` | `Step / In the UI` table: open your TechHub traces; **Evaluators** tab (**Online Evaluators** in an agent-based workspace, gap-5 §5); **+ Evaluator**; **Code Evaluator** under **Create from scratch**; name `wrong_return_window` (the name and the returned key are the same on purpose, note 03 "Unverified" item 10); filter Run Name is `deep_support_agent`; sampling rate 1.0; leave **Apply to past runs** off (the notebook already scored yesterday); paste the function; **Test Code**; **Save**. Labels are quoted from the docs text | none | Learner follows | "The facilitator shows this step." |
| 16 | code | The function to paste, and fresh traffic | Prints `WRONG_RETURN_WINDOW_SOURCE`. `SEND_LIVE_TRACES = SEEDED`: `send_live_traces("quality", n=4)` | `Client.batch_ingest_runs`, `Client.flush` | "Sent 4 fresh traces (2 give the wrong window). Refresh the feedback column." | `⏭️  Skipped. With the evaluator attached: 2 of the 4 new traces are scored wrong_return_window = 1.` |
| 17 | code | Read the scores back | Counts the live traces that already have the feedback key. Does not wait | `await client.runs.query(project_ids=[…], is_root=True, filter='has(tags, "live:m7")', min_start_time=…, selects=["ID", "FEEDBACK_STATS"])` | "k of 4 scored so far. The time from trace to score is not documented; if it is 0, carry on and re-run this cell later." | Skip line |
| 18 | md | `## 4. Filters and sampling: what you pay for and what you miss` | `Lever / Effect on cost / Effect on coverage` table: filter, sampling rate, weekly evaluator spend limit, retention (note 03 §2.5, §9). A table of filter strings in the documented syntax: `eq(is_root, true)`; `and(eq(is_root, true), eq(metadata_key, "app_version"), eq(metadata_value, "1.5.0"))`; `eq(name, "product-policy-specialist")`; why to filter on `lc_agent_name`, not on `model` (gap-2 §6.2) | none | same | same |
| 19 | code | Sample against filter | Three configurations, then 20 further seeded draws at 25%: "All root runs: 260 scored, 11 caught. Filter app_version 1.5.0: 104 scored, 11 caught. 25% sample: 65 scored, 3 caught. Over 20 draws: minimum, median, maximum." `check("s1_filter_sample", …)` | `utils.monitoring_local.sample`, `FILTERS` | same | same |
| 20 | md | `## 5. From scores to an alert` | Alert anatomy: metric (Run Count, Cost, Errors, Feedback Score, Latency), threshold, aggregation window of 5 or 15 minutes, channel (note 03 §11). `> 💡 **Try it first:**` which threshold can the background errors never reach? | none | same | same |
| 21 | code | The threshold, locally | Errors per 5-minute window as text bars, then: "Background errors: at most 2 in any 5 minutes. Burst: 8 in 3 minutes. Smallest threshold the background cannot reach: 3." `check("s1_alert", …)` | `utils.monitoring_local.error_windows` | same | same |
| 22 | md | The same in the UI | `Step / In the UI` table: **Alerts** icon; metric **Errors**; threshold 3; **Aggregation Window** 5 minutes; read the historical preview; **Send Test Alert**; the documented trap that the test "does not validate the downstream response"; the body is not templated (note 03 §11). States that a burst 50 minutes old cannot trip a live 5-minute window, and that the preview on back-dated runs is UNVERIFIED | none | Learner follows | Reads; facilitator demo |
| 23 | code | What an alert sends, and tripping one | Prints the 12 documented top-level keys from `data/alert_webhook_payload.json`. `TRIP_ALERT = False`: when set and seeded, `send_live_traces("errors", n=5)` | `Client.batch_ingest_runs` | Runs when the flag is set: "Sent 5 errored runs dated now. When the alert fires is not documented." | Payload keys only |
| 24 | md | `## 6. Route what was flagged to people` | Image `../../images/data_flywheel.png`. A rule is an item type, a filter, a sampling rate and an action (note 03 §3). `> 💡 **Try it first:**` which filter selects root runs scored `wrong_return_window` = 1? | none | same | same |
| 25 | code | Route | Local: the filter string `and(eq(is_root, true), eq(feedback_key, "wrong_return_window"), gt(feedback_score, 0.5))` with its predicate selects 11; `check("s1_routing", …)`. `CREATE_QUEUE = SEEDED`: get or create the queue and add the 11 uploaded runs; if the queue already exists it adds nothing | `Client.list_annotation_queues(name=…)`, `Client.create_annotation_queue(name="techhub-deep-agent-return-window-review", description=…, rubric_instructions=…)`, `await client.annotation_queues.items.create(queue_id, items=[{"item_type": "RUN", "run_id": …, "project_id": …, "start_time": …}])` (note 03 §4) | "Queue techhub-deep-agent-return-window-review: 11 items sent. Open **Annotation Queues** to see them." | "11 runs selected. ✅ Verified." |
| 26 | md | Automate it for new traffic, and review one item | Two `Step / In the UI` tables. (1) **+ New** > **New Automation**; **Item Type** Runs; filter on feedback key `wrong_return_window`; action **Add to Annotation Queue**; leave **Apply to Past Runs** off (note 03 §3). (2) The four reviewer steps of Module 3: validate; add feedback; correct the output to "14 days" in **Classic Trace View**; **Add to Dataset** `techhub-deep-agent-regressions` (note 03 §4; note 02 §2.1) | none | Learner follows | Reads |
| 27 | code | Optional: monitoring as code | `MONITORING_AS_CODE = False`. Always prints the two request bodies; sends them only when the flag is set and seeded, after listing rules and skipping a duplicate `display_name`, inside `try/except` that prints the UI steps on any error | `client.request_with_retries("GET", "/api/v2/runs/rules", …)`, `("POST", "/api/v1/runs/rules", json={… "code_evaluators": [{"code": WRONG_RETURN_WINDOW_SOURCE, "language": "python"}], "filter": "eq(is_root, true)", "sampling_rate": 1.0})`, and the same endpoint with `add_to_annotation_queue_id` (gap-6 §1.1, §2.1 to §2.3) | Sends when set. Labelled UNVERIFIED (gap-6 §4 item 1) | Prints the bodies and `⏭️  Not sent` |
| 28 | md | Mapping table and `## Recap` | `Step in this notebook / Same step in the UI` table. One paragraph on what was only shown: LLM-as-judge and thread evaluators (workspace model key, `messages` key, idle time at least 2 minutes, note 03 §2.2). Five recap bullets. `**Next:**` Section 2 | none | same | same |

## 8. Section 2 outline: `section_2_insights.ipynb`

| # | Kind | Heading or purpose | What the cell does and what the learner sees | Calls | Keyed | Keyless |
|---|---|---|---|---|---|---|
| 0 | md | `# Module 7, Section 2: Insights` | "An online evaluator answers a question you wrote down. Insights is for the questions you did not." Agenda | none | same | same |
| 1 | md | `## Setup` | No prerequisites for the core path. What a live report needs: Plus or Enterprise, a model configuration backed by a workspace provider key, up to 30 minutes (note 04 key findings 2, 3) | none | same | same |
| 2 | code | Setup | Shared `SETUP`; loads `seed_labels.json`; `INSIGHTS_REPORT_ID = os.getenv("M7_INSIGHTS_REPORT_ID")` | as Section 1 | same | same |
| 3 | md | `## 1. How Insights works` | Summarize, cluster, report. Facts table: up to 1,000 traces; "up to 30 minutes"; in a project with threads it analyses whole conversations; the workspace's own provider key pays (note 04 §2, §3, §10) | none | same | same |
| 4 | code | Load a report | Live report if keyed and an id is set; otherwise the sample, with the printed line "⏭️  Reading the sample report shipped with the module (hand-built from the seed, not real Insights output)." | `client.get_insights_report(id=…, project_id=DEST.project_id, include_runs=False)` or `InsightsReportResult(**json.loads(…))` (round trip verified offline, gap-3 §4.5) | Live or sample | Sample |
| 5 | code | Executive summary | Prints `report.report.key_points` and the highlighted traces (rank, reason) | attribute access | same | same |
| 6 | md | `## 2. Read it top down` | Executive summary, categories, subcategories, traces (note 04 §8). A `Look at / What to look for` table | none | same | same |
| 7 | code | Categories | Top-level categories sorted by `num_runs` with share, `error_rate`, `latency_p50`, `cost_p50`. Uses `parent_id is None`, not `level` (gap-3 §4.3): "Order status and tracking 78 (39%) …" | attribute access | same | same |
| 8 | code | Subcategories | Ten rows; `check("s2_report", …)`: "Highest error rate: Where is my order (19.6%). ✅" | `utils.monitoring_checks` | same | same |
| 9 | md | `## 3. Silent failures have a 0% error rate` | "Return window questions" and "Order reported as not found" both show 0.0. Categories are model output; metadata and tool results are fact. Check one claim | none | same | same |
| 10 | code | Check the claim against the traces | Runs the Section 1 evaluator on the 27 return-window conversations (selected through `seed_labels.json`, which exists only because the data is synthetic) and prints highlighted trace 1 as a tree: "Report: 'repeatedly gives 30 days for opened electronics'. Traces: 11 of 27. product-policy-specialist answered without calling search_policy_docs." `check("s2_claim", …)` | `apply_evaluator`, `print_trace` | same | same |
| 11 | md | `## 4. What should each finding become?` | `> 💡 **Try it first:**` for each of the five key points choose one of: alert, online evaluator, annotation queue, Engine issue, nothing. An empty table to fill | none | same | same |
| 12 | code | Worked answer | Prints a five-row table with a choice and one sentence of reasoning each, and says where two choices are both defensible. Not graded | none | same | same |
| 13 | md | `## 5. From a subcategory to a queue to a dataset` | The UI path: report, category, subcategory, traces table, select rows, **Add to Annotation Queue** (100 items per action); the exact control inside the report view is UNVERIFIED (note 04 §11). The Academy's order: review first, then dataset | none | same | same |
| 14 | code | One test case | Builds one dataset example (the customer's question and the corrected answer, "14 days from delivery for opened electronics") and prints it. `CREATE_DATASET = False`: when set and keyed, adds it to `techhub-deep-agent-regressions` after checking it is not there already | `Client.has_dataset`, `Client.create_dataset`, `Client.create_examples` | Runs when the flag is set | Prints the example |
| 15 | md | `## 6. Run a real report (in the UI)` | Steps: **+ New** > **New Insights Report**, the guided questions, **Run job** (note 04 §4). Requirements and cost. Start it at the beginning of a session and read it at the end. Why this notebook does not call `client.generate_insights`: it needs `chat_histories`, creates a new project and can store your model key as a workspace secret (note 04 key findings 4 to 6) | none | Learner with the plan and key may follow | Reads |
| 16 | md | `## Recap` | Four bullets and `**Next:**` Section 3 | none | same | same |

## 9. Section 3 outline: `section_3_engine.ipynb`

| # | Kind | Heading or purpose | What the cell does and what the learner sees | Calls | Keyed | Keyless |
|---|---|---|---|---|---|---|
| 0 | md | `# Module 7, Section 3: Engine` | The five-step loop: detect, diagnose, propose a fix, track with examples, reopen (note 05 §1). The docs' sentence: "Use Insights to understand how people use your agent. Use Engine to find out what is going wrong and what to change." | none | same | same |
| 1 | md | `## Setup` | None for the core path. A table of who can run Engine on each provisioning path (condensed from gap-4 §1.2 rows 12 to 14) | none | same | same |
| 2 | code | Setup | Shared `SETUP`; `ENGINE_ENABLED = os.getenv("M7_ENGINE_ENABLED") == "true"` | as Section 1 | same | same |
| 3 | md | `## 1. What Engine reads` | Errors, unusual traces, wrong answers that raise no error, and feedback from online evaluators, annotation queues and users; trace scope is one Run Name and one Metadata condition; `revision_id` ties traces to commits (note 05 §2, §4, §11) | none | same | same |
| 4 | code | Is this project ready for Engine? | Counts runs that carry `revision_id`, `environment`, `app_version`; lists feedback keys; prints the two scope conditions that fit (`Run Name is deep_support_agent`, `environment is production`, gap-2 §6.3) | local | same | same |
| 5 | md | `## 2. Read the issue board` | An issue has `name`, `description`, `severity` (0 urgent to 3 low), `status` (`open`, `fixing`, `watching`, `completed`, `ignored`), `type` (`actionable` or `finding`), `tags`, `proposed_fix`, `fixes` (gap-3 §4.1). The `list_project_issues` docstring lists keys that do not exist | none | same | same |
| 6 | code | Load the issues | Live if keyed and `ENGINE_ENABLED`, inside `try/except` that falls back to the sample; otherwise the sample, labelled hand-built. Sorted in Python on `severity`: three lines, `[high] open …`, `[medium] fixing … PR 42`, `[low] watching …` | `client.list_project_issues(DEST.project_name)` with no `priority=` argument (it is not a real filter, gap-3 §4.2), or the fixture's `issues` list | Live or sample | Sample |
| 7 | code | Open issue 1 | Prints the description, the proposed fix and the three evidence comments; then prints one evidence trace beside a correct `1.4.0` trace of the same kind of question. `check("s3_evidence", …)`: the missing call is `search_policy_docs` under `product-policy-specialist` | `print_trace` | same | same |
| 8 | md | `## 3. Triage` | `> 💡 **Try it first:**` write `next_action(issue)` in `exercises/triage.py`: one of four action codes from the issue's fields. What each action teaches Engine ("Engine learns from the reviewer", note 05 §4). Label note: the docs pages say **Watch**, the changelog says "Save for later" and a **Close** menu (note 05 key finding 9) | none | same | same |
| 9 | code | The reference rule | `check("s3_triage", next_action)`: three rows with the action and the fields that decide it, plus two extra cases | `utils.monitoring_checks` | same | same |
| 10 | md | `## 4. Turn evidence into test cases` | **Add offline examples**, then **Add to Dataset** or **Edit in annotation queue**; an assertion is a short claim about a correct answer (note 05 §6). `> 💡 **Try it first:**` six candidate assertions; pick the two that hold for the corrected answer and fail for the recorded one | none | same | same |
| 11 | code | Pick the assertions | Prints the recorded answer, the corrected answer and the six candidates; `MY_ASSERTIONS = [...]`; `check("s3_assertions", …)`; builds the offline example (inputs, corrected output, the two assertions) and prints it. `CREATE_DATASET = False`: adds it to the dataset when set and keyed | `Client.create_examples` when set | Runs when the flag is set | Prints the example |
| 12 | md | `## 5. The proposed fix, and what would prove it` | Shows the planted sentence of 1.5.0 and the proposed instruction (always call `search_policy_docs`, name the product condition). Engine never merges; a Context Hub or prompt fix is stored as a proposal until a person applies it (note 05 key finding 7, §5). The offline proof is the Workshop 8 job: the Harbor task `managed_agent/evals/opened-item-return-window` already tests this behaviour. This notebook does not re-run the agent | none | same | same |
| 13 | code | Watch the fix with the evaluator you already have (120-minute path) | Runs the Section 1 evaluator over two small follow-up sets from the generator, 10 traces each: before the fix 4 flagged, after the fix 0. The text says plainly that Engine reopens an issue on its own later scans and that this cannot be forced (note 05 §8, §12); the evaluator's scores are one of the signals Engine reads | `apply_evaluator` | same | same |
| 14 | md | `## 6. In the product` | `Step / In the UI` table: **Engine** in the sidebar; **+ Set up another project**; analysis level; **Start Analyzing**; **Accept & Continue**; **Open trace**; **Add offline examples**; **Flag for Engine** (note 05 §3, §4). Facts: an Organization Admin enables it, the first scan takes up to 20 minutes, a run costs about 7 to 45 LSU, set a spend limit (note 05 key findings 4, 5) | none | Follow if your organization has Engine | Facilitator demo |
| 15 | md | `## Recap` | Four bullets and `**Next:**` Section 4 | none | same | same |

(Section 3 has 16 cells in this table; the builder may split cell 7 or 11 into a markdown and a code cell, which gives the 17 in section 5.)

## 10. Section 4 outline: `section_4_gateway_and_governance.ipynb`

| # | Kind | Heading or purpose | What the cell does and what the learner sees | Calls | Keyed | Keyless |
|---|---|---|---|---|---|---|
| 0 | md | `# Module 7, Section 4: LLM Gateway and Governance` | Governance is "what agents do at runtime" (note 06 §6). Picks up the Module 4 warning "Traces are a separate control" (`build_module4.py` line 418). Agenda | none | same | same |
| 1 | md | `## Setup` | "Everything in this section runs with no key. One optional cell at the end calls the Gateway." | none | same | same |
| 2 | code | Setup | Shared `SETUP` | as Section 1 | same | same |
| 3 | md | `## 1. An email address in yesterday's traces` | The customer typed it. `PIIMiddleware` was on | none | same | same |
| 4 | code | Find it | Applies an email pattern to the inputs and outputs of every root run: "1 root run contains a raw email, in its inputs. The same message in its outputs reads [REDACTED_EMAIL]." `check("s4_leak", …)` | local | same | same |
| 5 | md | `## 2. Three controls, three places` | The table of note 06 §4.5: `PIIMiddleware` (what the model sees), a Gateway data policy (what the provider sees), client-side trace masking (what LangSmith stores) | none | same | same |
| 6 | md | `## 3. Prove what leaves the process` | Explains the capture client: a LangSmith client whose HTTP layer records uploads and answers locally. Nothing leaves the machine (note 06 §4.6) | none | same | same |
| 7 | code | Run 1: middleware only | `create_agent(scripted_model([...]), tools=[], middleware=[PIIMiddleware("email", strategy="redact", apply_to_input=True, apply_to_output=True)])` traced into `offline_client()`: the final state shows `[REDACTED_EMAIL]`, and "N of M uploaded payloads still contain the raw email" (on our runs 8 of 10) | `langchain.agents.create_agent`, `PIIMiddleware`, `langsmith.tracing_context(enabled=True, client=client)`, `Client.flush`. All HTTP is captured locally | same | same |
| 8 | md | Where they are | Root input and output, the two hook spans, the raw model output. `> 💡 **Try it first:**` write `build_anonymizer()` in `exercises/masking.py` | none | same | same |
| 9 | code | Run 2 and run 3 | Run 2: the same agent with `Client(anonymizer=create_anonymizer([{"pattern": EMAIL, "replace": "<email>"}]))`: 0 payloads, and a control string without PII is uploaded unchanged. Run 3: anonymizer without middleware: 0 payloads, but the model saw the email. `check("s4_masking", build_anonymizer)` | `langsmith.anonymizer.create_anonymizer`, `Client(anonymizer=…)` | same | same |
| 10 | code | Three traps | A three-row table `Setting / What you expect / What happens`: `LANGSMITH_HIDE_INPUTS` works only as lowercase `true` (shown in three subprocesses, because the SDK caches the first value it reads); `tracing_context(enabled="local")` still uploads LangChain runs (gap-3 §1.2); calling an anonymizer on your own dictionary mutates it (note 06 §4.3) | `Client()` in child processes, captured locally | same | same |
| 11 | md | `## 4. The LLM Gateway: one control layer` | In beta. The eight request steps. The three routes table (`LANGSMITH_GATEWAY=true`; the standard endpoint; the `langsmith:` provider string) (note 06 §1.1, §1.2) | none | same | same |
| 12 | code | Resolve the route without calling anything | Inside `mock.patch.dict(os.environ, …, clear=True)`, constructs `init_chat_model("openai:gpt-5.4")` and `init_chat_model("anthropic:claude-haiku-4-5")` with dummy keys under five environments and prints base URL and key source. Never invoked. `check("s4_routes", …)`. A note that the README sentence "provider keys win if several are set" is wrong for this case (note 06 "Unverified or conflicting" item 1) | `langchain.chat_models.init_chat_model` (construction only) | same | same |
| 13 | md | `## 5. What a policy block looks like` | Five policy types, where each is created, scopes, what the caller gets; all creation needs `organization:gateway:manage` (note 06 §2.1). `> 💡 **Try it first:**` three responses, name the policy type | none | same | same |
| 14 | code | Three blocked calls, replayed | `for kind in ("spend", "rate", "model_access"): gateway_replay(kind).invoke("ping")` inside `try/except`: status, exception class, `Retry-After`, and `request blocked by gateway policies: <name>`. Then prints the `_TRANSIENT_STATUSES` line of `agents/middleware/fault_tolerance.py`, copied at build time with the anchor technique of `build_module5.py`. `check("s4_blocks", answers)` | `langchain_openai.ChatOpenAI` on `http://offline.invalid/openai/v1` with `max_retries=0` and an `httpx.MockTransport` that returns the saved bodies | same | same |
| 15 | md | A spend cap is not a pre-check | "The request that crosses the cap still succeeds, and only later requests are blocked" (note 06 §2.2). What the TechHub agent does on a block: `429` is retried and then falls back; `402` and `403` skip retries; fallbacks on the same key are blocked too (note 06 §2.7; UNVERIFIED by a live run). A cap per end customer needs a header-based policy (note 06 §2.6) | none | same | same |
| 16 | code | Who spends what (120-minute path) | Estimated spend per `customer_id` and per subcategory from the seed's token counts and a small price table printed in the cell and labelled illustrative: "Top spender: CUST-010. Costliest subcategory: Compatibility between products." Then four lines of arithmetic on the day's requests in time order under a daily cap scoped to the agent's API key: request N crosses the cap and still succeeds | `utils.monitoring_local.cost_of` | same | same |
| 17 | md | `## 6. Which control stops which incident?` | `> 💡 **Try it first:**` a five-row table to fill: incidents A to E against alert, online evaluator, Engine issue, Gateway spend limit, trace masking, none | none | same | same |
| 18 | code | Worked answer | Prints the table with one sentence each: A, no governance control prevents it; the online evaluator detects it and a dataset example stops it returning. B, the alert. C, an Engine issue and a code fix. D, a Gateway spend limit caps the bill and does not fix the cause. E, client-side trace masking; a Gateway data policy scans requests to the provider, not application traces (note 06 §2.5). Not graded | none | same | same |
| 19 | md | `## 7. Who did what: traces, the audit log, roles and Custom Apps` | The three-row table of note 06 §3 (who called which model; who changed a policy; tool calls). Roles in three lines (note 06 §6). Custom Apps in three lines with the docs link (note 06 §5) | none | same | same |
| 20 | code | Optional: call the Gateway for real | `GATEWAY_LIVE = False`. With the flag and `LANGSMITH_GATEWAY_API_KEY`: `GET /v1/models` and one raw request, printing status, `Retry-After`, `X-LangSmith-Gateway-Metadata` and the body (the cell of note 06 §2.8). The only cell in the module that can spend model tokens | `httpx.get`, `httpx.post` to `https://gateway.smith.langchain.com/v1/…` | Runs only with the flag and a Gateway key. UNVERIFIED live | `⏭️  Skipped` |
| 21 | md | `## 8. Where to go next` | `Topic / Where` table: docs pages for policies, fallbacks, audit logs, Custom Apps; the Academy Engine course; Modules 3 and 5 | none | same | same |
| 22 | md | `## Recap` | A `Layer / What it blocks / Who configures it` table in the repo's security-note style | none | same | same |

## 11. Supporting files

All paths are relative to the ADLC repo. Nothing in this table exists yet.

| Path | New or changed | Purpose |
|---|---|---|
| `scripts/notebook_builders/build_module7.py` | New | Generates the four notebooks. Reads source excerpts at build time and fails on a missing anchor |
| `workshop_modules/module_7/section_1_online_evals_and_alerts.ipynb`, `section_2_insights.ipynb`, `section_3_engine.ipynb`, `section_4_gateway_and_governance.ipynb` | New (build output) | The notebooks, committed without outputs |
| `utils/trace_seeding.py` | New | `generate_seed(rng_seed=7) -> dict` (runs, feedback, labels, follow-up sets, the two rewritten fixtures, answers); `load_seed(path=None, shift_to_now=True)`; `answer_key(seed)`; `describe(seed)`; `print_trace(seed, trace_key)`; `shift_to_now`, `remap_ids`, `rebuild_dotted_order`. Plain dictionaries, `random.Random(7)`, standard library only |
| `scripts/module7_seed.py` | New | Command line: `build`, `verify`, `upload [--project NAME]` |
| `scripts/module7_connect_langsmith.py` | New | Key entry for the Instruqt setup challenge and for anyone who prefers a prompt to editing `.env`: masked input, endpoint probe, `--skip`, a state file (section 14.3). Makes a network call only when a key is supplied |
| `workshop_modules/module_7/data/techhub_production_day.json` | New (generated, committed) | The seed: 260 traces, about 3,300 runs, under 5 MB |
| `workshop_modules/module_7/data/seed_labels.json` | New (generated) | Ground truth per conversation (topic, subcategory name, incident). Never uploaded |
| `workshop_modules/module_7/data/answers.json`, `answer_hashes.json` | New (generated) | The answer key, and SHA-256 hashes of each answer's canonical JSON for places where the plain key is removed (section 14.3) |
| `workshop_modules/module_7/data/followup_traces.json` | New (generated) | Two sets of 10 traces (before and after the fix) for Section 3 cell 13 |
| `workshop_modules/module_7/data/insights_report_techhub.json`, `engine_issues_techhub.json` | New (generated from the validated fixtures) | Section 6.5 |
| `workshop_modules/module_7/data/gateway_blocked_responses.json` | New (hand-written from the docs) | The three documented block responses (`402`; `429` with `Retry-After`; `403`): status, headers, body, and the docs URL of each (note 06 §2.1) |
| `workshop_modules/module_7/data/alert_webhook_payload.json` | New (hand-written from the docs) | The 12 documented top-level keys of an alert webhook body, with the docs URL (note 03 §11) |
| `workshop_modules/module_7/exercises/return_window_evaluator.py`, `read_the_report.py`, `triage.py`, `masking.py` | New | Stubs for the "Try it first" callouts and the Instruqt track. Each has one or two functions with a docstring and a body that raises `NotImplementedError` |
| `workshop_modules/module_7/exercises/solutions/` (the same four file names) | New | Reference implementations. `return_window_evaluator.py` there imports nothing and equals `WRONG_RETURN_WINDOW_SOURCE` |
| `workshop_modules/module_7/exercises/check.py`, `show_report.py` | New | `check.py <id>` prints PASS or a specific FAIL line and sets the exit code; it only calls `utils.monitoring_checks`. `show_report.py` prints the saved report and issue board (the 60-minute follow-along) |
| `evaluators/online_evaluators.py` | New | Standard library only. `perform_eval(run, example=None)` (the return-window check, in the documented contract) and `WRONG_RETURN_WINDOW_SOURCE = inspect.getsource(perform_eval)`, the text that is pasted or posted to LangSmith |
| `evaluators/__init__.py`, `evaluators/README.md` | Changed | Export `wrong_return_window_evaluator` (an alias of `perform_eval`, so the package does not export a generic name) and `WRONG_RETURN_WINDOW_SOURCE`; list both in the docstring and README (note 01 §6.4) |
| `utils/langsmith_links.py` | Changed, additive | Adds `langsmith_status()`, `setup_langsmith()`, `collect_run_tree()`, `print_run_tree()`; `trace_link` yields the collector and prints the run tree when LangSmith is unavailable. Source: `research/09-gap-3-fixtures/prototype_langsmith_links.py`. Existing `project_url`, `trace_url` and `with trace_link("…"):` calls in Modules 4 and 5 keep working (gap-3 §3) |
| `utils/trace_upload.py` | New | Keyed helpers only: `resolve_destination(available)`, `upload_seed(seed, dest)`, `write_scores(...)`, `send_live_traces(kind, n)`. Never calls `create_project`; removes `LANGSMITH_AGENT_ID` and `LANGSMITH_AGENT_ENVIRONMENT` from the process (gap-5 §2.2) |
| `utils/monitoring_local.py` | New | `apply_evaluator(perform_eval, runs)`, `sample(runs, rate, seed)`, `error_windows(runs, minutes)`, `FILTERS` (documented filter string paired with a Python predicate), `cost_of(run, price_table)`. Every docstring says "a calculation on seed data, not the product" |
| `utils/monitoring_checks.py` | New | `check(exercise_id, obj) -> (ok, message)` and the public test cases used for diagnostic messages |
| `utils/offline_capture.py` | New | `Capture` and `offline_client(**client_kwargs)` (note 06 §4.6); `scripted_model(replies)` (a small chat model that keeps its replies in a module-level list, gap-2 §6.5); `gateway_replay(kind)` |
| `utils/monitoring_rest.py` | New | `ls(client, method, path, **kw)` (always the full `/api/…` path, gap-6 §1.1); body builders `code_evaluator_rule(...)`, `queue_rule(...)` that return dictionaries; `list_rules(...)` |
| `tests/test_trace_seeding.py`, `test_online_evaluators.py`, `test_monitoring_local.py`, `test_monitoring_checks.py`, `test_offline_capture.py`, `test_module7_fixtures.py`, `test_trace_upload.py`, `test_monitoring_rest.py`, `test_langsmith_links_keyless.py`, `test_module7_notebooks.py`, `test_module7_sdk_surface.py` | New | `unittest`, no network (section 20) |
| `scripts/verify_module7_offline.py` | New | Executes the four notebooks with `nbclient` on scratch copies in a stripped environment with a socket guard, and asserts every "✅ Verified" line |
| `.env.example` | Changed | Commented optional lines `M7_PROJECT`, `TECHHUB_AGENT_ID`, `TECHHUB_AGENT_ENVIRONMENT`, `M7_INSIGHTS_REPORT_ID`, `M7_ENGINE_ENABLED`, with the warning never to put `LANGSMITH_AGENT_ID` next to `LANGSMITH_PROJECT` (gap-5 §2) |
| `verify_setup.py` | Changed | `FIXES` entries for `402` and `429`, and the `403` text no longer says only "the key lacks gateway:invoke": a model access policy also returns `403` (note 06 "Unverified or conflicting" item 2) |
| `README.md`, `workshop_modules/README.md`, `CLAUDE.md` | Changed | Register Module 7 in the places listed in note 01 §6.1 to §6.3 |
| `scripts/notebook_builders/build_module4.py` (line 866), `build_module6.py` (line 583), and the two regenerated notebooks | Changed | The two forward references to "the Monitoring and Governance workshop" name Module 7. Line 418 of `build_module4.py` (the trace-masking warning) gains a pointer to Module 7 Section 4 |
| `pyproject.toml`, `uv.lock`, `simulations/`, Module 3 | Not changed | No new dependency. Tables are printed with plain string formatting and charts are text bars, because `pandas` and `matplotlib` are not installed |

A pull request with these files touches `evaluators/**`, so the required "Eval Regression Gate" check runs by itself and no line in `evals/DEMO_TRIGGER.md` is needed (note 01 §7.2). The new evaluator file imports only the standard library, so it cannot break the gate's imports.

Outside the repo (in `PROJECT`): the deck under `PROJECT/decks/workshop-10-monitoring/`, the Instruqt track under `PROJECT/module-7-build/instruqt/adlc-monitoring-governance/`, the Notion drafts under `PROJECT/module-7-build/notion/`.

## 12. Runs of show

All minutes are **estimates**. The team's guide requires a dry run to set time boxes (note 07 §2.7); the dry run is a deliverable (plan id `V2`) and its measured times replace these numbers in the Notion page. "S1" to "S4" are the notebook sections; the bracketed challenge is the Instruqt challenge.

### 12.1 Monday 2026-11-23: 60 minutes, slides plus demo, no lab

No track can exist on Monday (no `instruqt` CLI on the build machine, a usage-limit banner on the organization, note 10), and the notebooks are a stretch goal. Every demo has a fallback that needs nobody's help. Deck order: `order-monday.txt` (31 slides, the core deck without the six lab slides).

| Start | Block | Minutes | What happens | Fallback |
|---|---|---|---|---|
| 0:00 | Open | 2 | What they leave with | none needed |
| 0:02 | Where we are; one day of traffic; five problems | 5 | Slides `w10-agenda` to `w10-incidents` | none needed |
| 0:07 | Online evals | 8 | Slides `m-online-evals` to `w10-filter-sample` | none needed |
| 0:15 | Demo: an online evaluator | 7 | In the presenter's demo workspace: the **+ Evaluator** panel and one existing evaluator's scores on the simulated traffic | If Section 1 landed (stretch): run its keyless cells 12, 13 and 19 from a laptop. Otherwise stay on slide `w10-code-evaluator` |
| 0:22 | Alerts, automations, queues | 8 | Slides, then the alert form up to the preview and **Send Test Alert** | Slides `w10-alert-anatomy` and `threshold` only |
| 0:30 | Insights | 7 | Slides, then a report generated the day before, if the workspace plan allows | Slides `w10-insights` and `w10-silent`; the sample numbers are on the slide |
| 0:37 | Engine | 8 | Slides, then a prepared issue if Engine is enabled in the demo organization (unknown today, note 05 open question 4) | Slides `t-engine`, `w10-engine-issue`, `w10-engine-limits` |
| 0:45 | Governance | 9 | Slides; a policy and a blocked call only if the presenter has the access | Slides `w10-three-controls` to `w10-masking`; if Section 4 landed, its keyless masking cells |
| 0:54 | Custom Apps, recap, questions | 6 | Slides `w10-custom-apps`, `w10-prevent-map`, `w10-recap` | none needed |
| 1:00 | End | | 2+5+8+7+8+7+8+9+6 = 60 | |

### 12.2 The 120-minute and the 60-minute run with the lab

| # | Block | 120 min | 60 min | Material |
|---|---|---|---|---|
| 0 | Open and share the lab link | 5 | 3 | Slides 1 to 2 |
| 1 | Where we are: one day of production traffic | 7 | 4 | Slides to `w10-lab-0`; challenge 01 Setup done together |
| 2 | Online evals: signals, evaluators, filters, sampling | 10 | 5 | Slides; 2-minute look at **+ Evaluator** |
| 3 | Lab: catch the wrong return window | 20 | 12 | S1 §1 to §4 (challenge 02) |
| 4 | Alerts, automations and queues | 8 | 4 | Slides; UI demo of the alert preview |
| 5 | Lab: alert line and routing | 12 | 4 | S1 §5 to §6 |
| 6 | Insights | 7 | 4 | Slides; prepared report |
| 7 | Lab: check the report against the traces | 9 | 3 | S2 (challenge 03, first half) |
| 8 | Engine | 9 | 4 | Slides; prepared issue |
| 9 | Lab: triage and assertions | 10 | 3 | S3 (challenge 03, second half) |
| 10 | Governance: three controls, the Gateway, policies | 9 | 5 | Slides; policy demo if available |
| 11 | Lab: mask the trace, read a block | 9 | 4 | S4 (challenge 04) |
| 12 | Wrap-up and what's next | 5 | 5 | Slides `w10-prevent-map`, `w10-recap` |
| | **Total** | **120** | **60** | |

Sums: 5+7+10+20+8+12+7+9+9+10+9+9+5 = 120 and 3+4+5+12+4+4+4+3+4+3+5+4+5 = 60. Hands-on time: 60 of 120 minutes, 26 of 60.

What "60 minutes" means for each lab block:

- Block 3: challenge 02 in full (the evaluator). The filter and sampling cell is shown by the presenter.
- Block 5: follow-along. Learners run the two local cells (threshold, routing count); UI steps are a demo.
- Blocks 7 and 9: follow-along with `uv run python workshop_modules/module_7/exercises/show_report.py` (or S2 cells 4 to 10 and S3 cells 6 to 7). In Instruqt they then click **Skip** on challenge 03, whose solve script completes it. They are not asked to write the functions.
- Block 11: the masking exercise only. Challenge 04's check covers masking only, so a 60-minute attendee can pass it.

Notes that follow from product limits: an Insights report and an Engine scan are never waited for (up to 30 and up to 20 minutes, notes 04 and 05). On a Workshop Studio delivery, where attendees administer their own organization, they may start Engine on their seeded project in block 1 and read its board in block 9 (gap-4 §1.1 finding 3); nothing in the plan depends on it, and Engine on generated traces has no precedent (gap-1 "Unverified" item 3).

### 12.3 Requirements per block (for the "choose blocks and path a week before" checklist item)

| Block | Works with no key | Adds with a key (any plan) | Needs more |
|---|---|---|---|
| 3 | Everything checked | Upload, scores, attach in the UI, 4 live traces | An LLM judge needs a provider key stored in the workspace |
| 5 | Threshold and routing count | Queue with 11 items; automation; alert form | A real firing needs fresh errors and an unpublished evaluation delay |
| 7 | Saved report | Nothing | A live report: Plus or Enterprise, a workspace provider key, up to 30 minutes |
| 9 | Saved board | Nothing | A live board: Engine enabled by an Organization Admin; Workshop Studio attendees can start it themselves |
| 11 | Everything checked | Optional masked upload | A live Gateway call: a workspace-scoped key with `gateway:invoke` and a pre-made policy (gap-4 rows 16 to 18) |

## 13. Slide deck outline

Location: `PROJECT/decks/workshop-10-monitoring/`, same layout as `PROJECT/decks/lcae-master/`: `AUTHORING.md` (a copy of the master guide plus a Workshop 10 addendum), `project/deck.css` (copied unchanged), `project/deck.json`, `project/slides/<id>.html`, three order files (`order-monday.txt`, `order-core.txt`, `order-extended.txt`), `assets.txt`, and `tools/lint_slides.py`.

Rules, from `PROJECT/decks/lcae-master/AUTHORING.md`: one file per slide with one `<section>`; 1920×1080; title a statement of 50 characters or fewer (every title below was counted; the longest is 50); about 70 visible words; tables of at most 6 rows including the header; speaker notes in `<aside>`, at most 1,500 characters; no new CSS classes; pictures as `ASSET:<deck folder>/<file>`; no question as a title; teaching first, no exam framing. Additions for this deck: footer tag `Monitoring, Governance & Self-Improvement`; reused slides are copied, never edited in the master deck; a copied slide's `src="/_blob/…"` is switched back to its `ASSET:` path from `asset-map.tsv` (note 08 §1.2); rule P9 on UI labels; each lab slide has a "Check yourself" card with the numbers of section 6.6.

"Source": **as is** = copy of the named master-deck slide, footer changed; **rework** = that slide with the stated change; **new** = written from the named note. Kinds: D divider, C content, P picture, L lab, Q check-your-understanding.

### 13.1 Core deck (37 slides; `order-core.txt`). `order-monday.txt` is the same without the six L slides (31 slides)

| # | Id | Title (the takeaway) | Kind | Source |
|---|---|---|---|---|
| 1 | `w10-title` | Monitor, Govern, Improve | D | New. Lead line from the catalog: "Understand, control, and continuously improve agents in production." |
| 2 | `w10-agenda` | Four topics, one agent, one day of traffic | C (table) | New |
| 3 | `w10-where` | TechHub is deployed; now it has to be watched | P | New slide around `Workshop Nov 2026 - media/image113.png` (no customer content, note 08 §2.1) |
| 4 | `w10-five-questions` | Five questions, five kinds of tooling | C (table, 6 rows) | Rework of `m-three-questions`: adds "Who fixes it?" (Engine) and "Who may spend what?" (LLM Gateway) |
| 5 | `w10-incidents` | One day of traffic hides five problems | C (table, 6 rows) | New, from section 6.3: problem, the signal that moves, the tool |
| 6 | `w10-lab-0` | Open the lab and meet the production day | L | New. Check yourself: 200 conversations, 260 traces |
| 7 | `w10-sec-online` | Online Evals | D | Rework of `sec-quality` |
| 8 | `m-online-evals` | Online evals score live traces as they arrive | P | As is; `Workshop_ Agent Evals - media/image43.png` |
| 9 | `t-online-setup` | An online evaluator scores one trace or a thread | C (table) | As is |
| 10 | `w10-three-signals` | Errors and thumbs miss a confident wrong answer | C (table) | New, from S1 §2: signal, finds, misses |
| 11 | `w10-code-evaluator` | A code evaluator is one function of a run | C (code, 6 lines) | New; note 03 §2.3 |
| 12 | `w10-filter-sample` | Filter first, then sample what is left | C (three cards: filter, sampling rate, spend limit) | New; note 03 §2.5; numbers 260, 104 and 65 from S1 §4 |
| 13 | `w10-lab-1` | Catch the wrong return window | L | New. Check yourself: naive 23, correct 11 |
| 14 | `w10-alert-anatomy` | An alert is a metric, a threshold and a window | C | Rework of `alert-anatomy`: metric names Run Count, Cost, Errors, Feedback Score, Latency; window 5 or 15 minutes (note 03 §11; note 08 conflict C3) |
| 15 | `threshold` | Set the line above normal and below the spike | C (line drawing) | As is |
| 16 | `w10-automations` | Automations act on the scores for you | C | Rework of `m-automations`: adds the item type (runs or threads) and applying a rule to past runs (note 03 §3) |
| 17 | `m-annotation-queue` | An annotation queue turns a flag into a test case | C (flow) | As is |
| 18 | `w10-lab-2` | Set the alert line and route the failures | L | New. Check yourself: threshold 3; 11 items |
| 19 | `w10-sec-insights` | Insights | D | New |
| 20 | `w10-evals-vs-insights` | Evals for defined questions, Insights to discover | C | Rework of `evals-vs-insights`: same content, the title rewritten as a statement because the guide forbids questions in titles |
| 21 | `w10-insights` | Insights summarizes, clusters and reports | C | Rework of `insights`: three guided topics, not two; notes add "Plus and Enterprise" and "needs a model configured for Insights" (note 04 §3, §4.1) |
| 22 | `w10-silent` | Silent failures show a 0% error rate | C (table, 5 rows) | New: four subcategories of the sample report with conversations and error rate |
| 23 | `w10-lab-3` | Check the report against the traces | L | New. Check yourself: 27 conversations, error rate 0, 11 flagged |
| 24 | `w10-sec-engine` | Engine | D | New |
| 25 | `t-engine` | Engine turns failing traces into eval examples | P | As is; `Workshop Nov 2026 - media/image123.png`; talk track from `Workshop Nov 2026.txt` slides 110 to 114 with no customer or staff names (note 08 §2.4) |
| 26 | `w10-engine-issue` | An issue is a diagnosis, evidence and a fix | C (three cards) | New; note 05 §4 |
| 27 | `w10-engine-limits` | Engine proposes; your review and CI decide | C (three cards: never merges; first scan up to 20 minutes; metered in LSUs) | New; note 05 key findings 4, 5, 7 |
| 28 | `w10-lab-4` | Triage three issues and pick the assertions | L | New. Check yourself: the three next actions |
| 29 | `w10-sec-govern` | Govern | D | New; notes use the governance motivation of `Workshop Nov 2026.txt` slide 17, rewritten (note 06 §7) |
| 30 | `w10-three-controls` | Three controls protect three different places | C (table) | New; note 06 §4.5 |
| 31 | `w10-gateway-what` | The Gateway sits between agents and providers | C (flow) | New; replaces the single card on `d-runtime-env`; note 06 §1.1 |
| 32 | `w10-policies` | A policy block is a status code and a name | C (table, 5 rows) | New; note 06 §2.1 |
| 33 | `w10-masking` | Mask traces in the client, before upload | C (code, 5 lines) | New; note 06 §4.1 |
| 34 | `w10-custom-apps` | Custom Apps run inside LangSmith as the viewer | C | New; note 06 §5 |
| 35 | `w10-lab-5` | Keep an email out of stored traces | L | New. Check yourself: more than 0, then 0 |
| 36 | `w10-prevent-map` | Each incident has one control that fits | C (table, 6 rows) | New; S4 §6 |
| 37 | `w10-recap` | Five things to remember | C | Rework of `recap` |

### 13.2 Extension slides (27; shown in `order-extended.txt`, 64 slides in total)

| Id | Title | Kind | Source | After |
|---|---|---|---|---|
| `t-loop` | Online finds the issue, offline proves the fix | C | As is | `w10-where` |
| `m-eval-checks` | What online evaluators commonly check | P | As is; `Workshop_ Agent Evals - media/image51.png` | `t-online-setup` |
| `t-thread-catalog` | Some questions need the whole conversation | P | As is; `Workshop_ Agent Evals - media/image50.png` | `m-eval-checks` |
| `w10-eval-kinds` | Pick the cheapest evaluator that can decide | C (table) | New; note 03 §2.1 to §2.4 | `t-thread-catalog` |
| `w10-thread-limits` | Thread evaluators wait until a thread goes idle | C (table) | New; note 03 §2.2. Teaches two thread keys (note 03 key finding 10) | `w10-eval-kinds` |
| `w10-q-sampling` | (question: what a quiet alert at a 10% sample proves) | Q | New, newly written | `w10-lab-1` |
| `ab-test` | Tag runs with a version, then group by it | C | As is | `w10-q-sampling` |
| `m-dashboards` | Dashboards answer “is it healthy” at a glance | C | As is | `ab-test` |
| `w10-alert-test` | A green test alert is not proof of delivery | C (two cards) | New; note 03 §11 | `threshold` |
| `m-flywheel` | Production failures become tomorrow’s tests | P | As is; `Workshop_ Building Agents with LangChain and LangGraph - media/image58.png` | `m-annotation-queue` |
| `q-m09` | (question: an alert threshold) | Q | As is | `w10-lab-2` |
| `w10-insights-report` | Read a report from the summary down to traces | C (three cards) | New; note 04 §8 | `w10-insights` |
| `w10-insights-facts` | Bring a finished report; do not wait for one | C (table) | New; note 04 §3, §10 | `w10-insights-report` |
| `q-m07` | (question: online evaluator or Insights) | Q | As is | `w10-lab-3` |
| `w10-engine-setup` | Engine needs traces and an admin, not a repo | C (table) | New; note 05 §2 | `w10-engine-issue` |
| `w10-engine-signals` | Engine reads errors, behaviour and feedback | C | New; note 05 §4. Notes carry the line "the evaluator from block 3 is its input" | `w10-engine-setup` |
| `d-context-hub` | Context Hub versions prompts, skills and memory | C | As is | `w10-engine-limits` |
| `w10-q-engine` | (question: which signal finds a failure with no error) | Q | New | `w10-lab-4` |
| `w10-under-hood` | PII redaction and fallbacks live inside the agent | P | New; `Workshop Nov 2026 - media/image118.png` (not in `asset-map.tsv` yet; no customer content, note 08 §2.2) | `w10-sec-govern` |
| `w10-gateway-routes` | Three ways to route a model call through it | C (table) | New; note 06 §1.2 | `w10-gateway-what` |
| `w10-spend-lag` | A spend cap blocks the next request, not this one | C | New; note 06 §2.2 | `w10-policies` |
| `w10-audit` | Traces record calls; the audit log records changes | C (table) | New; note 06 §3 | `w10-masking` |
| `d-auth-layers` | Production auth runs in three directions | P | As is; `Workshop Nov 2026 - media/image132.png` | `w10-audit` |
| `w10-q-controls` | (question: which control keeps an email out of stored traces) | Q | New | `w10-lab-5` |
| `w10-fit-together` | How the pieces fit together | C (table, 6 rows) | Rework of `m-fit-together`: adds Engine and Gateway rows and merges alerts into the dashboards row to stay at six rows | `w10-prevent-map` |
| `w10-find-it-1`, `w10-find-it-2` | Where to look in LangSmith: monitoring; Where to look in LangSmith: improve and govern | C (two tables, 6 rows each) | Rework of `find-it`, split in two because the master slide already has six rows; says "project or agent environment" | `w10-fit-together` |

Pictures: 8, all from existing decks (limit 16): `image113`, `image43`, `image123` in the core; `image51`, `image50`, `image58`, `image118`, `image132` in the extension. No picture exists for the Gateway, Insights, alerts, masking or Custom Apps (note 08 key finding 2); those slides are tables, cards, flows and code. Not used: the lifecycle ring (blank background pictures), the picture with a logo, the picture with the undefined term "Sleep-time Review", any picture or note tied to a customer or a named person, and the master slides `threads` and `q-m01` (three thread keys where the docs list two).

## 14. Instruqt track outline

### 14.1 Shape

**Coding Agent style, built from the team's Claude Code template** (`template-claude-code/` in the private track repo, readable locally since note 10), as the owner asked: one **VS Code** tab (code-server on port 8080) with the Claude Code panel open and a terminal in the project folder; the learner directs Claude Code to fill in one or two functions per challenge; **Check** tests the outcome. The template's rule is that a check tests the outcome, not a diff, and calls no model (note 10); every exercise here already has a model-free checker. The module calls no model of its own, so the sandbox's Bedrock quota goes to Claude Code only; the template's own log still lists quota for about 30 concurrent sessions as an open question, so throttling is reduced, not removed.

The team rule is "Build ONLY when no existing track fits" (note 07 key finding 4). The existing Modular 5 and Modular 3 tracks teach Engine and the Gateway data policy on a research agent and need a deployment, a connected GitHub repository and extra keys (gap-1, Answer items 1 and 6). No existing track covers sampling and filters, alerts, Insights or trace masking, or TechHub. The owner should tell the Modular track owners.

The track is authored under `PROJECT/module-7-build/instruqt/adlc-monitoring-governance/` and is not pushed. First version: **four challenges**. The alert-and-routing challenge is added only after a browser dry run shows time and Bedrock headroom.

| Setting | Value | Basis |
|---|---|---|
| `slug` | `adlc-monitoring-governance`. Decide once: changing a slug makes a push create a second track | Template log (note 10) |
| `title` | `[ADLC] Monitoring, Governance & Self-Improvement (Coding Agent)`, prefixed with the builder's initials until shared | note 07 §2.3 |
| `owner`, `tags` | `langchain`; `coding-agent`, `claude-code`; `adlc-workshop-series` once shared | Template `track.yml`; note 07 §2.3 |
| `id`, `checksum`, challenge and tab `id` | Omitted. Instruqt assigns them on first push; a new track must not copy the template's | note 10 |
| `timelimit`, `idle_timeout` | 7200 and 3600, as the existing Coding Agent track (120 minutes, brief). Time in a LangSmith window does not reset the idle timer (note 07 §3.2) | Brief |
| `skipping_enabled` | `true`; every challenge has a solve script and no solve assumes an earlier challenge ran | Template |
| Layout | `default_layout: AssignmentLeft`, `default_layout_sidebar_size: 25`, theme `modern-dark` | Template |
| `config.yml` | Unchanged from the template: one virtual machine `workstation` (Ubuntu 24.04, 8 GB, 2 CPUs), the `bedrock` AWS account with four US regions, the environment pins. No `secrets:`, no external ingress | Template `config.yml` |
| Tab (every challenge) | One tab `VS Code`, `type: service`, `hostname: workstation`, `port: 8080`, `path: /?folder=/root/workshop` | Template |

### 14.2 Challenges

Assignments are short and do not restate what a file's docstring says (the retro's "redundant instructions" finding, note 07 §2.7). Each has the template's four parts: the goal in two sentences, "Ask for the change" with an example prompt, "Run it", "Check". Check scripts follow the house shape (`_fail` wrapper, no strict shell flags, `timeout --kill-after=3 50`). No check calls a model or LangSmith. Steps in LangSmith are a marked "If you have a key" section with an **Open LangSmith** button, because rendering LangSmith inside an Instruqt tab is UNVERIFIED (note 07 §3.5), and they are not gated.

| # | Folder and title | Teaser | What the learner does | Check passes when | Solve |
|---|---|---|---|---|---|
| 01 | `01-setup` · Setup | Meet one day of TechHub production traffic. | Done together. Runs `uv run python scripts/module7_connect_langsmith.py` (paste a key at the masked prompt, or `--skip`), then asks Claude Code: "Print the trace t-0042 as a tree and tell me how many conversations and traces the seed has." With a key the script also uploads the seed and prints the navigation sentence | The state file says `seed_verified: true` and `langsmith` is `verified` or `skipped`; the seed file's SHA-256 matches. A key is never required | Runs the script with `--skip` |
| 02 | `02-catch-the-silent-failure` · Catch the Silent Failure | Release 1.5.0 gives the wrong return window. Write the evaluator that finds every case. | Directs Claude Code to implement `perform_eval(run, example=None)` in `workshop_modules/module_7/exercises/return_window_evaluator.py`; runs `exercises/check.py s1_evaluator`. With a key: pastes it into a Code Evaluator in LangSmith (the steps of S1 §3.1) | The function, extracted with `ast` as in the template, gives the right boolean on the public cases, and the set of root runs it flags in the seed matches the answer hash. Messages name the failing case: "it also flags a correct answer about an unopened item", "define it as perform_eval(run, example=None)", "flags N of 260, expected 11" | Copies the solution |
| 03 | `03-read-the-report-and-the-issues` · Read the Report and the Issues | A report and an issue board say where the agent struggles. Prove one claim and decide what to do next. | In `exercises/read_the_report.py`: `summarise(report)` and `flagged_in_subcategory(name, seed, labels, perform_eval)`. In `exercises/triage.py`: `next_action(issue)`. 60-minute deliveries: run `exercises/show_report.py`, read, click **Skip** | `summarise` returns the largest category and the highest-error subcategory; `flagged_in_subcategory("Return window questions", …)` returns 11; `next_action` is right on the three issues and two extra cases | Copies the solutions |
| 04 | `04-keep-pii-out-of-traces` · Keep PII Out of Traces | Add trace masking, then prove with a local capture that no email leaves the sandbox. | Runs `uv run python workshop_modules/module_7/exercises/check.py s4_masking` and sees that payloads contain the email; directs Claude Code to implement `build_anonymizer()` in `exercises/masking.py`; re-runs until it passes. Then reads the three saved Gateway responses with Claude Code (not gated) | The capture run with the learner's `build_anonymizer()` uploads 0 payloads that contain the email, and a control string without PII is uploaded unchanged, so "hide everything" does not pass | Copies the solution |

Also in the track folder, as the team skill requires: `MEMORY.md` (seeded with this design's decisions and every runtime-verify item), `README.md` from the skill's template, `assets/langchain-icon.png` copied from the template. Notes: one consolidated card per challenge.

### 14.3 What the sandbox provides, and what the setup script changes

Starting from the template's `track_scripts/setup-workstation` (bootstrap wait, retried non-fatal `apt-get update`, `uv` on `/usr/local/bin`, AWS credentials in `~/.aws`, Claude Code settings in user scope, the code-server unit, the Bedrock warm-up), the changes are:

1. Replace the weather-agent project with a clone of the public ADLC repo at a **pinned commit** into `/root/workshop`, then `uv sync --frozen`. (The "no `uv sync`" rule of this build applies to the build machine, not to the sandbox.) Each step prints its elapsed seconds, as the template does, so the first play shows what the clone and sync add to start-up.
2. Do not build the vector store and do not install `langchain-aws`: the lab calls no model.
3. Write `/root/workshop/.env` with the LangSmith lines commented out, so a learner who skips the key lands in the quiet keyless state (gap-3 §1.4).
4. Run `scripts/module7_seed.py verify`; fail the track setup if the seed does not verify.
5. **Answer key.** Copy `workshop_modules/module_7/exercises/solutions/` to `/opt/m7-solutions/` for the solve scripts, then delete `solutions/` and `data/answers.json` from `/root/workshop`. The checker then compares with `data/answer_hashes.json` and still gives diagnostic messages from its public cases.
6. **Claude Code permissions.** Keep `defaultMode: acceptEdits` and the template's allow and deny lists, and add to `deny`: `Read(//root/workshop/.env)`, `Read(//opt/m7-solutions/**)`, `Read(//root/workshop/evaluators/online_evaluators.py)`. The template's log says a `Read()` deny does not stop `grep -r` or a script that opens the file, so this is a nudge, not a guarantee; the checks test outcomes either way.
7. Append to `/root/workshop/CLAUDE.md`: "The exercises are in `workshop_modules/module_7/exercises/`. Do not edit `utils/` or `data/`. Do not read `evaluators/online_evaluators.py`: writing that function is the exercise. Run checks with `uv run python workshop_modules/module_7/exercises/check.py <id>`."
8. Change the start-up extension to open `workshop_modules/module_7/exercises/return_window_evaluator.py`.

`scripts/module7_connect_langsmith.py` (in the ADLC repo) reads the key with `getpass` so it never appears on screen or in Claude Code's context, probes the US and EU API endpoints with it (the retro lists "regional langsmith endpoints" as a known failure, note 07 §2.7) and otherwise asks for the endpoint URL, writes `LANGSMITH_API_KEY`, `LANGSMITH_ENDPOINT` and `LANGSMITH_TRACING=true` to `.env`, uploads the seed, prints the navigation sentence, and records `verified` or `skipped` in `.m7_state.json`. `--skip` records that the learner continues without a key.

The sandbox needs no LangSmith workspace, no secrets, no external ingress, no Docker and no GitHub account.

### 14.4 What must be reconciled with the private template before the first push

1. **Location and process.** Move the folder into the track repository as a sibling of `template-claude-code/` on a new local branch, through the team skill `instruqt-track-builder-reference`: its build plan and audit are approval gates that need the owner, and the repository's own `CLAUDE.md` (absent in the local clone) is the primary authority if it exists by then.
2. **Platform-assigned values**: track, challenge and tab ids and the checksum exist only after the first push.
3. **A different file per challenge.** The template has one challenge and a start-up extension that opens one fixed file. How the multi-challenge Coding Agent tracks open a file per challenge is unknown: `test-edd-claude-code` and `adlc-managed-deep-agents` are not in the local clone (note 10). Until someone pulls one of them, each assignment names its file and the extension opens the first.
4. **The key-entry flow.** Those two tracks hold the team's wiring for "a LangSmith API key is optional". `scripts/module7_connect_langsmith.py` is this design's sketch; it should be diffed against theirs.
5. **Repo and `.env` paths**: `/root/workshop` in the template, `/opt/workshop` in one existing track (gap-6 §2.6).
6. **The pinned commit** needs the module pushed to a ref the sandbox can reach. This work may not commit or push.
7. **Anything that needs a push or a play**: `instruqt track validate`, `instruqt track test`, a browser play with Claude Code on the pinned Bedrock model, time per challenge, start-up time with the clone and sync, a room-sized Bedrock load, whether the organization's usage-limit banner blocks plays. A passing `track test` does not prove the browser experience (template log).
8. **Whether code-server renders notebooks.** The track does not depend on notebooks.

## 15. Notion catalog page content

Nothing is written to Notion by this work. The text is drafted in `PROJECT/module-7-build/notion/` in the format of the finished pages (note 07 §1) for the owner to paste.

**The example:** The TechHub support agent from Workshops 7 to 9, the morning after a release. Learners work on one seeded day of production traffic with five planted problems: they catch a silent wrong answer, set an alert, read a report, triage an issue board and mask a trace.

**Customer prereqs:** None required. A **LangSmith API key** per attendee is recommended: without one the labs still run, but traces print in the notebook instead of linking to LangSmith. The labs need no model key. (The open "TODO: confirm whether this has a lab" is removed: it has one.)

**Online evals: score production runs and threads in real time**
- **What's covered:**
  1. Three signals and what each misses: errors, user feedback, reading traces (S1).
  2. A code online evaluator, `perform_eval(run, example=None)`: it flags the 11 wrong return-window answers that a naive check over-flags as 23; with a key, attached in LangSmith with a filter and a sampling rate (S1).
  3. A filter against a sampling rate: runs scored and failures caught (S1).
  4. An error alert threshold from 5-minute windows; a rule that routes 11 flagged runs to an annotation queue (S1).
  5. LLM-as-judge and thread evaluators, idle time, backfill and the evaluator spend limit (deck, demo).
- **Docs:** Online code evaluators (`https://docs.langchain.com/langsmith/online-evaluations-code`) · Automation rules (`…/langsmith/rules`) · Alerts (`…/langsmith/alerts`)

**Insights: surface patterns across traces automatically**
- **What's covered:**
  1. Summarize, cluster, report; a defined question against open-ended discovery (deck).
  2. Reading a report object top down: key points, categories, subcategories, highlighted traces (S2).
  3. The largest category, the highest error rate, and the two silent failures that show 0% errors; one claim checked against the traces with the S1 evaluator (S2).
  4. What each finding should become: alert, evaluator, queue or Engine issue (S2).
  5. Generating a report: plan, model configuration, up to 30 minutes (deck, demo of a prepared report).
- **Docs:** Insights (`…/langsmith/insights`) · Annotation queues (`…/langsmith/annotation-queues`)

**Engine: turn production traces into fixes**
- **What's covered:**
  1. The loop: detect, diagnose, propose a fix, track with examples, reopen (deck).
  2. Reading an issue board from code with `client.list_project_issues(...)` or the saved sample: severity, status, type, evidence, proposed fix (S3).
  3. Triage of three issues, and the `search_policy_docs` call the agent skipped (S3).
  4. Evidence into a test case: choosing assertions for an offline example (S3).
  5. Setup, **Open PR**, regression and cost; Engine never merges (deck, demo of a prepared issue).
- **Docs:** Engine (`…/langsmith/engine`) · Set up Engine (`…/langsmith/engine-setup`) · Engine issues (`…/langsmith/engine-issues`)

**LLM Gateway and governance: one endpoint across model providers**
- **What's covered:**
  1. Three controls compared: `PIIMiddleware`, a Gateway data policy and client-side trace masking; `Client(anonymizer=create_anonymizer([...]))` takes raw-email payloads to 0 (S4).
  2. Which route a model call takes: `LANGSMITH_GATEWAY=true`, the standard endpoint, the `langsmith:` provider (S4).
  3. What a spend, rate-limit and model-access block returns (`402`, `429`, `403`), what LangChain raises and what the agent retries (S4).
  4. Creating policies, PII redaction, the `gateway` traces and the audit log (deck, demo).
  5. Custom Apps (deck).
- **Docs:** LLM Gateway (`…/langsmith/llm-gateway`) · Spend policies (`…/langsmith/llm-gateway-spend-policies`) · Mask inputs and outputs (`…/langsmith/mask-inputs-outputs`)

The "Also in the deck" line disappears, as on finished pages: its three items are numbered items above.

**Materials rows**: Slides: TODO, a Google Slides link with the deck title as text (the source is HTML; the owner decides how it is published). Code: `workshop_modules/module_7` on `main` (valid once the branch is merged). Hands-on lab: `Instruqt: adlc-monitoring-governance` once pushed; until then "**Temporary:** no track yet. Present from the repo notebooks; they need no keys." How to run Instruqt and LangSmith org for attendees: unchanged. Demo environment: the team's demo workspace for online evals, alerts and queues on its simulated supervisor-agent traffic, with a TODO for the owner to confirm whether Insights, Engine and Gateway policies can be shown there; until confirmed those three are shown from slides and the saved files. Further reading: the loop-engineering blog post.

**Prep checklist additions.** A week before: "Choose the blocks and the provisioning path (talk track table)". Day before: "Open the prepared Insights report and Engine issue; click through the evaluator, automation and alert forms once and correct any label in your notes." The standard sentence "The labs run without one." stays true.

**Talk track** (reference format of note 07 §1.8; gray time line; 1 to 3 beats per block). Intro sentence: "The section times are estimates from the notebooks: 120-min version, with the 60-min version in brackets."

| Block | Time line | Beats |
|---|---|---|
| `### 0 · Open and share the lab link` | `5 min (3)` | Say what they'll leave with: a way to catch, route and fix what production shows, and to govern what the agent may spend and store. Drop the Instruqt link now so sandboxes warm up while you talk |
| `### 1 · Where we are: one day of production traffic` | `7 min (4)` | TechHub is deployed; version 1.5.0 shipped last night. Five questions, five tools; five problems hide in the day. Walk through `01 - setup` together |
| `### 2 · Online evals` | `10 min (5)` | Errors and thumbs miss a confident wrong answer. A code evaluator is one function of a run. Filter first, then sample |
| `### 3 · Lab: catch the wrong return window` | `Lab S1 · 20 min (12)` | The naive check flags 23; the target is 11. Let them find out why. With a key, attach it and send four fresh traces. A 25% sample catches 3; the version filter catches all 11 |
| `### 4 · Alerts, automations and queues` | `8 min (4)` | Set the line above normal and below the spike. A green test alert is not proof of delivery. A rule is an item type, a filter, a sampling rate and an action |
| `### 5 · Lab: alert line and routing` | `Lab S1 · 12 min (4)` | Background errors never reach 3 in five minutes; the burst has 8 in three. The routing filter selects 11 runs; correct one into a dataset example |
| `### 6 · Insights` | `7 min (4)` | A defined question is an evaluator; discovery is Insights. Open the prepared report; never generate one live |
| `### 7 · Lab: check the report against the traces` | `Lab S2 · 9 min (3)` | The loud incident has the highest error rate; the two silent ones show 0%. 11 of 27: the report's claim holds |
| `### 8 · Engine` | `9 min (4)` | Issue, evidence, proposed fix, examples, regression; Engine never merges. Point at **Feedback cited by Engine**: the evaluator from block 3 is its input. Check that Engine is enabled before promising it |
| `### 9 · Lab: triage and assertions` | `Lab S3 · 10 min (3)` | Three issues, three different next actions. Two assertions separate the wrong answer from the corrected one |
| `### 10 · Governance` | `9 min (5)` | Three controls, three places. A policy block is a status code and a policy name; a spend cap blocks the next request. Traces record calls; the audit log records changes |
| `### 11 · Lab: mask the trace, read a block` | `Lab S4 · 9 min (4)` | With the middleware alone the email still reaches stored traces; the anonymizer takes it to zero. In the 120-min run, also map the three blocks |
| `### 12 · Wrap-up and what's next` | `5 min (5)` | Each incident has one control that fits. This is the end of "Road to production"; point to the Academy Engine course and the docs |

Sums: 120 and 60 (section 12.2).

`### Fallback if the lab breaks`: Present from the repo notebooks locally (they need no keys and no model) and share the repo link so attendees can follow along later.

`### Audience pivots`
- **Platform or security team:** spend more on blocks 10 and 11; shorten block 6. Show the audit log if the demo organization is Enterprise.
- **No LangSmith keys in the room:** stay on the notebooks' local path; run the UI parts of blocks 3 and 5 as demos in your own workspace.
- **Attendees are admins of their own new organization (Workshop Studio):** have them start Engine on the seeded project in block 1 and read its board in block 9 instead of the saved one.

## 16. Deviations from the repo's conventions

| # | Deviation | Why |
|---|---|---|
| D1 | No model call in any notebook on the default path | P1: the module must run for every attendee and be verifiable offline. Modules 4 to 6 call a model in their first agent cell |
| D2 | A `data/` subfolder and an `exercises/` folder inside `workshop_modules/module_7/` | Earlier modules keep one or two data files beside the notebooks (note 01 §8). Module 7 has nine data files and four exercise stubs that the Coding Agent track edits |
| D3 | A shared checker, `check(exercise_id, obj)`, called from notebook cells | One source of truth for notebooks, tests and Instruqt. In the notebooks it is used with the house "✅ Verified" print line and the drift-guard `assert` device (note 01 §3.8), not as a new exercise heading |
| D4 | The Setup cell calls `setup_langsmith()`, not `project_url()` | `project_url()` raises without a key (gap-3 answer 1). The builders of Modules 4 to 6 are not switched in this work |
| D5 | `evaluators/online_evaluators.py` defines a function named `perform_eval` | The documented contract name for code evaluators; the package exports it as `wrong_return_window_evaluator` |
| D6 | Notebooks write nothing into the repo tree | Examples are printed; no `data/out/` folder |

## 17. Decisions

### 17.1 Decision table

| Decision | Choice | Status |
|---|---|---|
| Module number, folder, name | Module 7, `workshop_modules/module_7/`, "Monitoring, Governance & Self-Improvement" | Proposed; owner confirms |
| Notebooks | Four, one per catalog topic; no bonus notebook | Proposed |
| Build method | `scripts/notebook_builders/build_module7.py` | Proposed |
| Agent and tools | Module 4 deep agent, default tools (`get_order_status` and so on), the captured configuration | Decided by the evidence (gap-2) |
| Units of the sample report | Conversations (200), not traces | Decided by the evidence (note 04 §2) |
| Seed | 200 conversations, 260 traces, 20 hours, five incidents, generated | Proposed |
| Keyed path | Deterministic SDK writes for history; UI objects for new traffic (P3) | Proposed |
| `generate_insights` | Never called from a notebook | Proposed |
| Monday 2026-11-23 | Slides plus demo; notebooks are a stretch | Proposed; owner and presenter confirm |
| Instruqt | Coding Agent style, four challenges first | Proposed |
| Deck | `PROJECT/decks/workshop-10-monitoring/`, footer tag "Monitoring, Governance & Self-Improvement" | Proposed |

### 17.2 Where the judges disagreed, and what was decided

| Point | Positions | Decision and reason |
|---|---|---|
| Base proposal | Two judges: A (deliverability; teaching). One judge: C (fit to conventions) | A's lab design as the base; C's conventions grafted onto it: function-named `utils` files, the exact Setup cell, the evaluator under `evaluators/` with its source exported, slide discipline, 7200-second limit, the Monday plan |
| Fixtures against seed | One judge: keep C's seed equal to the unchanged validated fixtures. Two judges: regenerate the fixtures from the seed | Regenerate from the seed and re-validate. The unchanged fixtures count traces, contradict any seed in three sentences, and name a tool whose trace shape was never captured |
| Order tool name | C used `query_my_orders` to match the fixture; a judge noted its trace shape is not verified | `get_order_status`, the captured tool. The real tool also returns `Order <id> not found.` for a lower-case id, which makes incident C true to the code |
| Alert seed | One judge: A's seed has a unique answer. One judge: B's shape is robust to window alignment but has five right answers | A new shape with both properties: background errors reach at most 2 in any 5-minute window, the burst has 8 inside 3 minutes (so at least 4 in one window however windows are aligned), and the question asks for the smallest threshold the background cannot reach: 3 |
| Engine coding task | One judge: A's `return_window_guard` repeats Section 1 and should become "repair the planted instruction". One judge: keep the guard | Neither. A prompt repair cannot be checked by outcome without a model, and the guard duplicates the evaluator. The graded Engine tasks are reading the evidence, a triage rule with one answer per issue, and choosing two of six assertions; the proposed fix and its proof (the existing Harbor task) are shown as text |
| Worked answers | One judge: C's collapsed `<details>` block. One judge: `<details>` is not a house form | The worked answer is the output of the next code cell. Committed notebooks carry no outputs, so it is hidden until the learner runs the cell |
| PII plant | One judge: plant one, where it really lands. One judge: plant none in replies | One synthetic email in the root inputs of one turn, the measured normal case. No card number, nothing in a reply or a `task` argument |
| Shared checker | One judge: the best feature of A. One judge: a pattern the repo lacks | Kept, recorded as deviation D3 |
| Answer key in the sandbox | A: deny rules. B: delete the key and compare hashes | Both: hashes for equality, public cases for diagnostic messages, deny rules as a nudge |
| Topic metadata on runs | B and C upload a `topic` key; a judge said it undercuts Insights | Not uploaded (P6) |
| Track time limit | A and B 9000 seconds; C 7200 | 7200, as the existing Coding Agent track |

## 18. Existing assets (verified 2026-11-19)

- `agents/deep_support_agent.py`: `create_deep_support_agent(...)`, `_pii_middleware()` (email redact, credit card mask). `agents/middleware/fault_tolerance.py`: `_TRANSIENT_STATUSES = {408, 409, 429}`.
- `tools/database.py`: `get_order_status` returns `Order <id> not found.` for an unknown id. `data/structured/techhub.db`: 50 customers, `CUST-003` owns `ORD-2025-0050`, `CUST-010` is Corporate. `data/documents/policies/return_policy.md` lines 7 to 13.
- `utils/langsmith_links.py`: `project_url`, `trace_url`, `trace_link` (raise or print an error without a key, gap-3 §1.5).
- `evaluators/__init__.py` exports five evaluators; `evaluators/README.md` lists them.
- `images/online_eval_process.png`, `images/data_flywheel.png`.
- `managed_agent/evals/opened-item-return-window/`: the Harbor task for the same behaviour.
- `tests/`: six files, 28 tests, `unittest`, pass in a stripped environment.
- `PROJECT/module-7-build/research/09-gap-3-fixtures/`: the two validated fixtures, `validate_fixtures.py`, `netguard.py`, `prototype_langsmith_links.py`. `research/09-gap-2-spike/lite_trace_sketch.py` and `09-gap-2-trace-template.json`.
- `PROJECT/decks/lcae-master/`: 266 slides; every reused id in section 13 exists; `m-three-questions` has 4 table rows, `m-fit-together` and `find-it` have 6, `m-automations` has 4. The eight picture files exist under `PROJECT/workshops/slides/`; `image118.png` is not in `asset-map.tsv`.
- The Claude Code template track and the team skill, in the local clone of the private track repo (note 10).
- Installed: langsmith 0.14.12, langchain 1.4.7, langgraph 1.2.17, deepagents 0.7.32, nbclient 0.10.4, nbconvert 7.17.1; `jupyter-execute` present.

## 19. Tasks

Ids refer to `PROJECT/module-7-build/plan.md`, which has the paths, dependencies and checks. Check each item off here as it lands.

**By Monday 2026-11-23 (the deck)**
- [ ] **M1** Deck scaffold, authoring addendum and lint script.
- [ ] **M2** Core slides: opening and online evals. **M3** Core slides: alerts, routing, Insights. **M4** Core slides: Engine, governance, closing.
- [ ] **M5** Deck assembly: three order files, lint clean, asset list.
- [ ] **M6** Notion draft v1 (what's covered, materials, talk track). **M7** Monday demo runbook.
- [ ] Stretch, in this order: **R1**, **R2**, **R3**, **R4**, **R8** (Section 1), so the presenter can show keyless cells.

**By 2026-12-02**
- [ ] **R1** Keyless helper. **R2** Seed, labels, answers, fixtures. **R3** Online evaluator. **R4** Local helpers, checker, exercises. **R5** Offline capture, Gateway replay, static fixtures. **R6** Keyed upload, destination, REST builders. **R7** SDK surface test.
- [ ] **R8** to **R11** Notebook sections 1 to 4. **R12** Builder integration and offline execution. **R13** Registration edits.
- [ ] **D1** Lab slides. **D2** Extension slides and questions.
- [ ] **I1** Instruqt track, authored and statically checked.
- [ ] **N1** Notion page final text.
- [ ] **L1** Live-check checklist for a person with a key. **V1** Full offline verification, recorded in section 21. **V2** Dry run with measured times (needs people).

## 20. Acceptance criteria and verification plan

### 20.1 On the build machine, with no keys

The shell on the build machine exports provider credential variables (note 01 key finding 13). Every command that imports repo code starts with `env -i PATH="$PATH" HOME="$HOME" LANGSMITH_TRACING=false` and uses `.venv/bin/python` (never `uv sync`).

| Check | How | Pass condition |
|---|---|---|
| Builder is deterministic | Build into a scratch folder and `cmp` with the committed notebooks; rebuild Modules 4 and 6 | Four notebooks identical; the only diffs in Modules 4 and 6 are the three forward-reference lines |
| Notebook structure | `tests/test_module7_notebooks.py`: `nbformat.validate`; no outputs; ids `cell-000…`; every code cell compiles with `ast.PyCF_ALLOW_TOP_LEVEL_AWAIT`; every image and relative link resolves | Pass |
| **Full offline execution** | `scripts/verify_module7_offline.py`: `nbclient` on scratch copies, stripped environment, a `sitecustomize` socket guard that allows loopback (the kernel needs it) and records every other connect | All four notebooks run top to bottom; 0 non-loopback connects; every "✅ Verified" line of section 6.6 is in the output |
| The same with a bad key | Repeat with `LANGSMITH_API_KEY=<placeholder>` and `LANGSMITH_TRACING=true` (state B of gap-3 §1.4) | Still runs; no failed-upload log lines |
| Seed | `tests/test_trace_seeding.py`: regenerating gives the committed bytes; `answers.json` equals `answer_key(seed)`; every constant of sections 6.2, 6.3 and 6.6; root `id == trace_id` after remap; `dotted_order` well formed; `messages` in root inputs and outputs; caller metadata on every run; every customer and order id exists in `techhub.db`; file under 5 MB; after the shift the newest root run is 5 minutes old and the oldest under 21 hours | Pass |
| Evaluator | `tests/test_online_evaluators.py`: naive 23, reference 11, equal to the answer key; a run with no outputs does not raise; `WRONG_RETURN_WINDOW_SOURCE` compiles alone and imports only the standard library; the solution file equals it | Pass |
| Local helpers and checker | `tests/test_monitoring_local.py`, `test_monitoring_checks.py`: sampling reproducible; window counts; each solution passes its check; each stub fails with the intended message; the checker works with `answers.json` absent | Pass |
| Capture and replay | `tests/test_offline_capture.py`: middleware only gives more than 0 payloads with the email; with the anonymizer 0 and the control string intact; the three spellings of `LANGSMITH_HIDE_INPUTS`; `gateway_replay` raises `RateLimitError`, `APIStatusError`, `PermissionDeniedError` with the policy name; 0 sockets | Pass. If the replay cannot be reproduced, cell 14 of Section 4 prints the saved bodies instead and the exception column cites note 06 §2.7 |
| Fixtures | `tests/test_module7_fixtures.py`: `InsightsReportResult(**data)` loads and round-trips; each issue passes `langsmith.types.issue.Issue.model_validate`; report counts and error rates equal the seed labels; no evidence comment contradicts the seed. With a local copy of the public OpenAPI document: `validate_fixtures.py` on the module's `data/` folder | Pass; 0 schema errors |
| Keyed code paths, offline | `tests/test_trace_upload.py`, `test_monitoring_rest.py` through the capture adapter: create batch then update batch, at most 250 per call, `session_id` and `extend_trace_retention=False` on feedback, the re-run guard, `min_start_time` on every query, no `create_project` call, REST URLs start with `/api/`, filter strings equal `FILTERS` | Pass |
| Keyless helper | `tests/test_langsmith_links_keyless.py`: the four credential states of gap-3 §2 | Pass |
| SDK surface | `tests/test_module7_sdk_surface.py`: `inspect.signature` for every SDK name used | Pass |
| Existing tests | `python -m unittest discover -s tests` | The 28 existing tests still pass |
| Deck | `python3 PROJECT/decks/workshop-10-monitoring/tools/lint_slides.py` | 0 findings |
| Instruqt track, static | YAML parses; `bash -n` on every script; each check run locally against the stub (fail, with the right message) and the solution (pass); no `id` or `checksum` | As stated |

### 20.2 Acceptance criteria

- All four notebooks run top to bottom from a fresh kernel with only `uv sync`, with no `.env`, and print every answer of section 6.6.
- With a key, no cell raises when the upload, the agent-based route or any optional request fails: it prints one line and continues.
- Every number on a slide, in a notebook's text, in the Notion draft and in an Instruqt assignment equals `data/answers.json`.
- The 60-minute and 120-minute columns each sum exactly.
- No slide face carries a click path or button label; no slide, note or file names a customer or a person.

## 21. Results

Empty until the module is built. Plan item V1 records here: the test count, the offline execution result, the seed file size, the final value of every design constant, and any constant that had to change.

### 21.1 Recorded by plan item R2 (seed generator, 2026-11-19)

No number that a learner sees in sections 6.2, 6.3 or 6.6 changed. `uv run python scripts/module7_seed.py verify` prints the full answer key. Four points of the seed's structure differ from the first draft of section 6.2; the first two are corrected in the table there.

1. **Failed root runs have empty outputs.** The 13 errored root runs carry `error` and outputs `{}`, not a `messages` list. That is what the LangChain tracer records for a failed chain or tool run (measured offline with a LangGraph graph whose node raises). Code that reads a reply must therefore accept a run without `messages` in its outputs; `utils.trace_seeding.reply_text(run)` returns `''` for such a run.
2. **Tree sizes.** 3 runs (direct answer, 63 traces), 10 (the specialist answers without a tool: the 11 wrong return-window traces; or the first tool fails: the 13 errored traces), 13 (scope-guard refusal, 11 traces), 14 (one delegation with one tool call, 138 traces), 33 (compatibility, 24 traces). A compatibility trace is larger than "one more branch per extra delegation": the main agent delegates, receives a complete answer and delegates the same question again, which needs a second main-agent model call, and the specialist runs two searches each time (`search_policy_docs` for the compatibility guide, `search_product_docs` for the product page). With one search per delegation the token model puts the median cost at roughly one and a half times that of a single-product spec lookup (an estimate, not a measured build), short of the "about twice" of section 6.5.
3. **The seed file stores the runs grouped by trace**, with the values every run of a trace shares (the caller metadata, the tags, the trace id) written once per trace and without `dotted_order`. This keeps the file under 5 MB. `load_seed()` returns the flat list of complete runs; a test asserts that loading gives back exactly what was generated. Read the file only through `load_seed()`.
4. **Token counts are synthetic** and leave out the all-zero `input_token_details` and `output_token_details` blocks of a live upload. The three counts are in the four documented places. `ls_integration` is not written.

Values as built: 200 conversations (140 with one turn, 60 with two), 260 root runs (156 and 104), 3,296 runs, seed file 4,897,194 bytes. Sampling seed constant `SAMPLING_SEED = 3` (65 scored, 3 caught). Illustrative prices per 1 million tokens, labelled as invented in the code and in the seed's `meta`: `gpt-5.4` 2.50 US dollars input and 10.00 output, `gpt-5.4-mini` 1.00 and 4.00. Sample report: "Compatibility between products" `cost_p50` 0.0391 and `latency_p50` 13.5 seconds against 0.0211 and 6.5 seconds for "Single-product spec lookups" (1.85 times the cost). Its `cost_p50` and `latency_p50` are medians over a category's conversations of the summed cost and the summed agent time of the conversation's turns; how the product computes these two statistics for a thread is UNVERIFIED. Engine issue 3: `recurrences_since_watching` 11. Second turns follow their first turn by 45 to 160 seconds; 12 need a lookup and 48 are answered by the main agent from the conversation so far. Refund conversations end on the `request_refund` tool call that waits for approval (the last output message has no text); the resumed trace is not seeded, because its root inputs have no `messages` key (gap-2 §3.4).

## 22. Risks and open questions

### 22.1 Risks

| Risk | Effect | Mitigation in this design |
|---|---|---|
| The lab teaches on hand-built Insights and Engine output | Wording, category count or issue style may differ from the product (gap-3 §6 item 12) | Files are labelled; numbers come from the seed; demos show the real thing where access exists; replace with real output if someone produces it |
| "Too synthetic" for rooms that want the product | Lower engagement | Keyed learners upload the same day in one cell and attach a real evaluator and automation on live traces; every topic has a demo cue |
| Seeded lite traces look thin beside a live 95-run trace | A question from the room | Said in Section 1 cell 3 and in the notes of `w10-lab-0` |
| Time boxes are untested | Rushed blocks | All minutes are labelled estimates; dry run V2; the 60-minute run uses follow-along for four of five lab blocks |
| Sandbox start-up grows with the repo clone and `uv sync` | Slow start for a room | Elapsed seconds printed per setup step; measured in the first play; the template log already records one slow start |
| Claude Code reads a solution, or is throttled | The exercise teaches less, or a room stalls | Solutions and the plain answer key leave the workshop folder; deny rules; outcome checks; typed fallback in each assignment; **Skip**; a room-sized dry run |
| `utils/langsmith_links.py` is shared with Modules 4 and 5 | A regression there breaks other workshops | Additive change; a unit test on the old call form; fallback: a new file `utils/langsmith_keyless.py` if the owner prefers |
| A 4 to 5 MB JSON file in the repo | Repo weight | Lite trees with truncated strings and a size test; fallback: generate at setup (the test already proves reproducibility) |
| Labels and behaviour change before delivery (Online Insights, Engine actions, agent-based workspaces) | Stale steps | Labels live in step tables and speaker notes only; a label check is on the day-before checklist |
| The build shell exports provider credentials | An accidental billable call during verification | The stripped-environment rule of section 20.1 |
| The module overlaps two existing tracks | A question from the other team | The new track avoids Engine set-up and policy creation; the owner tells their owners |

### 22.2 UNVERIFIED items, and why the workshop does not depend on them

| # | Unverified (source) | What depends on it | Why the workshop still works |
|---|---|---|---|
| 1 | Back-dated lite traces are accepted and charted at their own time; cost for `gpt-5.4` and `gpt-5.4-mini`; seeded feedback in filters and charts (note 08 U1, U2, U6) | The optional view of the seeded day in LangSmith | No checked answer reads it; a failed upload falls back to local mode |
| 2 | A bare project name and the compatibility route in an agent-based workspace; whether `/projects/p/<id>` links open (gap-5 Part 3 items 2 to 4) | Keyed learners in fresh organizations | `TECHHUB_AGENT_ID` route wrapped in `try/except`; navigation sentence printed beside every link |
| 3 | Backfill on seeded runs and its duration (note 08 U3) | Nothing | Evaluator and automation are attached without backfill (P3) |
| 4 | Time from trace to evaluator score; rule polling interval (gap-6 §4 item 14) | S1 cell 17 | The cell does not wait and says so; the expected result is printed |
| 5 | Whether a code evaluator's feedback key is its name or the returned key (note 03 "Unverified" item 10) | The UI step | Both are `wrong_return_window` |
| 6 | Alert preview depth, window alignment, evaluation frequency (gap-6 §4 items 5, 6) | The UI alert steps | The checked answer is a threshold that holds under any alignment; the preview and a live firing are optional |
| 7 | `POST /api/v1/runs/rules` with `code_evaluators`, and the alert request format (gap-6 §4 items 1, 2) | S1 cell 27 | Off by default; bodies are printed; no alert request is sent from code |
| 8 | Whether Engine opens useful issues on generated traces (gap-1 "Unverified" item 3); whether Engine is enabled in the demo organization (note 05 open question 4) | The Engine demo | The saved board; slides `t-engine`, `w10-engine-issue` |
| 9 | Whether a real Insights report over the seed finds comparable categories; whether Online Insights replaced the batch flow (note 04 §13) | The Insights demo | The sample report; slides |
| 10 | The agent's behaviour on a policy block; placeholder restoration on the `LANGSMITH_GATEWAY=true` route; PII entitlement of any demo organization (note 06 "Unverified" items 7, 10; key finding 5) | The Gateway demo | Offline replay and text labelled UNVERIFIED; slides |
| 11 | UI labels in both workspace types (note 03 "Unverified" item 16; gap-5 Part 3 item 8) | Step tables | Both wordings given; nothing on slide faces (P9) |
| 12 | Everything about the pushed track (section 14.4 item 7) | The Instruqt delivery | Notebooks are the fallback and need no sandbox |
| 13 | The 30-second limit of code evaluators (note 03 §2.3; not on the page as fetched today) | Nothing | Not printed on a slide |
| 14 | Tree characters and status marks in the code-server terminal and JupyterLab (gap-3 §6 item 10) | Appearance | Checked in the first play |

Items 1 to 7 need about half an hour with any LangSmith key in a fresh account; nobody on this project has measured that estimate. Plan item L1 writes the checklist. The order of work is: run the short live test of the seed upload first, and only then switch keyed defaults on (owner decision 10 in the plan).

### 22.3 Open questions for the owner

Listed with recommended defaults in `PROJECT/module-7-build/plan.md`, section "Decisions for the owner".

## 23. Out of scope

- Switching Modules 4 to 6 to `setup_langsmith()`; fixing the README sentence on key precedence.
- A TechHub data pack for the provisioning tools; a shared workshop Gateway key.
- A recorded trace file for attendee-run Engine; any attendee-run Engine, Insights or Gateway policy step as a requirement.
- Committing, pushing, opening a pull request, pushing the track, writing to Notion.
- The alert-and-routing and prove-the-fix Instruqt challenges (after the first dry run).
