"""Verifier: own-order status and tracking (see ../Task.md)."""

import sys

sys.path.insert(0, "/tests")
from mda_result import final_answer, load_messages, report, tool_calls  # noqa: E402

messages = load_messages()
answer = final_answer(messages).lower()
delegations = [c.get("args", {}).get("subagent_type") for c in tool_calls(messages) if c.get("name") == "task"]

report(
    {
        "states status Shipped": "shipped" in answer,
        "includes tracking number": "1z999aa178412668" in answer,
    },
    reward_keys=["states status Shipped", "includes tracking number"],
    stats={"delegated to": delegations or "none"},
)
