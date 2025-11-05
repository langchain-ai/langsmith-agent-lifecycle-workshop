"""
Shared agent implementations for the AI Engineering Lifecycle workshop.

This module contains reusable agent configurations and implementations
used across multiple workshop modules.
"""

from agents.db_agent import DB_AGENT_BASE_TOOLS, DB_AGENT_SYSTEM_PROMPT, create_db_agent
from agents.docs_agent import (
    DOCS_AGENT_BASE_TOOLS,
    DOCS_AGENT_SYSTEM_PROMPT,
    create_docs_agent,
)
from agents.sql_agent import SQL_AGENT_BASE_TOOLS, create_sql_agent
from agents.supervisor_agent import (
    SUPERVISOR_AGENT_SYSTEM_PROMPT,
    create_supervisor_agent,
)
from agents.supervisor_hitl_agent import create_supervisor_hitl_agent

__all__ = [
    "create_db_agent",
    "DB_AGENT_SYSTEM_PROMPT",
    "DB_AGENT_BASE_TOOLS",
    "create_docs_agent",
    "DOCS_AGENT_SYSTEM_PROMPT",
    "DOCS_AGENT_BASE_TOOLS",
    "create_sql_agent",
    "SQL_AGENT_BASE_TOOLS",
    "create_supervisor_agent",
    "SUPERVISOR_AGENT_SYSTEM_PROMPT",
    "create_supervisor_hitl_agent",
]
