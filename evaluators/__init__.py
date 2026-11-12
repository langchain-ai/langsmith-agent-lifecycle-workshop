"""
Evaluators for measuring TechHub agent performance.

This module contains evaluators developed in Module 2 for quantifying
agent performance on customer support tasks:

- correctness_evaluator: LLM-as-judge comparing outputs to ground truth
- count_total_tool_calls_evaluator: Counts tool invocations for efficiency tracking
- order_specialist_tool_calls_evaluator: Counts the deep agent's order-specialist tool calls (Module 5)

These evaluators are built inline in Module 2, Section 1 for pedagogical value,
then packaged here for reuse in subsequent sections and modules.
"""

from evaluators.evaluators import (
    correctness_evaluator,
    count_total_tool_calls_evaluator,
    order_specialist_tool_calls_evaluator,
)

__all__ = [
    "correctness_evaluator",
    "count_total_tool_calls_evaluator",
    "order_specialist_tool_calls_evaluator",
]
