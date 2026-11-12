"""
Evaluators for TechHub customer support agent evaluation.

This module contains evaluators developed in Module 2, Section 1 for measuring
agent performance on our baseline dataset. These evaluators help us quantify
how well our agent performs and identify areas for improvement.
"""

from langchain.chat_models import init_chat_model
from langsmith.schemas import Run
from pydantic import BaseModel, Field

from config import DEFAULT_MODEL

# ============================================================================
# CORRECTNESS EVALUATOR (LLM-as-Judge)
# ============================================================================
# This evaluator uses an LLM to determine if the agent's output is "correct"
# by comparing it against a reference output (ground truth).
# ============================================================================

CORRECTNESS_PROMPT = """You are an expert data labeler evaluating model outputs for correctness.

Your task is to assign a boolean score based on the following rubric:

<Rubric>
  A correct answer (True):
  - Provides accurate and complete information
  - Contains no factual errors
  - Addresses all parts of the question
  - Is logically consistent
</Rubric>

<Instructions>
  - Carefully read the input and output
  - Compare the output to the reference_output
  - Check for factual accuracy and completeness
  - Focus on correctness of information rather than style or verbosity differences
  - Return a boolean score (True if correct, False if incorrect), not a string
</Instructions>

<Note>
- It's ok if the ouput provides additional information that is not directly included in the reference output
- The output is just the final output from an agent invocation, so it will not include all the intermediate steps or tool calls, this is ok.
</Note>

<input>
{inputs}
</input>

<output>
{outputs}
</output>

<reference_outputs>
{reference_outputs}
</reference_outputs>
"""


class CorrectnessScore(BaseModel):
    """Structured output schema for correctness evaluation."""

    reasoning: str = Field(..., description="A concise reasoning for the score")
    score: bool = Field(
        ..., description="True if the output is correct, False if incorrect."
    )


# Create a structured LLM for correctness evaluation
_correctness_evaluator_llm = init_chat_model(
    model=DEFAULT_MODEL
).with_structured_output(CorrectnessScore)


def correctness_evaluator(inputs: dict, outputs: dict, reference_outputs: dict) -> dict:
    """Evaluate the correctness of the output against the reference output.

    This evaluator uses LLM-as-a-Judge to compare the agent's output against
    a ground truth reference output. It returns a boolean score (True/False)
    indicating whether the output is correct.

    Args:
        inputs: The input to the system (e.g., customer question)
        outputs: The system's actual output (e.g., agent's response)
        reference_outputs: The expected/ground truth output

    Returns:
        Dictionary with:
        - key: "correctness"
        - score: Boolean (True if correct, False if incorrect)
        - comment: Reasoning for the score

    Example:
        >>> result = correctness_evaluator(
        ...     inputs={"messages": [{"role": "user", "content": "What's 2+2?"}]},
        ...     outputs={"messages": [{"role": "assistant", "content": "4"}]},
        ...     reference_outputs={"messages": [{"role": "assistant", "content": "The answer is 4"}]}
        ... )
        >>> result["score"]
        True
    """
    formatted_prompt = CORRECTNESS_PROMPT.format(
        inputs=inputs, outputs=outputs, reference_outputs=reference_outputs
    )

    eval_result = _correctness_evaluator_llm.invoke(formatted_prompt)

    return {
        "key": "correctness",
        "score": eval_result.score,
        "comment": eval_result.reasoning,
    }


# ============================================================================
# TOOL CALL COUNTER EVALUATOR (Trace-Based)
# ============================================================================
# This evaluator counts the total number of tool calls made during agent
# execution. It doesn't require a reference output - instead it analyzes
# the execution trace (Run object) from LangSmith.
#
# Why track this? Fewer tool calls often means more efficient execution.
# This helps identify patterns like:
# - Sequential chains (get_order_items → get_product_info × N)
# - Missing capabilities (can't aggregate, forcing multiple queries)
# ============================================================================


def count_total_tool_calls_evaluator(run: Run) -> dict:
    """Count total tool calls across the entire run (supervisor + sub-agents).

    This evaluator recursively traverses the execution trace to count all
    tool invocations. It's useful for identifying inefficient patterns and
    measuring whether improvements actually reduce tool usage.

    Args:
        run: LangSmith Run object containing the full execution trace

    Returns:
        Dictionary with:
        - key: "total_tool_calls"
        - score: Integer count of tool invocations

    Example:
        >>> # After running agent
        >>> full_run = client.read_run(run.id, load_child_runs=True)
        >>> result = count_total_tool_calls_evaluator(full_run)
        >>> result["score"]  # e.g., 7
        7

    Note:
        This evaluator works by examining the Run object's metadata,
        not the inputs/outputs. It counts all runs where run_type == "tool".
    """

    def traverse_runs(run_obj: Run) -> int:
        """Recursively count all tool-type runs in the execution tree."""
        count = 0

        # Count this run if it's a tool execution
        if run_obj.run_type == "tool":
            count = 1

        # Recursively count child runs
        if hasattr(run_obj, "child_runs") and run_obj.child_runs:
            for child in run_obj.child_runs:
                count += traverse_runs(child)

        return count

    total_tools = traverse_runs(run)

    return {"key": "total_tool_calls", "score": total_tools}


# ============================================================================
# ORDER-SPECIALIST TOOL CALLS EVALUATOR (Module 5)
# ============================================================================
# The deep agent delegates order questions to its `order-specialist` subagent,
# which appears in the trace as a run named "order-specialist" under the main
# agent's `task` tool. Total tool calls also counts those delegations and the
# product-policy specialist's searches; this counts only the order specialist's
# own tool calls, which is what changes when its tools change (Module 5 Section 2).
# ============================================================================


def order_specialist_tool_calls_evaluator(run: Run) -> dict:
    """Count tool calls made inside the deep agent's order-specialist subagent.

    Args:
        run: LangSmith Run object containing the full execution trace

    Returns:
        Dictionary with key "order_specialist_tool_calls" and the integer count.
    """

    def traverse_runs(run_obj: Run, inside: bool = False) -> int:
        """Count tool runs that have an ancestor named "order-specialist"."""
        inside = inside or run_obj.name == "order-specialist"
        count = 1 if inside and run_obj.run_type == "tool" else 0
        for child in getattr(run_obj, "child_runs", None) or []:
            count += traverse_runs(child, inside)
        return count

    return {"key": "order_specialist_tool_calls", "score": traverse_runs(run)}
