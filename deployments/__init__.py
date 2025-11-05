"""
Deployment-ready graph instances for LangSmith deployment.

This module contains module-level graph instances that can be referenced
directly in langgraph.json for deployment. These are distinct from the
factory functions in agents/ which provide flexibility for development
and workshop pedagogy.

Deployment pattern:
- Factory functions (agents/) → Parameterized, flexible for development
- Graph instances (deployments/) → Fixed configuration for deployment

Available deployments:

Module 1 (Baseline):
- db_agent_graph: Database agent with rigid tools
- docs_agent_graph: Documents agent for searching product docs and policies
- supervisor_agent_graph: Supervisor agent coordinating between specialists
- supervisor_hitl_agent_graph: Complete verification + supervisor agent with HITL

Module 2 (Improved):
- sql_agent_graph: SQL agent with flexible query generation
- supervisor_hitl_sql_agent_graph: Verification + supervisor using SQL agent
"""

__all__ = [
    "db_agent_graph",
    "docs_agent_graph",
    "sql_agent_graph",
    "supervisor_agent_graph",
    "supervisor_hitl_agent_graph",
    "supervisor_hitl_sql_agent_graph",
]
