"""
Deep Support Agent - Deployment Configuration (Module 4)

The TechHub support agent rebuilt on the Deep Agents harness: order and
product/policy subagents, AGENTS.md + skills, per-customer memory, PII
redaction, a customer-scope guard, and a human-approved refund tool.

For development and workshop purposes, use the factory function:
    from agents import create_deep_support_agent, SupportContext

    agent = create_deep_support_agent()

For deployment, this module provides a fixed configuration:
    langgraph.json → "./deployments/deep_support_agent_graph.py:graph"

Pass the verified customer as run context, e.g. {"customer_id": "CUST-003"}.

Note: use_checkpointer=False because LangGraph API provides managed persistence
and the platform store backs /memories/.
"""

from agents import create_deep_support_agent

# Module-level graph instance for deployment
graph = create_deep_support_agent(use_checkpointer=False, with_verifier=True)
