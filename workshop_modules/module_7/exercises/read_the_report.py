"""Exercise for Module 7, Section 2: read an Insights report, then check one of its claims against the traces.

An Insights report groups conversations into categories and subcategories and gives each group a
few statistics. The grouping is model output; the traces are fact. This exercise has two functions:

- `summarise(report)` reads the two headline facts out of a report.
- `flagged_in_subcategory(name, seed, labels, perform_eval)` counts, for one subcategory, the
  conversations that an online evaluator flags. With the Section 1 evaluator it tells you how many
  "Return window questions" really got the wrong answer.

Fill in both, then check them from the repository root:

    uv run python workshop_modules/module_7/exercises/check.py s2_report s2_claim

To read the report and the issue board first: `uv run python workshop_modules/module_7/exercises/show_report.py`.
The report shipped with the module is a hand-built sample generated from the seed, not real Insights output.

The check runs this file's imports, assignments, definitions and blocks (`if`, `for`, `try`, `with`).
It does not run a bare call at the top level of the file (a `print`, a test call), so whatever
the two functions need belongs in one of those, or inside the function.
"""


def summarise(report):
    """Return the largest category and the subcategory with the highest error rate.

    `report` is a report as a dictionary, the way `utils.trace_seeding.load_insights_report()` returns
    it. `report["clusters"]` is a list with one dictionary per category and per subcategory:

        "name"        the category's or subcategory's name
        "parent_id"   None for a top-level category; the category's "id" for a subcategory
        "num_runs"    the number of conversations in it
        "stats"       {"error_rate": a fraction between 0 and 1, "latency_p50": ..., "cost_p50": ...}

    Every conversation is in exactly one subcategory, and a category's `num_runs` is the sum of its
    subcategories'.

    Return a dictionary with exactly these keys:

        "largest_category"                 name of the top-level category with the most conversations
        "largest_category_conversations"   its `num_runs`
        "largest_category_share"           its share of all conversations, as a fraction rounded to
                                           2 decimal places (0.25 for a quarter)
        "highest_error_rate_subcategory"   name of the subcategory with the highest `stats["error_rate"]`
        "highest_error_rate"               that error rate, as the report gives it
    """
    raise NotImplementedError("summarise is not written yet: workshop_modules/module_7/exercises/read_the_report.py")


def flagged_in_subcategory(name, seed, labels, perform_eval):
    """Return how many conversations of the subcategory `name` the evaluator `perform_eval` flags.

    `seed` is the seed from `utils.trace_seeding.load_seed()`; `seed["runs"]` is a flat list of runs.
    A root run (one per customer turn) has `run["parent_run_id"] is None`, and its trace key is
    `run["extra"]["metadata"]["seed_trace_key"]`, for example "t-0042".

    `labels` is the ground truth from `utils.trace_seeding.load_labels()`, which exists only because
    the data is synthetic. Each item of `labels["conversations"]` has "subcategory" (a name from
    the report) and "trace_keys" (the trace keys of the conversation's turns, one or two).

    `perform_eval` is a code evaluator: `perform_eval(run)` returns {"wrong_return_window": True}
    or {"wrong_return_window": False} for one root run.

    A conversation counts once, however many of its turns are flagged. Return a whole number.
    """
    raise NotImplementedError("flagged_in_subcategory is not written yet: workshop_modules/module_7/exercises/read_the_report.py")
