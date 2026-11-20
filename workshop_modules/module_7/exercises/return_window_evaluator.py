"""Exercise for Module 7, Section 1: the online evaluator that finds the wrong return-window answers.

Release 1.5.0 of the TechHub support agent tells some customers the wrong return window. No error
is raised and the customers are pleased, so neither the error count nor the thumbs-down shows it.
TechHub's Return Policy (`data/documents/policies/return_policy.md`) says:

    Unopened electronics: 30 days from delivery.
    Opened electronics:   14 days from delivery.

Fill in `perform_eval` below, then check it from the repository root:

    uv run python workshop_modules/module_7/exercises/check.py s1_evaluator

This is a LangSmith code evaluator: LangSmith runs the function's source on its own, once per
run, with no access to this repository and no internet. Keep everything the function needs
inside its body: imports (standard library only), constants and helper functions. The check runs
the function inside this file and then once more from its own source alone. It fails if the
function needs anything from the rest of the file (an import, a constant, a helper, a name in a
type annotation), or if it imports this repository or an installed package: those imports work
here and fail in LangSmith.
"""


def perform_eval(run, example=None):
    """Flag a reply that gives an opened or used product the 30-day return window.

    `run` is one root run of the agent as a dictionary. The parts you need:

        run["inputs"]["messages"]    a list of messages; the last one is the customer's message
        run["outputs"]["messages"]   the conversation so far; the last one is the agent's reply
        a message                    a dictionary with "content" (the text) and "type" or "role"

    A run that failed has `error` set and empty outputs (`{}` or `None`). Do not raise on it.

    Return {"wrong_return_window": True} when the customer says the product was opened or used
    and the reply gives a 30-day window, and {"wrong_return_window": False} otherwise.
    True means a problem was found.

    `example` is not used here. LangSmith passes a second argument when the evaluator is tested
    against a dataset example, so the function has to accept one.

    The function has to work when its source is pasted into LangSmith on its own. Put every
    import (standard library only), constant and helper function inside this function's body.
    """
    raise NotImplementedError("perform_eval is not written yet: workshop_modules/module_7/exercises/return_window_evaluator.py")
