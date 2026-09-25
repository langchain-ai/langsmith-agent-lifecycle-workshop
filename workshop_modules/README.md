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

