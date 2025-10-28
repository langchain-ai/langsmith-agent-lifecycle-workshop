"""
Shared agent implementations for the AI Engineering Lifecycle workshop.

This module contains reusable agent configurations and implementations
used across multiple workshop modules.
"""

from agents.db_agent import create_db_agent
from agents.rag_agent import create_rag_agent

__all__ = [
    "create_db_agent",
    "create_rag_agent",
]
