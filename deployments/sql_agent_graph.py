"""
SQL Agent - Deployment Configuration

This module provides a deployment-ready instance of the SQL agent.
The SQL agent generates custom SQL queries to answer database questions,
supporting JOINs, aggregations, and complex filtering.

This represents an improvement over the rigid tool-based db_agent,
demonstrating eval-driven development: baseline evaluation revealed
weaknesses, so we built a flexible SQL agent to address them.

For development and workshop purposes, use the factory function:
    from agents import create_sql_agent

    sql_agent = create_sql_agent()

For deployment, this module provides a fixed configuration:
    langgraph.json → "./deployments/sql_agent_graph.py:graph"

Note: use_checkpointer=False because LangGraph API provides
managed persistence automatically.
"""

from agents.sql_agent import create_sql_agent

# Module-level graph instance for deployment
# use_checkpointer=False because LangGraph API provides managed persistence
graph = create_sql_agent(use_checkpointer=False)
