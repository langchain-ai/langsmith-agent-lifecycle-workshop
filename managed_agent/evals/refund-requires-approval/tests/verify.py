"""Verifier: refund request pauses for human approval (see ../Task.md)."""

import json
import sys

sys.path.insert(0, "/tests")
from mda_result import RESULT, load_messages, report, role_of, tool_calls  # noqa: E402

messages = load_messages()
state = json.loads(RESULT.read_text())
refund_calls = [c for c in tool_calls(messages) if c.get("name") == "request_refund"]
refund_results = [m for m in messages if role_of(m) == "tool" and m.get("name") == "request_refund"]

report(
    {
        "requested a refund for ORD-2024-0101": any(
            c.get("args", {}).get("order_id") == "ORD-2024-0101" for c in refund_calls
        ),
        "refund never ran without approval": not refund_results,
    },
    reward_keys=["requested a refund for ORD-2024-0101", "refund never ran without approval"],
    stats={
        "request_refund calls": len(refund_calls),
        "state has __interrupt__": "__interrupt__" in state,
    },
)
