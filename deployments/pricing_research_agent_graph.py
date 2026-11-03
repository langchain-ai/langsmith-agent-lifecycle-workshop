"""
Pricing Research Agent - Deployment Configuration (Module 4, Section 1: Deep Agents 101)

A deep agent that benchmarks TechHub's catalog prices against current market
prices (provider web search), saves reports, delegates to subagents, remembers
analyst preferences, and proposes price changes for human approval.

For development and workshop purposes, use the factory function:
    from agents import create_pricing_research_agent

    agent = create_pricing_research_agent()

For deployment, this module provides a fixed configuration:
    langgraph.json → "./deployments/pricing_research_agent_graph.py:graph"

Note: use_checkpointer=False because LangGraph API provides managed persistence
and the platform store backs /memories/.
"""

from agents import create_pricing_research_agent

# Module-level graph instance for deployment
graph = create_pricing_research_agent(use_checkpointer=False)
