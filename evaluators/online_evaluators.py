"""
Online evaluators for the TechHub deep support agent (Module 7, Section 1).

An online evaluator scores production traces as they arrive, with no reference answer to compare
against. The one in this file is a LangSmith *code evaluator*: a plain Python function that
receives one run as a dictionary and returns a dictionary of feedback key to score.

- perform_eval: the wrong-return-window check, in the shape LangSmith expects
- WRONG_RETURN_WINDOW_SOURCE: the source text of that function, to paste into a Code Evaluator
  in the LangSmith UI or to send to the API

What it checks. TechHub's Return Policy (`data/documents/policies/return_policy.md`) gives
unopened electronics 30 days from delivery and opened electronics 14 days. The check flags a
root run when the customer says the product was opened or used and the agent's reply gives a
30-day window. It is a heuristic on wording, costs no model call, and does not read the policy:
a reply that mentions both windows, or a customer who uses other words for "opened", is outside
what it can judge.

Polarity. `{"wrong_return_window": True}` means a problem was found. A score of True is not
a pass here.

Attach it to root runs only (in Module 7: a filter on the run name `deep_support_agent`). A
specialist's run inside the trace carries the same question and reply in the same `messages`
shape, so without the filter one wrong answer is scored more than once.

Rules for anything added to this file, because LangSmith runs the function's source on its own:

- The function is named `perform_eval` and takes `(run, example=None)`. The second argument
  is what LangSmith passes when the evaluator is tested against a dataset example.
- Everything the function needs is inside its body: no imports, no module-level helpers or
  constants. `tests/test_online_evaluators.py` compiles the source text alone and compares it
  with the imported function on every root run of the Module 7 seed.
- It reads `run["inputs"]` and `run["outputs"]` as plain dictionaries and never raises: a run
  that failed has no outputs.

The package exports the function as `wrong_return_window_evaluator`, so that
`from evaluators import ...` does not hand out a generic name.

Standard library only. The module imports `inspect` to read the function's source; the function
itself imports nothing.
"""

import inspect


def perform_eval(run, example=None):
    """Flag a reply that gives an opened or used product the 30-day return window.

    TechHub's Return Policy: unopened electronics can be returned within 30 days of delivery,
    opened electronics within 14 days.

    Returns {"wrong_return_window": True} when the customer says the product was opened or
    used and the agent's reply gives a 30-day window, otherwise {"wrong_return_window": False}.
    True means a problem was found.
    """

    def as_message(message):
        # A message is a dictionary. A serialized LangChain message keeps its fields under "kwargs".
        if not isinstance(message, dict):
            return {}
        inner = message.get("kwargs")
        return inner if isinstance(inner, dict) else message

    def text_of(message):
        # Content is a string, or a list of content blocks such as {"type": "text", "text": "..."}.
        content = as_message(message).get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = [block if isinstance(block, str) else block.get("text", "") for block in content if isinstance(block, (str, dict))]
            return " ".join(part for part in parts if isinstance(part, str))
        return ""

    def words_of(text):
        # Lower-case words, split at everything that is not a letter or a digit. Whole words
        # matter: "unopened" and "unused" must not count as "opened" and "used".
        return "".join(ch if ch.isalnum() else " " for ch in text.lower()).split()

    def messages_of(payload):
        # run["outputs"] is None or {} when the run failed, so a missing key is normal.
        messages = payload.get("messages") if isinstance(payload, dict) else None
        return messages if isinstance(messages, list) else []

    if not isinstance(run, dict):
        return {"wrong_return_window": False}
    asked = messages_of(run.get("inputs"))
    answered = messages_of(run.get("outputs"))
    if not asked or not answered:
        return {"wrong_return_window": False}

    # The customer's message is the last one in the inputs. The reply is the last message in the
    # outputs, and only if the agent wrote it: a turn can also end on a tool call or an error.
    question = words_of(text_of(asked[-1]))
    last = as_message(answered[-1])
    if last.get("type", last.get("role")) not in ("ai", "assistant"):
        return {"wrong_return_window": False}
    reply = words_of(text_of(last))

    says_opened = "opened" in question or "used" in question
    gives_30_days = any(a in ("30", "thirty") and b in ("day", "days") for a, b in zip(reply, reply[1:]))
    return {"wrong_return_window": says_opened and gives_30_days}


# The text that is pasted into a LangSmith Code Evaluator (or posted to the API). It is taken
# from the function above, so the copy in the product and the copy under test cannot drift.
WRONG_RETURN_WINDOW_SOURCE = inspect.getsource(perform_eval)
