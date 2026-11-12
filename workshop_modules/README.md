# Workshop Modules

This workshop teaches the complete AI engineering lifecycle through three progressive modules. Work through them sequentially - each builds on concepts from the previous module.

## Getting Started

1. **Start here:** Open `module_1/section_1_foundation.ipynb`
2. **Work sequentially** through sections - each builds on the previous
3. **Run all cells** - notebooks are self-contained with explanations and examples

Each notebook includes:
- 📖 Clear explanations of concepts
- 💻 Working code examples
- 🎯 Hands-on exercises
---

## Module 1: Agent Development

Build from manual tool calling to production-ready multi-agent systems.

**Section 1: Foundation** (`module_1/section_1_foundation.ipynb`)
- Manual tool calling loop with database tools
- Understanding how agents work under the hood

**Section 2: Create Agent** (`section_2_create_agent.ipynb`)
- Using `create_agent()` abstraction
- Memory with checkpointers and thread separation
- Streaming for better UX

**Section 3: Multi-Agent** (`section_3_multi_agent.ipynb`)
- Database Agent (order status, product info, pricing)
- Documents Agent (product specs, policies via RAG)
- Supervisor Agent coordinating parallel and sequential tasks

**Section 4: LangGraph HITL** (`section_4_langgraph_hitl.ipynb`)
- Customer verification with `interrupt()` for HITL
- Query classification and conditional routing
- Dynamic prompts injecting state (customer_id)
- Full integration of verification + supervisor + sub-agents

---

## Module 2: Evaluation & Improvement

Learn evaluation-driven development to systematically improve agents.

**Section 1: Baseline Evaluation** (`module_2/section_1_baseline_evaluation.ipynb`)
- Curated dataset with ground truth examples
- LLM-as-judge correctness evaluator
- Trace-based tool call counter
- Running experiments in LangSmith

**Section 2: Eval-Driven Development** (`section_2_eval_driven_development.ipynb`)
- Identified problem: Rigid DB tools → excessive tool calls
- Solution: SQL Agent with flexible query generation
- Re-evaluation showing quantitative improvement
- Composing improved agent with existing system

**Section 3: Advanced Evaluation** (`section_3_advanced_evaluation.ipynb`)
- Single-step evaluation: unit-testing isolated routing decisions
- Trajectory evaluation: verifying HITL steps, tool call sequences, and efficiency
- Run-based evaluators: traversing the LangSmith trace tree to inspect sub-agent tool calls
- Multi-turn simulation: realistic customer conversations with LLM-simulated users

**Bonus: Aligning an LLM-as-Judge** (`bonus_align_llm_judge.ipynb`)
- Measuring agreement between the Module 2 `correctness` judge and human labels on a 30-item golden set (`golden_set.json`)
- Grouping disagreements by cause with a confusion matrix and the judge's reasoning
- Fixing the rubric one rule at a time and re-measuring on the same frozen outputs

---

## Module 3: Deployment & Continuous Improvement

Deploy to production and build a data flywheel for continuous improvement.

**Section 1: Production Data Flywheel** (`module_3/section_1_production_data_flywheel.ipynb`)
- Creating deployments in LangSmith
- Setting up online evaluation (LLM-as-judge for helpfulness)
- Building annotation queues for human review
- Automation rules to capture production failures
- Complete data flywheel: production → annotation → dataset → improvement

**Section 2: SDK Interaction** (`section_2_sdk_interaction.ipynb`)
- Using LangGraph SDK to call deployed agents
- Streaming responses from production
- Handling HITL interrupts programmatically
- Building custom integrations and applications

**Section 3: CI/CD Regression Gating** (`section_3_cicd_regression_gate.ipynb`)
- Wiring the Module 2 evaluators into GitHub Actions as a merge-blocking check
- Syncing a single, git-sourced LangSmith dataset for comparable experiments across PRs
- Tracing experiments back to the PR/commit that produced them
- How offline CI gating and the online eval flywheel (Section 1) reinforce each other

---

## Module 4: Deep Agents (101 → 201)

Rebuild the TechHub support agent on the Deep Agents harness, then improve it by tuning the harness while the model stays fixed. Uses `agents/deep_support_agent.py`.

**Section 1: Deep Agents 101** (`module_4/section_1_deep_agents_101.ipynb`), a TechHub pricing research agent (`agents/pricing_research_agent.py`)
- What a deep agent is: `create_agent()` + a harness (planning, filesystem, subagents, context management)
- Provider built-in web search (no search API key) + the TechHub catalog
- Planning with `TodoListMiddleware`, saving reports to the filesystem
- Subagents: `market-researcher` and `catalog-analyst` on a smaller model; `AGENTS.md` + a `competitive-pricing` skill
- Follow-up research on the same thread, long-term memory for analyst preferences
- Human approval before any price change
- Guardrails: a research budget, a `think_tool` reflection step, numbered citations, and fault-tolerance middleware

**Section 2: Deep Agents 201: Harness Engineering** (`module_4/section_2_harness_engineering.ipynb`)
- The Module 1 supervisor as a deep agent (subagent specs instead of hand-wrapped tools)
- Context engineering: `AGENTS.md` (always loaded) vs skills (on demand) vs memory
- Routing memory with `CompositeBackend`: per-customer `/memories/`, read-only org assets
- Context quarantine: subagent tool calls never enter the main context
- Fewer tools per model call: provider tool search vs `LLMToolSelectorMiddleware`, measured on the order specialist
- Custom middleware: PII redaction (input, output, tool results), verified-customer prompt, customer-scope guard
- Fault tolerance: retries, a cross-provider fallback to Claude (with a simulated outage), and call limits
- Human-in-the-loop on refunds and filesystem permissions

**Section 3: Deep Agents 201: Orchestration and Verification** (`module_4/section_3_orchestration_and_verification.ipynb`)
- Dynamic subagents: the agent writes the dispatch loop over a support inbox
- Verification loop with `RubricMiddleware`
- Multi-model harnesses: single- vs multi-model on the same tickets
- Jev as a decision model (`langchain-typesafe`): triage the inbox with typed answers and probabilities, compare with a small LLM, route by confidence
- Jev inside the agent: a tool-safety gate that sends likely side effects to a person
- The four loops of loop engineering and where each lives in this workshop

---

## Module 5: Advanced Evaluation

Module 2's evaluation path, repeated on the Module 4 deep agent, then Harbor evals in sandboxes. Notebooks are generated by `scripts/notebook_builders/build_module5.py`.

**Section 1: Baseline Evaluation** (`module_5/section_1_baseline_evaluation.ipynb`)
- Module 2's 12 examples plus a cross-customer question (`module_5/baseline_dataset.json`)
- A target function that signs the customer in: customer ID from the email, passed as run context
- Correctness, total tool calls, and order-specialist tool calls

**Section 2: Eval-Driven Development** (`module_5/section_2_eval_driven_development.ipynb`)
- A customer-scoped SQL tool (`query_my_orders`) instead of a raw `execute_sql`
- `create_deep_support_agent(order_tools="sql")`, re-evaluated on the same dataset and compared

**Section 3: Aligning the Judge** (coming soon)

**Section 4: Jev as a Judge** (coming soon)

**Section 5: Harbor Evals** (`module_5/section_5_harbor_evals.ipynb`)
- Environment evals: the managed agent in a fresh LangSmith sandbox, graded on its saved run state
- Building a task spec-first, testing the verifier (local fixtures and the oracle), and breaking the agent on purpose

---

## Module 6: Deploying Agents into Production

Run the Module 4 agent as a Managed Deep Agent (`managed_agent/`). Requires a LangSmith Cloud workspace (GCP US/EU/APAC or AWS US) with MDA public beta access, and `mda deploy` (see `managed_agent/README.md`).

**Section 1: Managed Deep Agents** (`module_6/section_1_managed_deep_agents.ipynb`)
- From `create_deep_agent` to `define_deep_agent`: what moves where
- Project anatomy, `mda dev` and `mda deploy`, the LLM Gateway model string
- Calling the deployed agent with a verified customer as run context
- Production guardrails MDA doesn't add for you; identity claims vs run context
- Human-in-the-loop over the API; Context Hub, ops-only agent memory, and schedules

**Section 2: Runtime and Sandboxes** (`module_6/section_2_runtime_and_sandboxes.ipynb`)
- Agent Server primitives: assistants, threads, runs, streaming
- Per-thread sandboxes provisioned by `setup.sh` snapshots
- A default-deny egress allowlist, demonstrated with a blocked request
- Why customer data stays out of the sandbox, and a sandbox security checklist
- Harbor evals before you ship: correctness, authorization, and grounding tasks (`managed_agent/evals/`)

---

## Key Concepts Covered

### Agent Development
- Tool calling and agent loops
- Multi-agent systems with supervisor pattern
- Sub-agent coordination (parallel & sequential)
- State management and memory
- Human-in-the-loop with interrupts

### Evaluation & Testing
- Offline evaluation with LangSmith
- LLM-as-judge evaluators
- Trace-based metrics
- Experiment comparison
- Evaluation-driven development workflow

### Deployment & Production
- LangSmith deployments and revisions
- Online evaluation and monitoring
- Annotation queues and human review
- Automation rules for continuous improvement
- SDK integration for custom applications

### Best Practices Throughout
- Factory functions for agent reusability
- Separation of dev (checkpointer) vs. deploy (platform-managed)
- Dynamic prompts with state injection
- Structured outputs with Pydantic
- Streaming for better UX

---

**Ready to begin?** Open `module_1/section_1_foundation.ipynb` and start building! 🚀

