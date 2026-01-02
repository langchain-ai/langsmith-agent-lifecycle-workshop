# Agents

Reusable agent factory functions for the TechHub customer support system. Each agent is built using LangChain's `create_agent()` and configured with specific tools and prompts for different capabilities.

## Available Agents

| Agent | Description | Used In |
|-------|-------------|---------|
| **Database Agent** (`db_agent.py`) | Queries structured data using rigid tools (order status, product info) | Module 1 |
| **SQL Agent** (`sql_agent.py`) | Flexible query generation with SQL - improved version of DB agent | Module 2 |
| **Documents Agent** (`docs_agent.py`) | Searches product docs and policies using RAG/vector search | Module 1 |
| **Supervisor Agent** (`supervisor_agent.py`) | Coordinates DB and Docs agents to handle complex queries | Module 1 |
| **Supervisor HITL Agent** (`supervisor_hitl_agent.py`) | Full system with customer verification and human-in-the-loop | Module 1 |

## Quick Start

All agents follow the same simple factory pattern:

```python
from agents import create_db_agent, create_docs_agent, create_supervisor_agent

# Create agents with sensible defaults
db_agent = create_db_agent()
docs_agent = create_docs_agent()
supervisor = create_supervisor_agent(db_agent, docs_agent)

# Use like any LangGraph graph
result = supervisor.invoke({"messages": [{"role": "user", "content": "..."}]})
```

## Configuration

All agents use workshop-wide configuration from the root `config.py`:

```python
# .env file
WORKSHOP_MODEL="anthropic:claude-haiku-4-5"

# Automatically used by all agents
db_agent = create_db_agent()  # Uses model from config
```

## Advanced Usage

### Custom State Schema

Pass a custom state schema to share data between graphs:

```python
from langgraph.graph import MessagesState

class CustomState(MessagesState):
    customer_id: str

agent = create_db_agent(state_schema=CustomState)
```

### Additional Tools

Extend agents with extra tools:

```python
from tools import get_customer_orders

agent = create_db_agent(additional_tools=[get_customer_orders])
```

### Override Defaults

Customize model or prompt for specific needs:

```python
agent = create_db_agent(
    model="anthropic:claude-sonnet-4",
    system_prompt="Custom instructions..."
)
```

### Deployment Mode

Disable checkpointers for production (state managed by LangGraph Cloud):

```python
agent = create_db_agent(use_checkpointer=False)
```

See the `deployments/` directory for production-ready configurations.

## Implementation Details

Each agent file follows a consistent pattern:

1. **Module-level constants** - System prompts and base tools defined at the top
2. **Factory function** - `create_*_agent()` with sensible defaults and optional overrides
3. **Returns a compiled graph** - Ready to use with `.invoke()` or `.stream()`

This pattern provides simplicity by default while allowing customization when needed. See individual agent files for specific implementations.
