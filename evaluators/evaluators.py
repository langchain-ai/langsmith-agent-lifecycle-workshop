"""
Evaluators for TechHub customer support agent evaluation.

This module contains evaluators developed in Module 2, Section 1 for measuring
agent performance on our baseline dataset. These evaluators help us quantify
how well our agent performs and identify areas for improvement.
"""

from functools import cache

from langchain.chat_models import init_chat_model
from langchain_typesafe import Noul, NoulCriteria
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
# DEEP-AGENT CORRECTNESS EVALUATOR (Module 5, Section 3)
# ============================================================================
# CORRECTNESS_PROMPT aligned to human labels on the deep agent's answers
# (workshop_modules/module_5/golden_set.json): one rule per cause of
# disagreement. The judge model is pinned, because a judge is a measuring
# instrument: change the model and every earlier score means something else.
# Re-run Module 5 Section 3 before changing either.
# ============================================================================

DEEP_AGENT_JUDGE_MODEL = "openai:gpt-5-mini"

RULE_NO_INVENTED_ACTIONS = (
    "  - Does not offer or claim actions the assistant can't take. The assistant can look up orders, products, account "
    "details, and store policies, and can submit a refund request, which a person must approve before anything is refunded. "
    "Claiming that a refund was issued or approved, or offering or claiming to update account data, place or cancel orders, "
    "open returns, send messages, labels, or codes, apply discounts or credits, or contact other teams or systems makes the "
    "output incorrect, even if everything else is right. Offering to look something up, reformat the answer, or submit a "
    "refund request is fine.\n"
    "  - Does not claim the customer asked for something they didn't. Details the assistant looked up, such as the "
    "customer's name or ID, are fine.\n"
)

RULE_ANSWER_WHAT_WAS_ASKED = (
    "  - Answers what the customer asked with the information itself. If the customer asks for their own account "
    "details (for example, their phone number or account type), the output must give them in full: the customer is "
    "already verified, so masking or withholding them doesn't answer the question. If the output says it couldn't "
    "find, check, or verify something the question asks for, and the reference output contains that information, that "
    "part is unanswered and the output is incorrect.\n"
)


def _insert_after(prompt: str, anchor: str, addition: str) -> str:
    if prompt.count(anchor) != 1:
        raise ValueError(f"CORRECTNESS_PROMPT changed: expected one {anchor.strip()!r} line")
    return prompt.replace(anchor, anchor + addition)


DEEP_AGENT_CORRECTNESS_PROMPT = _insert_after(
    _insert_after(CORRECTNESS_PROMPT, "  - Is logically consistent\n", RULE_NO_INVENTED_ACTIONS),
    "  - Addresses all parts of the question\n",
    RULE_ANSWER_WHAT_WAS_ASKED,
)

@cache
def _deep_agent_judge_llm():
    # Created on first use: importing evaluators shouldn't need model credentials
    return init_chat_model(model=DEEP_AGENT_JUDGE_MODEL).with_structured_output(CorrectnessScore)


def deep_agent_correctness_evaluator(inputs: dict, outputs: dict, reference_outputs: dict) -> dict:
    """correctness_evaluator with the rubric aligned on the deep agent's answers (Module 5 Section 3).

    A drop-in replacement: same arguments and the same "correctness" feedback key.
    """
    eval_result = _deep_agent_judge_llm().invoke(
        DEEP_AGENT_CORRECTNESS_PROMPT.format(inputs=inputs, outputs=outputs, reference_outputs=reference_outputs)
    )
    return {"key": "correctness", "score": eval_result.score, "comment": eval_result.reasoning}


# ============================================================================
# JEV CORRECTNESS EVALUATOR (Module 5, Section 4)
# ============================================================================
# The aligned rubric as three typed questions for Jev, TypeSafe's decision model
# (utils/jev.py). The state holds the question, the reference, and the answer;
# the grading criteria live in the questions. An output is correct when every
# question's probability is at least JEV_THRESHOLD, chosen on Module 5 Section 4's
# rule items. Thresholds don't transfer between Jev versions (utils.jev.JEV_MODEL
# is pinned): re-run Section 4 before changing either.
# ============================================================================

JEV_THRESHOLD = 0.15

JEV_RUBRIC_QUESTIONS = {
    "facts_agree": Noul(
        instructions="Do the facts in the agent answer agree with the reference answer, and with each other? Check totals, "
        "counts, prices, dates, items, and any breakdown against its own total.",
        criteria=NoulCriteria(
            true="Every fact the reference answer covers matches, and any breakdown adds up to the total it supports. "
            "Extra details the reference doesn't mention are fine.",
            false="A number, item, or fact contradicts the reference answer, or a breakdown doesn't add up to the total "
            "it supports.",
        ),
    ),
    "answers_question": Noul(
        instructions="Does the agent answer give the customer the information they asked for, for every part of the question?",
        criteria=NoulCriteria(
            true="It states the requested information itself for every part of the question.",
            false="It leaves part unanswered: it masks or withholds the customer's own details, says it couldn't find, "
            "check, or verify something, or answers only part of the question. Declining because the order or data "
            "belongs to a different customer is not leaving it unanswered: when the reference answer also declines, "
            "that is the right answer.",
        ),
    ),
    "possible_actions": Noul(
        instructions="Does the agent answer stay within what the assistant can do: look things up, and submit refund "
        "requests that a person approves?",
        criteria=NoulCriteria(
            true="It only reports what it looked up, offers to look something else up or reformat, or offers to submit "
            "a refund request for a person to approve.",
            false="It claims or offers something else: says a refund was issued, updated account data, opened a return, "
            "sent an email or label, placed or cancelled an order, or contacted another team.",
        ),
    ),
}


def jev_state(question: str, reference: str, output: str) -> str:
    """What Jev reads: the question, the reference, and the answer. No grading instructions."""
    return f"Customer question:\n{question}\n\nReference answer (ground truth):\n{reference}\n\nAgent answer:\n{output}"


def _last_content(messages_dict: dict) -> str:
    return messages_dict["messages"][-1]["content"]


def jev_correctness_evaluator(inputs: dict, outputs: dict, reference_outputs: dict) -> dict:
    """Grade an answer with Jev: one feedback score per rubric question, plus an overall `correctness`.

    `correctness` is 1 when every question's probability is at least JEV_THRESHOLD, and its
    comment holds the lowest probability, so you can see how close the call was.
    """
    from utils.jev import jev_classifier  # imported here: needs the Jev key only when called

    state = jev_state(_last_content(inputs), _last_content(reference_outputs), _last_content(outputs))
    response = jev_classifier().invoke({"state": state, "questions": JEV_RUBRIC_QUESTIONS})
    probabilities = {name: response.nouls[name].noul for name in JEV_RUBRIC_QUESTIONS}
    lowest = min(probabilities.values())
    return {
        "results": [
            *({"key": name, "score": p} for name, p in probabilities.items()),
            {"key": "correctness", "score": int(lowest >= JEV_THRESHOLD), "comment": f"lowest question probability {lowest:.2f}"},
        ]
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
