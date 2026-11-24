"""Local calculations for Module 7: what an evaluator flags, what a filter selects, what a sample misses.

Module 7 teaches monitoring on a fixed data set, the "seed" (`utils/trace_seeding.py`): one synthetic
day of TechHub production traces. The helpers in this file answer the lab's questions on that data
with plain Python, so every answer can be computed with no LangSmith key and no network.

Every function here is a calculation on seed data, not the product. There is no local interpreter
for LangSmith's filter language and no simulated alert engine. Where LangSmith has a setting (a
filter string, a sampling rate, an alert window), the helper prints or carries the documented
setting and computes, in ordinary Python, what that setting would select on the seed.

    from utils.trace_seeding import load_seed, root_runs
    from utils.monitoring_local import FILTERS, apply_evaluator, error_windows, sample, select

    seed = load_seed()
    rows = apply_evaluator(perform_eval, root_runs(seed))    # one row per run and feedback key
    select("flagged_wrong_return_window", seed["runs"], rows)  # the runs a routing rule would pick
    sample(root_runs(seed), rate=0.25)                        # a fixed, reproducible 25% draw
    error_windows(seed)                                       # errors per 5-minute window

Standard library only. Nothing here calls a model, LangSmith or the network.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable

from utils import trace_seeding as ts

# The feedback key the Section 1 evaluator writes. True (or 1) means a problem was found.
WRONG_RETURN_WINDOW_KEY = "wrong_return_window"

DEFAULT_ALERT_WINDOW_MINUTES = 5


def _runs_of(seed_or_runs) -> list[dict]:
    return seed_or_runs["runs"] if isinstance(seed_or_runs, dict) else list(seed_or_runs)


def _parse(value) -> datetime:
    return value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))


# ---------------------------------------------------------------------------------------------
# Running a code evaluator over runs
# ---------------------------------------------------------------------------------------------


def apply_evaluator(perform_eval: Callable, runs) -> list[dict]:
    """Call a code evaluator once per run and return its scores as rows.

    A calculation on seed data, not the product: LangSmith calls a code evaluator as
    `perform_eval(run)` for each run that passes the evaluator's filter and sampling rate, and stores
    every key of the returned dictionary as feedback on that run. This function makes the same call
    for every run it is given and returns one row per run and feedback key:

        {"run_id": ..., "trace_id": ..., "trace_key": "t-0042", "start_time": ..., "key": "wrong_return_window", "score": True}

    Pass root runs (`utils.trace_seeding.root_runs(seed)`). In the lab the evaluator is attached to
    root runs only: a specialist's run inside a trace carries the same question and reply, so
    scoring every run would count one wrong answer several times. If `runs` is a whole seed
    dictionary, its root runs are used.

    The evaluator's own errors are not hidden: an exception is re-raised with a note naming the
    trace, and a return value that is not a dictionary raises `TypeError`.
    """
    targets = ts.root_runs(runs) if isinstance(runs, dict) else list(runs)
    rows: list[dict] = []
    for run in targets:
        key = _trace_key_or_id(run)
        try:
            result = perform_eval(run)
        except Exception as exc:
            exc.add_note(f"(raised by the evaluator on trace {key})")
            raise
        if not isinstance(result, dict):
            raise TypeError(
                f"The evaluator returned {type(result).__name__} for trace {key}. A code evaluator returns a "
                'dictionary of feedback key to score, for example {"wrong_return_window": True}.'
            )
        for feedback_key, score in result.items():
            rows.append({"run_id": run.get("id"), "trace_id": run.get("trace_id"), "trace_key": key,
                         "start_time": run.get("start_time"), "key": feedback_key, "score": score})
    return rows


def _trace_key_or_id(run: dict) -> str:
    try:
        return ts.trace_key(run)
    except (KeyError, TypeError):
        return str(run.get("id")) if isinstance(run, dict) else repr(run)


def _is_flagged(score) -> bool:
    """A score counts as flagged when it is True or a number above 0.5 (the routing filter's `gt(feedback_score, 0.5)`)."""
    if isinstance(score, bool):
        return score
    return isinstance(score, (int, float)) and score > 0.5


def flagged_trace_keys(rows: Iterable[dict], key: str = WRONG_RETURN_WINDOW_KEY) -> list[str]:
    """The trace keys of the rows from `apply_evaluator` whose score for `key` is True (or above 0.5), sorted.

    A calculation on seed data, not the product.
    """
    return sorted({row["trace_key"] for row in rows if row["key"] == key and _is_flagged(row["score"])})


def feedback_by_run(rows: Iterable[dict] | None) -> dict[str, dict[str, Any]]:
    """Run id -> {feedback key: score}, from rows that have `run_id`, `key` and `score`.

    Both kinds of rows in the module have that shape: the rows `apply_evaluator` returns and the
    seeded user scores in `seed["feedback"]`. A calculation on seed data, not the product.
    """
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows or []:
        grouped.setdefault(row["run_id"], {})[row["key"]] = row["score"]
    return grouped


# ---------------------------------------------------------------------------------------------
# Filters: the documented string, and a Python predicate that selects the same runs on the seed
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class LocalFilter:
    """A LangSmith filter string paired with a Python predicate for the seed.

    `filter` is the string to paste into LangSmith or send to its API, in the documented filter
    syntax. `predicate(run, feedback)` says whether one seed run matches: `run` is a run dictionary
    and `feedback` is that run's `{feedback key: score}` (empty when it has none). The predicate
    is a calculation on seed data, not the product: it is written by hand for this one string and
    does not interpret the filter language. `source` says where the string's syntax is documented.
    """

    filter: str
    meaning: str
    predicate: Callable[[dict, dict], bool]
    source: str


def _is_root(run: dict) -> bool:
    return run.get("parent_run_id") is None


def _metadata(run: dict) -> dict:
    return (run.get("extra") or {}).get("metadata") or {}


_QUERY_SYNTAX = "https://docs.langchain.com/langsmith/trace-query-syntax"
_IS_ROOT_NOTE = (
    "`eq(is_root, true)` is the filter in the documentation's own configuration examples (for example the "
    "Insights configuration file on https://docs.langchain.com/langsmith/langsmith-cli#manage-insights) and in "
    f"this repo's Module 5; the field table on {_QUERY_SYNTAX} does not list `is_root`."
)

# Design constants: the strings in the table of Section 1 (PRD section 7, cells 15, 18 and 25) and the
# two tag filters of the keyed helpers. `utils/trace_upload.py` and `utils/monitoring_rest.py` send
# these strings unchanged; a unit test compares them.
FILTERS: dict[str, LocalFilter] = {
    "root_runs": LocalFilter(
        filter="eq(is_root, true)",
        meaning="Every root run: one per trace, so one per customer turn.",
        predicate=lambda run, feedback: _is_root(run),
        source=_IS_ROOT_NOTE,
    ),
    "support_agent_root_runs": LocalFilter(
        filter=f'and(eq(is_root, true), eq(name, "{ts.ROOT_RUN_NAME}"))',
        meaning="Root runs of the deep support agent, by run name. In the UI: Run Name is deep_support_agent.",
        predicate=lambda run, feedback: _is_root(run) and run.get("name") == ts.ROOT_RUN_NAME,
        source=f"{_QUERY_SYNTAX} (`eq(name, ...)`). {_IS_ROOT_NOTE}",
    ),
    "root_runs_on_1_5_0": LocalFilter(
        filter=f'and(eq(is_root, true), eq(metadata_key, "app_version"), eq(metadata_value, "{ts.NEW_VERSION}"))',
        meaning="Root runs of release 1.5.0, by the metadata key app_version.",
        predicate=lambda run, feedback: _is_root(run) and _metadata(run).get("app_version") == ts.NEW_VERSION,
        source=f"{_QUERY_SYNTAX} (`and(eq(metadata_key, ...), eq(metadata_value, ...))`). {_IS_ROOT_NOTE}",
    ),
    "policy_specialist_runs": LocalFilter(
        filter='eq(name, "product-policy-specialist")',
        meaning="The product-policy-specialist's run inside a trace (a child run, not a root run).",
        predicate=lambda run, feedback: run.get("name") == "product-policy-specialist",
        source=f"{_QUERY_SYNTAX} (`eq(name, ...)`).",
    ),
    "flagged_wrong_return_window": LocalFilter(
        filter=f'and(eq(is_root, true), eq(feedback_key, "{WRONG_RETURN_WINDOW_KEY}"), gt(feedback_score, 0.5))',
        meaning="Root runs the evaluator scored wrong_return_window = 1: the runs to route to an annotation queue.",
        predicate=lambda run, feedback: _is_root(run) and _is_flagged(feedback.get(WRONG_RETURN_WINDOW_KEY)),
        source=f"{_QUERY_SYNTAX} (`and(eq(feedback_key, ...), lt(feedback_score, ...))`, with the comparator `gt`). {_IS_ROOT_NOTE}",
    ),
    "seeded_runs": LocalFilter(
        filter=f'has(tags, "{ts.SEED_TAG}")',
        meaning="Every run of the seeded day (all carry the tag seed:m7). The uploader uses it to see whether the seed is already there.",
        predicate=lambda run, feedback: ts.SEED_TAG in (run.get("tags") or []),
        source=f"{_QUERY_SYNTAX} (`has(tags, ...)`).",
    ),
    "live_runs": LocalFilter(
        filter='has(tags, "live:m7")',
        meaning="The handful of fresh traces the lab sends with a key (tag live:m7). None of them is in the seed.",
        predicate=lambda run, feedback: "live:m7" in (run.get("tags") or []),
        source=f"{_QUERY_SYNTAX} (`has(tags, ...)`).",
    ),
}


def select(name: str, runs, feedback_rows: Iterable[dict] | None = None) -> list[dict]:
    """The runs that the filter `FILTERS[name]` selects, in the order given.

    A calculation on seed data, not the product: it applies the Python predicate that is paired
    with the filter string, it does not send the string anywhere. `runs` is a list of runs or a
    whole seed dictionary (then all its runs are considered, child runs included, as in a project).
    `feedback_rows` supplies the feedback a filter on `feedback_key` needs: the rows from
    `apply_evaluator`, the seed's `feedback` list, or both added together.
    """
    if name not in FILTERS:
        raise KeyError(f"No filter named {name!r}. Known names: {', '.join(FILTERS)}.")
    predicate = FILTERS[name].predicate
    feedback = feedback_by_run(feedback_rows)
    return [run for run in _runs_of(runs) if predicate(run, feedback.get(run.get("id"), {}))]


# ---------------------------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------------------------


def sample(runs, rate: float = ts.SAMPLING_RATE, seed: int = ts.SAMPLING_SEED) -> list[dict]:
    """A reproducible sample of `round(rate * len(runs))` runs. The same arguments always give the same runs.

    A calculation on seed data, not the product: LangSmith decides for each run on its own whether
    to evaluate it, so a sampling rate of 0.25 scores about a quarter of the runs, a different
    quarter every time and not exactly a quarter. This helper draws a fixed number with a fixed
    random seed so that the exercise has one answer. Change `seed` to see how much the number of
    caught wrong answers moves from draw to draw.

    The draw is `utils.trace_seeding.sample_runs`, the function the answer key was computed with.
    It orders the runs by trace key first, so it does not depend on run ids or timestamps.
    """
    return ts.sample_runs(list(runs), rate, seed)


# ---------------------------------------------------------------------------------------------
# Errors per time window
# ---------------------------------------------------------------------------------------------


def _densest(times: list[datetime], seconds: float) -> tuple[int, int]:
    """(largest number of `times` inside any span of `seconds`, index of the first one). `times` is sorted."""
    best_count, best_first = 0, 0
    for first, start in enumerate(times):
        count = sum(1 for moment in times[first:] if (moment - start).total_seconds() <= seconds)
        if count > best_count:
            best_count, best_first = count, first
    return best_count, best_first


def error_windows(seed_or_runs, minutes: int = DEFAULT_ALERT_WINDOW_MINUTES) -> dict:
    """Where the errored root runs fall in time, and which alert threshold the quiet hours cannot reach.

    A calculation on seed data, not the product. An alert in LangSmith counts a metric over an
    aggregation window (5 or 15 minutes) and fires when the count crosses a threshold; how the
    product aligns its windows and how often it evaluates them is not documented. This function
    therefore reports two views of the same errors:

    - `windows`: the count in each clock-aligned window of `minutes` minutes that has at least one
      error (for a chart), and
    - the largest count inside any span of `minutes` minutes wherever it starts, which is the
      number that matters for a threshold because it holds for every alignment.

    An error is a root run with `error` set; its time is the run's start time. The "burst" is the
    largest group of errors that fits into one span of `minutes` minutes (the earliest such group
    if two are equally large), and the "background" is every other error.

    Pass a whole seed (or all its runs) so that the failing tool can be named: it is read from the
    errored tool run inside each trace. With root runs only, `failing_tool` is `None`.

    Returns a dictionary:

        minutes                   the window length used
        errors                    one row per errored root run, oldest first:
                                  {"trace_key", "start_time" (datetime), "error", "failing_tool", "in_burst"}
        windows                   [{"start": datetime, "count": int}, ...], oldest first
        max_in_any_window         largest number of errors inside any span of `minutes` minutes
        burst                     {"errors", "span_seconds", "first", "last", "failing_tools"}
        background                {"errors", "max_in_any_window"}
        smallest_safe_threshold   background["max_in_any_window"] + 1: the smallest threshold that
                                  the background errors can never reach
    """
    runs = _runs_of(seed_or_runs)
    by_trace = ts.runs_by_trace(runs)
    failed = [run for run in ts.root_runs(runs) if run.get("error")]
    times = [_parse(run["start_time"]) for run in failed]
    span = minutes * 60

    count, first = _densest(times, span)
    in_burst = set(range(first, first + count))
    background_times = [moment for index, moment in enumerate(times) if index not in in_burst]
    background_max = _densest(background_times, span)[0]

    def failing_tool(run: dict) -> str | None:
        members = by_trace.get(ts.trace_key(run), [])
        return next((r["name"] for r in members if r["run_type"] == "tool" and r.get("error") and r["name"] != "task"), None)

    errors = [
        {"trace_key": ts.trace_key(run), "start_time": times[index], "error": run["error"],
         "failing_tool": failing_tool(run), "in_burst": index in in_burst}
        for index, run in enumerate(failed)
    ]

    buckets: dict[datetime, int] = {}
    for moment in times:
        epoch = moment.timestamp()
        start = datetime.fromtimestamp(epoch - epoch % span, tz=timezone.utc)
        buckets[start] = buckets.get(start, 0) + 1

    burst_rows = [row for row in errors if row["in_burst"]]
    return {
        "minutes": minutes,
        "errors": errors,
        "windows": [{"start": start, "count": buckets[start]} for start in sorted(buckets)],
        "max_in_any_window": count,
        "burst": {
            "errors": len(burst_rows),
            "span_seconds": (burst_rows[-1]["start_time"] - burst_rows[0]["start_time"]).total_seconds() if burst_rows else 0.0,
            "first": burst_rows[0]["start_time"] if burst_rows else None,
            "last": burst_rows[-1]["start_time"] if burst_rows else None,
            "failing_tools": sorted({row["failing_tool"] for row in burst_rows if row["failing_tool"]}),
        },
        "background": {"errors": len(errors) - len(burst_rows), "max_in_any_window": background_max},
        "smallest_safe_threshold": background_max + 1,
    }


def error_bars(result: dict, now: datetime | None = None) -> list[str]:
    """The `windows` of an `error_windows` result as text lines, one bar per window that has an error.

    A calculation on seed data, not the product (this is not LangSmith's alert preview). Each line
    gives the window's start in UTC, how long ago that was, a bar and the count:

        2026-11-19 08:05 UTC   55 min ago  ######## 8

    The module has no plotting library, so charts are text.
    """
    now = now or datetime.now(timezone.utc)
    lines = []
    for window in result["windows"]:
        ago = now - window["start"]
        if ago < timedelta(hours=2):
            age = f"{int(ago.total_seconds() // 60):>4} min ago"
        else:
            age = f"{ago.total_seconds() / 3600:>5.1f} h ago "
        lines.append(f"{window['start']:%Y-%m-%d %H:%M} UTC  {age}  {'#' * window['count']} {window['count']}")
    return lines


# ---------------------------------------------------------------------------------------------
# Cost
# ---------------------------------------------------------------------------------------------


def cost_of(run: dict, price_table: dict | None = None) -> float:
    """Estimated cost in US dollars of one run: its token counts times a price per 1 million tokens.

    A calculation on seed data, not the product: LangSmith computes cost from its own model price
    map, and whether that map prices the model names in the seed is not verified. `price_table`
    maps a model name to `{"input": <dollars per 1M input tokens>, "output": <dollars per 1M output tokens>}`.
    The default is the illustrative table stored in the seed (`utils.trace_seeding.ILLUSTRATIVE_PRICES_PER_1M`),
    round numbers invented for the lab, not a provider's price list. Only LLM runs cost anything; every
    other run returns 0.0, so summing over all runs of a trace gives the trace's cost.
    """
    return ts.run_cost(run, price_table)


def spend_by(seed_or_runs, metadata_key: str = "customer_id", price_table: dict | None = None) -> dict[str, float]:
    """Estimated spend per value of a metadata key (for example per `customer_id`), largest first.

    A calculation on seed data, not the product: it sums `cost_of` over the runs that carry each
    value of `metadata_key`. Every run of a seeded trace carries the caller's metadata, so the
    LLM runs inside a trace are counted for the customer who asked.
    """
    totals: dict[str, float] = {}
    for run in _runs_of(seed_or_runs):
        value = _metadata(run).get(metadata_key)
        if value is not None and run.get("run_type") == "llm":
            totals[value] = totals.get(value, 0.0) + cost_of(run, price_table)
    return dict(sorted(totals.items(), key=lambda item: (-item[1], str(item[0]))))
