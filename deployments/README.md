# Deployment Configurations

This directory contains deployment-ready graph instances for LangSmith deployment.

## Purpose

The `deployments/` directory provides a clean separation between:
- **Development/Workshop**: Factory functions in `agents/` with flexible parameters
- **Deployment**: Fixed, module-level graph instances ready for `langgraph.json`

## Pattern

### Factory Function (agents/)
Used in notebooks and development for flexibility:

```python
from agents import create_db_agent
from tools import get_customer_orders

# Flexible - can customize state schema and tools
db_agent = create_db_agent(
    state_schema=CustomState,
    additional_tools=[get_customer_orders]
)
```

### Deployment Instance (deployments/)
Used for LangSmith deployment with fixed configuration:

```python
# deployments/db_agent_graph.py
from agents import create_db_agent

# Module-level instance for deployment
# use_checkpointer=False because platform provides managed persistence
graph = create_db_agent(use_checkpointer=False)
```

### Configuration (langgraph.json)
References the module-level graph instance:

```json
{
  "graphs": {
    "db_agent": "./deployments/db_agent_graph.py:graph"
  }
}
```

## Why This Approach?

1. **Pedagogical Clarity**: Workshop participants see both patterns
2. **Separation of Concerns**: Development flexibility vs. deployment stability
3. **Best Practice**: Follows [LangChain deployment guidelines](https://docs.langchain.com/langsmith/setup-pyproject)
4. **Module 3 Foundation**: This pattern becomes essential for deployment workflows

## Important: Checkpointer Behavior

**Development (notebooks):**
```python
db_agent = create_db_agent()  # use_checkpointer=True by default
```

**Deployment (LangGraph API):**
```python
graph = create_db_agent(use_checkpointer=False)  # Platform provides persistence
```

Why? LangGraph API [handles persistence automatically](https://docs.langchain.com/oss/python/langgraph/persistence) with managed Postgres. Set `use_checkpointer=False` to disable the local checkpointer for deployment.

## Current Deployments

### Module 1 Agents
- `db_agent_graph.py` - Database agent with rigid tools (Module 1 baseline)
- `docs_agent_graph.py` - Documents agent for searching product docs and policies
- `supervisor_agent_graph.py` - Supervisor coordinating db_agent + docs_agent
- `supervisor_hitl_agent_graph.py` - Complete verification + supervisor with HITL

### Module 2 Agents (Improved)
- `sql_agent_graph.py` - SQL agent with flexible query generation (Module 2 improvement)
- `supervisor_hitl_sql_agent_graph.py` - Verification + supervisor using SQL agent

## Agent Evolution & Composition

The workshop demonstrates **eval-driven development** through deployment variants:

### Phase 1: Baseline (Module 1)
```python
# deployments/supervisor_hitl_agent_graph.py
from agents import create_supervisor_hitl_agent

# Uses default db_agent with rigid tools
graph = create_supervisor_hitl_agent(use_checkpointer=False)
```

### Phase 2: Improved (Module 2)
```python
# deployments/supervisor_hitl_sql_agent_graph.py
from agents import create_sql_agent, create_supervisor_hitl_agent
from agents.supervisor_hitl_agent import CustomState
from tools import get_customer_orders

# Instantiate improved SQL agent
sql_agent = create_sql_agent(
    state_schema=CustomState,
    additional_tools=[get_customer_orders],
    use_checkpointer=False,
)

# Compose into supervisor HITL (dependency injection)
graph = create_supervisor_hitl_agent(
    db_agent=sql_agent,
    use_checkpointer=False,
)
```

**Key Teaching Points:**
1. **Baseline → Evaluation → Improvement**: Module 1 baseline → Module 2 eval reveals issues → SQL agent improves
2. **Composition over Rewriting**: Swap in improved agent without changing verification logic
3. **Side-by-Side Comparison**: Both deployments available for A/B testing in production

## Adding New Deployments

1. Create a new file: `deployments/your_agent_graph.py`
2. Import and instantiate: `graph = create_your_agent()`
3. Add to `langgraph.json`: `"your_agent": "./deployments/your_agent_graph.py:graph"`
4. Export in `__init__.py`

