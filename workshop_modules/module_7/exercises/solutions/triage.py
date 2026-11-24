"""Reference solution for `exercises/triage.py` (Module 7, Section 3).

Check it from the repository root:

    M7_EXERCISES_DIR=workshop_modules/module_7/exercises/solutions uv run python workshop_modules/module_7/exercises/check.py s3_triage
"""

ACTIONS = ("apply_fix_and_add_examples", "review_pull_request", "save_for_later", "close_incorrectly_flagged")


def next_action(issue):
    """Return the next action for one issue: one of the four codes in `ACTIONS`."""
    # A finding is an observation: the answers are correct, so there is nothing to apply or review.
    if issue.get("type") == "finding":
        return "save_for_later"
    # A fix is in flight when the issue is being fixed and at least one fix has been opened.
    if issue.get("status") == "fixing" and issue.get("fixes"):
        return "review_pull_request"
    # Otherwise the issue is a real problem that nobody has started on. Severity sets the order
    # of work, not the action. "close_incorrectly_flagged" is a person's call after reading the
    # evidence; no field of an issue says that the agent behaved correctly.
    return "apply_fix_and_add_examples"
