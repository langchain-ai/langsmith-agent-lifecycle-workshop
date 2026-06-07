"""Regression tests for cross-customer PII leak via the database_specialist tool.

Verified customer CUST-007 asks about ORD-2025-0003, which belongs to CUST-044.
The supervisor's `database_specialist` tool must (a) forward an AUTHORIZATION
preamble naming CUST-007 to the sub-agent, and (b) redact any rows containing
another customer's CUST-XXX identifier from the sub-agent's response before
returning to the supervisor.
"""

from langchain_core.messages import AIMessage

from agents.supervisor_agent import _redact_other_customer_ids, create_supervisor_agent


class _StubAgent:
    """Stub sub-agent that records the forwarded prompt and returns a canned reply."""

    def __init__(self, reply: str):
        self.reply = reply
        self.last_query: str | None = None

    def invoke(self, payload):
        self.last_query = payload["messages"][-1]["content"]
        return {"messages": [AIMessage(content=self.reply)]}


def _get_db_tool(supervisor):
    for node in supervisor.get_graph().nodes.values():
        data = getattr(node, "data", None)
        tools = getattr(data, "tools_by_name", None) if data is not None else None
        if tools and "database_specialist" in tools:
            return tools["database_specialist"]
    raise AssertionError("database_specialist tool not found on supervisor")


def test_authorization_preamble_is_forwarded_to_sub_agent():
    leaky_reply = (
        "Order ORD-2025-0003 belongs to Ryan Smith (CUST-044), "
        "ryan@example.com, status: shipped."
    )
    db_agent = _StubAgent(reply=leaky_reply)
    docs_agent = _StubAgent(reply="n/a")

    supervisor = create_supervisor_agent(
        db_agent=db_agent, docs_agent=docs_agent, use_checkpointer=False
    )
    db_tool = _get_db_tool(supervisor)

    result = db_tool.invoke(
        {
            "query": "Look up ORD-2025-0003 status",
            "state": {"customer_id": "CUST-007"},
        }
    )

    assert db_agent.last_query is not None
    assert "AUTHORIZATION" in db_agent.last_query
    assert "CUST-007" in db_agent.last_query
    assert "not associated with your account" in db_agent.last_query

    assert "CUST-044" not in result
    assert "Ryan Smith" not in result
    assert "ryan@example.com" not in result


def test_redact_other_customer_ids_strips_leaked_rows():
    text = (
        "order_id,customer_id,name,email\n"
        "ORD-2025-0003,CUST-044,Ryan Smith,ryan@example.com\n"
        "ORD-2025-0010,CUST-007,Jane Doe,jane@example.com"
    )
    redacted = _redact_other_customer_ids(text, "CUST-007")
    assert "CUST-044" not in redacted
    assert "Ryan Smith" not in redacted
    assert "ryan@example.com" not in redacted
    assert "CUST-007" in redacted


def test_redact_other_customer_ids_returns_refusal_when_everything_leaks():
    text = "ORD-2025-0003 belongs to CUST-044 (Ryan Smith)"
    redacted = _redact_other_customer_ids(text, "CUST-007")
    assert "CUST-044" not in redacted
    assert "Ryan Smith" not in redacted
    assert "not associated with your account" in redacted
