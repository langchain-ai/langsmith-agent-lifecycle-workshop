"""
Supervisor HITL + SQL Agent - Deployment Configuration

This module provides a deployment-ready instance of the supervisor HITL agent
using the improved SQL agent instead of the rigid tool-based db_agent.

This demonstrates eval-driven development and composition:
- Module 1, Section 4: Baseline supervisor HITL agent with rigid DB tools
- Module 2, Section 2: Improved SQL agent that generates flexible queries
- This deployment: Compose them together to get best of both worlds

Architecture:
- Query classification → Customer verification (HITL) → Supervisor agent
- Supervisor routes to: SQL agent (flexible queries) + Docs agent (RAG)

For deployment, this module provides a fixed configuration:
    langgraph.json → "./deployments/supervisor_hitl_sql_agent_graph.py:graph"

Note: use_checkpointer=False because LangGraph API provides
managed persistence automatically.
"""

from agents.docs_agent import create_docs_agent
from agents.sql_agent import create_sql_agent
from agents.supervisor_hitl_agent import create_supervisor_hitl_agent

# Instantiate improved SQL agent for deployment
sql_agent = create_sql_agent(
    use_checkpointer=False,
)

# Instantiate docs agent
docs_agent = create_docs_agent(use_checkpointer=False)

# Module-level graph instance for deployment
# Compose supervisor HITL with SQL agent instead of db_agent
graph = create_supervisor_hitl_agent(
    db_agent=sql_agent,
    docs_agent=docs_agent,
    use_checkpointer=False,
)
