# AI Engineering Lifecycle on LangSmith Platform

<div align="center">
    <img src="images/techhub_logo.png" width="500">
</div>

Enterprise workshop series teaching the complete AI engineering lifecycle using LangChain, LangGraph, and LangSmith—centered around building a customer support agent for a fictional online technology e-commerce store called TechHub.

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
git clone https://github.com/langchain-ai/techhub-workshop.git
cd techhub-workshop

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

## Workshop Outline

This workshop consists of three modules that take you from manual tool calling to production deployment:

1. **Module 1: Agent Development** - Build from basics to multi-agent systems with HITL
2. **Module 2: Evaluation & Improvement** - Use eval-driven development to systematically improve agents
3. **Module 3: Deployment & Continuous Improvement** - Deploy to production and build a data flywheel

📚 To get started, see [workshop_modules/README.md](workshop_modules/README.md)


## Repo Structure

```
techhub-workshop/
├── workshop_modules/        # Interactive Jupyter notebooks
│   ├── module_1/            # Agent Development (4 sections)
│   ├── module_2/            # Evaluation & Improvement (2 sections)
│   └── module_3/            # Deployment & Continuous Improvement (2 sections)
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
