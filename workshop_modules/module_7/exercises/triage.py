"""Exercise for Module 7, Section 3: decide the next action for each issue on an Engine issue board.

LangSmith Engine groups failures it finds in a tracing project into issues. A reviewer then decides
what happens to each one. Fill in `next_action` below so that it makes that decision from an
issue's fields, then check it from the repository root:

    uv run python workshop_modules/module_7/exercises/check.py s3_triage

To read the three issues first: `uv run python workshop_modules/module_7/exercises/show_report.py`.
The board shipped with the module is a hand-built sample generated from the seed, not real Engine output.

The check runs this file's imports, assignments, definitions and blocks (`if`, `for`, `try`, `with`).
It does not run a bare call at the top level of the file (a `print`, a test call), so whatever
`next_action` needs belongs in one of those, or inside the function.
"""

ACTIONS = ("apply_fix_and_add_examples", "review_pull_request", "save_for_later", "close_incorrectly_flagged")


def next_action(issue):
    """Return the next action for one issue: one of the four codes in `ACTIONS`.

    `issue` is a dictionary, as in `utils.trace_seeding.load_engine_issues()["issues"]`. The fields
    that matter here:

        "type"           "actionable" (something is wrong and can be fixed) or
                         "finding" (an observation only: nothing is wrong with the answers)
        "status"         "open", "fixing", "watching", "completed" or "ignored"
        "fixes"          a list with one entry per fix that was opened for this issue, each with a
                         "branch" and a "pr_number"; empty when no fix has been opened
        "proposed_fix"   the fix Engine proposes, as text (may be missing)
        "severity"       0 urgent, 1 high, 2 medium, 3 low: the order to work in, not the action

    What each action is for:

        "apply_fix_and_add_examples"   The issue is a real problem and nobody has started on it.
                                       Apply the proposed fix and add offline examples, so a
                                       dataset catches the problem if it comes back.
        "review_pull_request"          A fix is already in flight: the issue is in status "fixing"
                                       and a pull request exists. Review it.
        "save_for_later"               The issue is a finding. There is nothing to fix now; keep
                                       an eye on it.
        "close_incorrectly_flagged"    A person has read the evidence and found that the agent
                                       behaved correctly. No field of an issue says that, so a
                                       rule on fields never chooses this action.
    """
    raise NotImplementedError("next_action is not written yet: workshop_modules/module_7/exercises/triage.py")
