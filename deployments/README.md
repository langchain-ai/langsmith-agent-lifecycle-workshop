# Deployments

Production-ready graph configurations for deploying to LangSmith. Each file exports a `graph` instance referenced in `langgraph.json`.

## Available Deployments

| Deployment | Agent | Description | Module |
|------------|-------|-------------|--------|
| `db_agent_graph.py` | Database Agent | Baseline with rigid tools | 1 |
| `sql_agent_graph.py` | SQL Agent | Improved with flexible queries | 2 |
| `docs_agent_graph.py` | Documents Agent | RAG search over docs/policies | 1 |
| `supervisor_agent_graph.py` | Supervisor | Coordinates DB + Docs agents | 1 |
| `supervisor_hitl_agent_graph.py` | Supervisor HITL | Full system with verification | 1 |
| `supervisor_hitl_sql_agent_graph.py` | Supervisor HITL + SQL | Best version (SQL agent) | 2 |

## Structure

Each deployment file follows a simple pattern:

```python
# deployments/db_agent_graph.py
from agents import create_db_agent

# Module-level graph instance for LangSmith deployment
graph = create_db_agent(use_checkpointer=False)
```

**Key difference from workshop notebooks:**
- `use_checkpointer=False` - LangSmith provides managed persistence, so disable local checkpointer

## LangSmith Deployment

These deployments are referenced in `langgraph.json`:

```json
{
  "graphs": {
    "db_agent": "./deployments/db_agent_graph.py:graph",
    "supervisor_hitl_sql": "./deployments/supervisor_hitl_sql_agent_graph.py:graph"
  }
}
```