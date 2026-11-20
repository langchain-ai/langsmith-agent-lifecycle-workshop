"""Reference solution for `exercises/read_the_report.py` (Module 7, Section 2).

Check it from the repository root:

    M7_EXERCISES_DIR=workshop_modules/module_7/exercises/solutions uv run python workshop_modules/module_7/exercises/check.py s2_report s2_claim
"""


def summarise(report):
    """Return the largest category and the subcategory with the highest error rate (see the exercise file for the keys)."""
    # `parent_id` is what separates the two layers. The `level` number is documented for subcategories only.
    categories = [cluster for cluster in report["clusters"] if cluster["parent_id"] is None]
    subcategories = [cluster for cluster in report["clusters"] if cluster["parent_id"] is not None]

    largest = max(categories, key=lambda cluster: cluster["num_runs"])
    # Every conversation is in exactly one top-level category, so their counts add up to the total.
    total = sum(cluster["num_runs"] for cluster in categories)
    worst = max(subcategories, key=lambda cluster: (cluster.get("stats") or {}).get("error_rate", 0.0))

    return {
        "largest_category": largest["name"],
        "largest_category_conversations": largest["num_runs"],
        "largest_category_share": round(largest["num_runs"] / total, 2),
        "highest_error_rate_subcategory": worst["name"],
        "highest_error_rate": worst["stats"]["error_rate"],
    }


def flagged_in_subcategory(name, seed, labels, perform_eval):
    """Return how many conversations of the subcategory `name` the evaluator `perform_eval` flags."""
    root_by_trace_key = {
        run["extra"]["metadata"]["seed_trace_key"]: run
        for run in seed["runs"]
        if run["parent_run_id"] is None
    }
    flagged = 0
    for conversation in labels["conversations"]:
        if conversation["subcategory"] != name:
            continue
        turns = [root_by_trace_key[key] for key in conversation["trace_keys"]]
        # A conversation counts once, however many of its turns are flagged.
        if any(perform_eval(run)["wrong_return_window"] for run in turns):
            flagged += 1
    return flagged
