# AI Engineering Lifecycle on LangSmith Platform

Enterprise workshop series teaching the complete AI engineering lifecycle using LangChain, LangGraph, and LangSmith—centered around building a customer support agent for a fictional online technology e-commerce store called TechHub.

<div align="center">
    <img src="images/main_graphic.png">
</div>

## What You'll Build

A customer support agent system featuring:
- **Multi-agent architecture** with specialized Database and Documents agents coordinated by a Supervisor
- **Human-in-the-loop (HITL)** customer verification with LangGraph primitives
- **Evaluation-driven development** using offline evaluation to identify and fix bottlenecks
- **Production deployment** to LangSmith with online evaluation and data flywheels for continuous improvement

## Quick Setup

This workshop uses [uv](https://docs.astral.sh/uv/) - a fast Python package installer and resolver. If you don't have it:

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then set up the workshop:

```bash
# Clone repository
git clone https://github.com/langchain-ai/langsmith-agent-lifecycle-workshop.git
cd langsmith-agent-lifecycle-workshop

# Install dependencies (creates virtual environment automatically)
uv sync

# Configure API keys
cp .env.example .env
# Edit .env and add your API keys:
#   ANTHROPIC_API_KEY=sk-ant-...
#   LANGSMITH_API_KEY=lsv2_pt_...

# Build vectorstore (one-time setup, ~60 seconds)
uv run python data/data_generation/build_vectorstore.py

# Launch Jupyter
uv run jupyter lab
```

### Embedding Configuration (Optional)

By default, the vectorstore uses **HuggingFace embeddings** (local model, no API key required). If you're in an environment where downloading models from HuggingFace is restricted, you can use **OpenAI embeddings** instead:

```bash
# Add to your .env file:
EMBEDDING_PROVIDER=openai

# Rebuild the vectorstore with OpenAI embeddings
uv run python data/data_generation/build_vectorstore.py
```

### LLM Gateway (Optional)

Instead of storing raw Anthropic/OpenAI API keys, orgs with access to LangSmith's [LLM Gateway](https://docs.langchain.com/langsmith/llm-gateway) can route chat model calls through it using a LangSmith API key with `gateway:invoke` permission:

```bash
# Add to your .env file instead of ANTHROPIC_API_KEY / OPENAI_API_KEY:
LANGSMITH_GATEWAY="true"
LANGSMITH_GATEWAY_API_KEY="<langsmith-api-key-with-gateway-invoke>"
```

This covers chat models only (requires `langchain-anthropic>=1.5.1` / `langchain-openai>=1.4.1`, already the repo minimums). If `EMBEDDING_PROVIDER=openai`, embeddings need their own gateway setup instead, since they aren't covered by `LANGSMITH_GATEWAY`:

```bash
OPENAI_API_KEY="<langsmith-api-key-with-gateway-invoke>"
OPENAI_BASE_URL="https://gateway.smith.langchain.com/openai/v1"
```

This is entirely optional - direct provider API keys (the default setup above) work the same either way, so this only applies if your org has gateway access.

## Workshop Outline

This workshop consists of three modules that take you from manual tool calling to production deployment:

1. **Module 1: Agent Development** - Build from basics to multi-agent systems with HITL
2. **Module 2: Evaluation & Improvement** - Use eval-driven development to systematically improve agents
3. **Module 3: Deployment & Continuous Improvement** - Deploy to production and build a data flywheel

📚 To get started, see [workshop_modules/README.md](workshop_modules/README.md)

## Continuous Evaluation (CI/CD)

Every PR that touches agent-relevant code (`agents/`, `tools/`, `evaluators/`, `deployments/`, `evals/`, `config.py`) is automatically evaluated against the Module 2 baseline dataset — the same `correctness` and `total_tool_calls` evaluators from Module 2, wired into GitHub Actions as a merge-blocking regression test rather than something you have to remember to run by hand.

- **See it in code:** [`evals/run_ci_eval.py`](evals/run_ci_eval.py) and [`.github/workflows/eval-regression.yml`](.github/workflows/eval-regression.yml)
- **See it explained:** [`workshop_modules/module_3/section_3_cicd_regression_gate.ipynb`](workshop_modules/module_3/section_3_cicd_regression_gate.ipynb)
- **Demo it live:** run `./scripts/demo_ci_pr.sh` to open a throwaway PR that only touches `evals/DEMO_TRIGGER.md` — no real agent/eval code changes — so you can show the gate triggering and passing (or failing) an audience without needing a real code change every time. Close the PR without merging when you're done.

## Repo Structure

```
langsmith-agent-lifecycle-workshop/
├── workshop_modules/        # Interactive Jupyter notebooks
│   ├── module_1/            # Agent Development (4 sections)
│   ├── module_2/            # Evaluation & Improvement (3 sections)
│   └── module_3/            # Deployment & Continuous Improvement (3 sections)
│
├── agents/                  # Reusable agent factory functions
│   ├── db_agent.py          # Database queries (rigid tools)
│   ├── sql_agent.py         # Flexible SQL generation (improved)
│   ├── docs_agent.py        # RAG for product docs & policies
│   ├── supervisor_agent.py  # Multi-agent coordinator
│   └── supervisor_hitl_agent.py  # Full verification + routing system
│
├── tools/                   # Database & document search tools
│   ├── database.py          # 6 DB tools (orders, products, SQL)
│   └── documents.py         # 2 RAG tools (products, policies)
│
├── evaluators/              # Evaluation metrics
│   └── evaluators.py        # Correctness & tool call counters
│
├── evals/                   # CI/CD regression gate
│   ├── run_ci_eval.py       # Runs Module 2 evaluators, gates on threshold
│   └── DEMO_TRIGGER.md      # No-op file for demoing the CI gate via a PR
│
├── deployments/             # Production-ready graph configurations
│   ├── db_agent_graph.py                   # Baseline database agent
│   ├── docs_agent_graph.py                 # RAG documents agent
│   ├── sql_agent_graph.py                  # Improved SQL agent
│   ├── supervisor_agent_graph.py           # Basic supervisor
│   ├── supervisor_hitl_agent_graph.py      # Supervisor with verification
│   └── supervisor_hitl_sql_agent_graph.py  # Complete system (best)
│
├── data/                    # Complete dataset & generation scripts
│   ├── structured/          # SQLite DB + JSON files
│   ├── documents/           # Markdown docs for RAG
│   ├── vector_stores/       # Pre-built vectorstore
│   └── data_generation/     # Scripts to regenerate data
│
├── scripts/                 # Maintenance & demo scripts
│   └── demo_ci_pr.sh        # Opens a throwaway PR to demo the eval gate
│
├── .github/workflows/       # CI/CD
│   ├── eval-regression.yml  # Eval Regression Gate (this section)
│   └── simulate_traffic.yml # Simulated production traffic for demos
│
├── config.py                # Workshop-wide configuration
├── langgraph.json           # LangGraph deployment config
└── pyproject.toml           # Dependencies
```

## Key Concepts Covered

- **Agent Development:** Tool calling, multi-agent systems, supervisor pattern, HITL with interrupts
- **Evaluation & Testing:** Offline evaluation, LLM-as-judge, trace metrics, eval-driven development
- **Deployment & Production:** LangSmith deployments, online evaluation, annotation queues, SDK integration
- **Best Practices:** Factory functions, state management, dynamic prompts, structured outputs, streaming

See [workshop_modules/README.md](workshop_modules/README.md) for detailed breakdown by module.

## Dataset Overview

The **TechHub dataset** is a high-quality synthetic e-commerce dataset:
- **50 customers** across consumer, corporate, and home office segments
- **25 products** (laptops, monitors, keyboards, audio, accessories)
- **250 orders** spanning 2 years with realistic patterns
- **439 order items** with product affinity patterns
- **SQLite database** (156 KB) with full schema and indexes
- **30 documents** (25 product specs + 5 policies) for RAG

All data is ready to use! See `data/data_generation/README.md` for details.

## Additional Resources

### Documentation
- **Data Generation Guide:** `data/data_generation/README.md` - Complete dataset documentation
- **Database Schema:** `data/structured/SCHEMA.md` - Full schema reference
- **RAG Documents:** `data/documents/DOCUMENTS_OVERVIEW.md` - Document corpus guide
- **Agent Architecture:** `agents/README.md` - Agent factory patterns

### External Links
- [LangChain Python Docs](https://python.langchain.com)
- [LangGraph Python Docs](https://langchain-ai.github.io/langgraph)
- [LangSmith Platform](https://smith.langchain.com)
- [LangChain Academy](https://academy.langchain.com)

## Prerequisites

### Required (Complete Before Workshop)

Free courses from [LangChain Academy](https://academy.langchain.com):
- [LangChain Essentials - Python](https://academy.langchain.com/courses/langchain-essentials-python) (30 min)
- [LangGraph Essentials - Python](https://academy.langchain.com/courses/langgraph-essentials-python) (1 hour)
- [LangSmith Essentials](https://academy.langchain.com/courses/quickstart-langsmith-essentials) (30 min)

### Recommended (For Deeper Understanding)

- [Foundation: Introduction to LangGraph](https://academy.langchain.com/courses/intro-to-langgraph) (6 hours)
- [Foundation: Introduction to Agent Observability & Evaluations](https://academy.langchain.com/courses/intro-to-langsmith) (3.5 hours)

### Technical Requirements

- **Python 3.10+**
- **API Keys:**
  - LangSmith (free tier: [smith.langchain.com](https://smith.langchain.com))
  - Anthropic or OpenAI (workshop uses Claude Haiku 4.5 by default)
- **Tools:** Git, Jupyter, uv (or pip)

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

Educational workshop materials. Synthetic dataset free to use and distribute.

---

**Ready to begin?** Open `workshop_modules/module_1/section_1_foundation.ipynb` and start building! 🚀
