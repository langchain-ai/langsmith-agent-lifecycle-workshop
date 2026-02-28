# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an enterprise workshop series teaching the complete AI engineering lifecycle using LangChain, LangGraph, and LangSmith. It centers around building a customer support agent for TechHub, a fictional e-commerce store.

The workshop progresses through three modules:
1. **Agent Development** - Building multi-agent systems with human-in-the-loop
2. **Evaluation & Improvement** - Using offline evaluation to systematically improve agents
3. **Production Deployment** - Deploying to LangSmith with online evaluation and data flywheels

## Essential Commands

### Environment Setup
```bash
# Install dependencies (creates .venv automatically)
uv sync

# Configure environment
cp .env.example .env
# Edit .env with your API keys
# Optional: Set EMBEDDING_PROVIDER=openai if HuggingFace downloads are blocked

# Build vectorstore (required one-time setup, ~60 seconds)
# Uses HuggingFace embeddings by default (local, no API key)
# Set EMBEDDING_PROVIDER=openai in .env to use OpenAI embeddings instead
uv run python data/data_generation/build_vectorstore.py

# Note: Changing EMBEDDING_PROVIDER requires rebuilding the vectorstore
```

### Development
```bash
# Launch Jupyter for workshop notebooks
uv run jupyter lab

# Test LangGraph deployments locally
langgraph dev

# Test specific deployment graph
langgraph dev --graph supervisor_hitl_sql_agent
```

### Running Python Scripts
```bash
# All Python commands should use uv
uv run python <script.py>
```

## Architecture Overview

### Agent Factory Pattern

All agents use factory functions that return compiled LangGraph graphs:

```python
from agents import create_db_agent, create_docs_agent, create_supervisor_agent

# Development mode (with checkpointer for memory)
agent = create_db_agent(use_checkpointer=True)

# Production mode (LangSmith manages state)
agent = create_db_agent(use_checkpointer=False)
```

**Available Agents** (in `agents/`):
- `db_agent.py` - Rigid database tools for order/product queries
- `sql_agent.py` - Flexible SQL generation (improved version from Module 2)
- `docs_agent.py` - RAG search over product specs and policies
- `supervisor_agent.py` - Coordinates DB + Docs agents
- `supervisor_hitl_agent.py` - Full system with customer verification using LangGraph interrupts

### Multi-Agent System Architecture

The complete system (`supervisor_hitl_agent`) uses a three-stage flow:

1. **Classification** - Determines if query requires customer identity verification
2. **Verification (HITL)** - Uses `interrupt()` to collect and validate customer email
3. **Supervisor Routing** - Routes to specialized sub-agents (DB/SQL and Docs agents)

Key implementation details:
- Uses custom `IntermediateState(MessagesState)` to share `customer_id` between parent and subgraphs
- Subgraphs are added as nodes using `.add_node("supervisor", supervisor_graph)`
- Shared state keys (like `messages`) automatically flow between parent and subgraphs
- Dynamic prompts inject state (e.g., `customer_id`) at runtime

### State Management

**Development vs. Deployment:**
- **Local/Notebooks**: `use_checkpointer=True` with `MemorySaver()` for conversation memory
- **Production**: `use_checkpointer=False` because LangGraph Cloud provides managed persistence

**Custom State Schemas:**
```python
from langgraph.graph import MessagesState

class IntermediateState(MessagesState):
    customer_id: str  # Shared between parent and subgraphs
```

### Configuration System

Centralized in `config.py`:
- `DEFAULT_MODEL` - Workshop-wide model setting (override with `WORKSHOP_MODEL` env var)
- `DEFAULT_EMBEDDING_PROVIDER` - Embedding provider setting (override with `EMBEDDING_PROVIDER` env var, defaults to `huggingface`)
- `DEFAULT_DB_PATH` - Path to SQLite database
- `DEFAULT_VECTORSTORE_PATH` - Path to pre-built vectorstore (includes provider in filename)
- Path resolution handles both local dev and LangSmith deployment environments

All agents inherit settings from `config.py` but can override:
```python
agent = create_db_agent(model="anthropic:claude-sonnet-4")
```

## Key Files and Directories

### Core Modules
- `agents/` - Reusable agent factory functions
- `tools/` - Database tools (`database.py`) and RAG tools (`documents.py`)
- `evaluators/` - LLM-as-judge (`correctness_evaluator`) and trace-based metrics (`count_total_tool_calls_evaluator`)
- `deployments/` - Production-ready graph configurations referenced by `langgraph.json`

### Workshop Content
- `workshop_modules/` - 3 modules, 8 sections (Jupyter notebooks)
  - Work through sequentially: each builds on previous concepts
  - Start with `module_1/section_1_foundation.ipynb`

### Data
- `data/structured/techhub.db` - SQLite database (50 customers, 25 products, 250 orders)
- `data/documents/` - 30 markdown docs (product specs + policies) for RAG
- `data/vector_stores/techhub_vectorstore_{provider}.pkl` - Pre-built vectorstore (must run `build_vectorstore.py` first, provider is `huggingface` or `openai`)
- `data/structured/SCHEMA.md` - Complete database schema reference

### Deployment
- `langgraph.json` - Defines 6 deployable graphs for LangSmith
- Each deployment imports from `deployments/` and sets `use_checkpointer=False`

## Database Schema

TechHub SQLite database (`techhub.db`):
- **customers** (50 records) - customer_id, email, name, segment (Consumer/Corporate/Home Office)
- **products** (25 records) - product_id, name, category, price, stock_quantity
- **orders** (250 records) - order_id, customer_id, status, order_date, ship_date
- **order_items** (439 records) - order_item_id, order_id, product_id, quantity, price

Customer IDs: `CUST-###`
Order IDs: `ORD-YYYY-####`
Product IDs: `TECH-XXX-###` (XXX = LAP/MON/KEY/AUD/ACC)

See `data/structured/SCHEMA.md` for complete schema details.

## Tools Architecture

**Database Tools** (`tools/database.py`):
- Lazy-loaded SQLDatabase connection at module level
- 6 tools: `get_order_status`, `get_customer_orders`, `get_product_info`, `get_order_item_price`, `get_product_price`, `execute_sql`
- Tools are designed for customer support queries (not admin functions)

**Document Tools** (`tools/documents.py`):
- Lazy-loaded InMemoryVectorStore with configurable embeddings (HuggingFace or OpenAI)
- Embedding provider controlled by `EMBEDDING_PROVIDER` env var (defaults to HuggingFace)
- Vectorstore filename includes provider: `techhub_vectorstore_{provider}.pkl`
- 2 tools: `search_product_documents`, `search_policy_documents`
- Vectorstore must be built first using `build_vectorstore.py`

## Evaluation Patterns

**Reference-based evaluators** (compare output to ground truth):
```python
def evaluator(inputs: dict, outputs: dict, reference_outputs: dict) -> dict:
    return {"key": "metric_name", "score": value}
```

**Trace-based evaluators** (analyze execution metadata):
```python
from langsmith.schemas import Run

def evaluator(run: Run) -> dict:
    return {"key": "metric_name", "score": value}
```

LangSmith automatically routes based on function signature. Can mix both types in experiments.

## Important Patterns

### Factory Function Signature
```python
def create_agent(
    state_schema=MessagesState,
    model: str = DEFAULT_MODEL,
    additional_tools: list = None,
    use_checkpointer: bool = True,
) -> CompiledGraph:
    # Returns compiled graph ready for .invoke() or .stream()
```

### Deployment Pattern
```python
# deployments/example_graph.py
from agents import create_example_agent

# Module-level graph instance for LangSmith
graph = create_example_agent(use_checkpointer=False)
```

### HITL with Interrupts
```python
from langgraph.types import interrupt

# Pause execution and wait for user input
user_input = interrupt({"question": "What is your email?"})
```

### Dynamic Prompts
```python
# System prompt can access state at runtime
system_prompt = f"""You are helping customer {state['customer_id']}..."""
```

### Structured Outputs
```python
from typing_extensions import TypedDict

class OutputSchema(TypedDict):
    reasoning: str
    decision: bool

# Use with_structured_output for type safety
model.with_structured_output(OutputSchema)
```

## Module-Specific Notes

### Module 1: Agent Development
- Progression: Manual loop → `create_agent()` → Multi-agent → HITL
- Section 4 introduces the complete supervisor HITL system with interrupts
- Uses `Command` for explicit routing control in state graphs

### Module 2: Evaluation & Improvement
- Section 1: Build baseline with curated dataset in `baseline_dataset.json`
- Section 2: Introduces SQL agent to fix inefficiency identified in eval
- Demonstrates eval-driven development: measure → identify issue → improve → re-measure
- Shows how to compose improved SQL agent with existing supervisor system

### Module 3: Deployment & Production
- Section 1: Online evaluation, annotation queues, automation rules
- Section 2: LangGraph SDK for streaming and programmatic HITL handling
- Focus on production data flywheel for continuous improvement

## Environment Variables

Required API keys in `.env`:
- `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` (depending on model choice)
- `LANGSMITH_API_KEY` (for tracing and experiments)

Optional configuration:
- `WORKSHOP_MODEL` - Override default model for all agents (default: `anthropic:claude-haiku-4-5`)
- `EMBEDDING_PROVIDER` - Embedding provider for vectorstore: `huggingface` (default, local) or `openai` (requires `OPENAI_API_KEY`)
- `LANGSMITH_PROJECT` - Project name for traces (default: `langsmith-agent-lifecycle-workshop`)
- `LANGSMITH_TRACING` - Enable/disable tracing (default: `true`)

## Development Workflow

1. **Starting a new module**: Open corresponding notebook in `workshop_modules/`
2. **Testing agents locally**: Use notebooks or `langgraph dev`
3. **Making changes to agents**: Edit factory functions in `agents/`
4. **Adding tools**: Extend `tools/database.py` or `tools/documents.py`
5. **Deploying**: Update deployment file in `deployments/`, ensure `use_checkpointer=False`
6. **Evaluation**: Create dataset → run experiment → analyze results → iterate

## Common Gotchas

- **Vectorstore not found**: Must run `uv run python data/data_generation/build_vectorstore.py` before using RAG tools. If changing `EMBEDDING_PROVIDER`, must rebuild vectorstore
- **Checkpointer conflicts**: Use `use_checkpointer=False` for production deployments (LangSmith manages state)
- **State schema mismatches**: Shared keys in custom state must match parent/subgraph schemas
- **Path resolution**: `config.py` handles both local (`Path(__file__).parent`) and LangSmith deployment (`/deps/...`) paths
- **Database connection**: Uses lazy loading at module level - connection is created on first tool use
