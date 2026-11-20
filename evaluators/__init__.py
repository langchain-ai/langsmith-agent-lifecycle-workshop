"""
Evaluators for measuring TechHub agent performance.

This module contains evaluators developed in Module 2 for quantifying
agent performance on customer support tasks:

- correctness_evaluator: LLM-as-judge comparing outputs to ground truth
- count_total_tool_calls_evaluator: Counts tool invocations for efficiency tracking
- order_specialist_tool_calls_evaluator: Counts the deep agent's order-specialist tool calls (Module 5)
- deep_agent_correctness_evaluator: correctness_evaluator aligned on the deep agent's answers (Module 5 Section 3)
- jev_correctness_evaluator: the aligned rubric as Jev decision-model questions (Module 5 Section 4)
- wrong_return_window_evaluator: online code evaluator that flags a 30-day return window given for an opened or used product (Module 7 Section 1)
- WRONG_RETURN_WINDOW_SOURCE: the source text of that function, to paste into a LangSmith Code Evaluator

These evaluators are built inline in Module 2, Section 1 for pedagogical value,
then packaged here for reuse in subsequent sections and modules.

The online evaluator lives in `evaluators/online_evaluators.py`, where LangSmith's contract
requires the name `perform_eval(run, example=None)`. It is exported here under a specific
name, so the package does not hand out a generic one.
"""

from evaluators.evaluators import (
    correctness_evaluator,
    count_total_tool_calls_evaluator,
    deep_agent_correctness_evaluator,
    jev_correctness_evaluator,
    order_specialist_tool_calls_evaluator,
)
from evaluators.online_evaluators import WRONG_RETURN_WINDOW_SOURCE
from evaluators.online_evaluators import perform_eval as wrong_return_window_evaluator

__all__ = [
    "WRONG_RETURN_WINDOW_SOURCE",
    "correctness_evaluator",
    "count_total_tool_calls_evaluator",
    "deep_agent_correctness_evaluator",
    "jev_correctness_evaluator",
    "order_specialist_tool_calls_evaluator",
    "wrong_return_window_evaluator",
]
