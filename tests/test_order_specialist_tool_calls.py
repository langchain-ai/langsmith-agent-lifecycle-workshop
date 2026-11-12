"""order_specialist_tool_calls_evaluator counts only the order specialist's tool calls.

Run: uv run python -m unittest tests.test_order_specialist_tool_calls
"""

import unittest
from types import SimpleNamespace

from evaluators import count_total_tool_calls_evaluator, order_specialist_tool_calls_evaluator


def node(name: str, run_type: str = "chain", *children) -> SimpleNamespace:
    return SimpleNamespace(name=name, run_type=run_type, child_runs=list(children))


# The shape of a real deep-agent trace: main agent -> `task` tool -> specialist subagent -> tools.
TRACE = node(
    "deep_support_agent",
    "chain",
    node("task", "tool", node("order-specialist", "chain", node("get_customer_orders", "tool"), node("get_order_items", "tool"))),
    node("task", "tool", node("product-policy-specialist", "chain", node("search_policy_docs", "tool"))),
)


class OrderSpecialistToolCallsTest(unittest.TestCase):
    def test_counts_only_tools_inside_the_order_specialist(self):
        self.assertEqual(order_specialist_tool_calls_evaluator(TRACE), {"key": "order_specialist_tool_calls", "score": 2})

    def test_total_still_counts_everything(self):
        # 2 `task` delegations + 2 order tools + 1 docs search
        self.assertEqual(count_total_tool_calls_evaluator(TRACE)["score"], 5)

    def test_no_order_specialist_means_zero(self):
        trace = node("deep_support_agent", "chain", node("task", "tool", node("product-policy-specialist", "chain", node("search_policy_docs", "tool"))))
        self.assertEqual(order_specialist_tool_calls_evaluator(trace)["score"], 0)


if __name__ == "__main__":
    unittest.main()
