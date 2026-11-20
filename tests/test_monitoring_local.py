"""utils/monitoring_local.py: the local calculations of Module 7 give the numbers of the answer key.

Every number asserted here is read from `workshop_modules/module_7/data/answers.json` (written by
the seed generator), so this file holds no design constant of its own. Nothing is sent: the
whole module runs inside `refuse_non_local_connects()` and fails if any code tried to reach a
non-local address.

Run: uv run python -m unittest tests.test_monitoring_local
"""

import inspect
import json
import unittest
from datetime import datetime, timedelta, timezone

import utils.monitoring_local as local
import utils.trace_seeding as ts
from evaluators import wrong_return_window_evaluator
from utils.monitoring_local import (
    FILTERS,
    apply_evaluator,
    cost_of,
    error_bars,
    error_windows,
    feedback_by_run,
    flagged_trace_keys,
    sample,
    select,
    spend_by,
)
from utils.offline_capture import refuse_non_local_connects

ANSWERS = json.loads((ts.DATA / ts.ANSWERS_FILE).read_text(encoding="utf-8"))
NON_LOCAL_ATTEMPTS: list = []


def setUpModule():
    global NON_LOCAL_ATTEMPTS, SEED, ROOTS, ROWS
    guard = refuse_non_local_connects()
    NON_LOCAL_ATTEMPTS = guard.__enter__()
    unittest.addModuleCleanup(guard.__exit__, None, None, None)
    SEED = ts.load_seed()
    ROOTS = ts.root_runs(SEED)
    ROWS = apply_evaluator(wrong_return_window_evaluator, ROOTS)


def tearDownModule():
    assert NON_LOCAL_ATTEMPTS == [], f"a test tried to leave the machine: {NON_LOCAL_ATTEMPTS}"


def naive_perform_eval(run, example=None):
    """The naive check of Section 1: every reply that says "30 days"."""
    return {"wrong_return_window": "30 days" in ts.reply_text(run)}


class ApplyEvaluatorTest(unittest.TestCase):
    def test_one_row_per_root_run_and_the_flagged_rows_are_the_answer_key(self):
        self.assertEqual(len(ROWS), len(ROOTS))
        self.assertEqual(len(ROWS), ANSWERS["reference"]["root_runs"])
        self.assertEqual({row["key"] for row in ROWS}, {"wrong_return_window"})
        self.assertEqual(flagged_trace_keys(ROWS), ANSWERS["s1_evaluator"]["flagged_trace_keys"])
        by_id = {run["id"]: run for run in ROOTS}
        for row in ROWS:
            run = by_id[row["run_id"]]
            self.assertEqual((row["trace_id"], row["trace_key"], row["start_time"]), (run["trace_id"], ts.trace_key(run), run["start_time"]))
            self.assertIsInstance(row["score"], bool)

    def test_a_whole_seed_is_evaluated_on_its_root_runs_only(self):
        # Child runs carry the same question and reply; scoring them would count a wrong answer three times.
        self.assertEqual(apply_evaluator(wrong_return_window_evaluator, SEED), ROWS)
        every_run = apply_evaluator(wrong_return_window_evaluator, SEED["runs"])
        self.assertGreater(sum(row["score"] for row in every_run), sum(row["score"] for row in ROWS))

    def test_the_naive_check_flags_the_documented_number(self):
        rows = apply_evaluator(naive_perform_eval, ROOTS)
        self.assertEqual(len(flagged_trace_keys(rows)), ANSWERS["reference"]["s1_evaluator"]["naive_flagged"])
        extra = set(flagged_trace_keys(rows)) - set(flagged_trace_keys(ROWS))
        self.assertEqual(len(extra), ANSWERS["reference"]["s1_evaluator"]["naive_flagged_correct_answers"])

    def test_numeric_scores_count_as_flagged_above_one_half(self):
        rows = [{"trace_key": "t-1", "key": "wrong_return_window", "score": 1},
                {"trace_key": "t-2", "key": "wrong_return_window", "score": 0.5},
                {"trace_key": "t-3", "key": "wrong_return_window", "score": 0},
                {"trace_key": "t-4", "key": "other", "score": True}]
        self.assertEqual(flagged_trace_keys(rows), ["t-1"])
        self.assertEqual(flagged_trace_keys(rows, key="other"), ["t-4"])

    def test_an_evaluator_that_raises_is_not_hidden_and_the_trace_is_named(self):
        def broken(run, example=None):
            return {"wrong_return_window": run["outputs"]["messages"][-1]["content"] == ""}

        with self.assertRaises(KeyError) as caught:
            apply_evaluator(broken, ROOTS)
        self.assertTrue(any("raised by the evaluator on trace t-" in note for note in caught.exception.__notes__))

    def test_a_return_value_that_is_not_a_dictionary_is_a_type_error(self):
        with self.assertRaises(TypeError) as caught:
            apply_evaluator(lambda run: True, ROOTS[:1])
        self.assertIn("dictionary of feedback key to score", str(caught.exception))


class SampleTest(unittest.TestCase):
    def test_the_default_draw_is_reproducible_and_has_the_documented_size(self):
        first, second = sample(ROOTS), sample(ROOTS)
        self.assertEqual([run["id"] for run in first], [run["id"] for run in second])
        expected = ANSWERS["s1_filter_sample"]["sample_25_percent"]
        self.assertEqual(len(first), expected["scored"])
        self.assertEqual(len(sample(ROOTS, rate=0.25)), expected["scored"])
        self.assertEqual(len({run["id"] for run in first}), len(first))

    def test_the_default_draw_catches_the_documented_number_of_wrong_answers(self):
        wrong = set(ANSWERS["s1_evaluator"]["flagged_trace_keys"])
        caught = sum(ts.trace_key(run) in wrong for run in sample(ROOTS))
        self.assertEqual(caught, ANSWERS["s1_filter_sample"]["sample_25_percent"]["caught"])

    def test_the_draw_is_the_generators_and_does_not_depend_on_order_or_on_the_time_shift(self):
        self.assertEqual((ts.SAMPLING_RATE, ts.SAMPLING_SEED), (SEED["meta"]["sampling"]["rate"], SEED["meta"]["sampling"]["seed"]))
        keys = [ts.trace_key(run) for run in sample(ROOTS)]
        self.assertEqual(keys, [ts.trace_key(run) for run in ts.sample_runs(ROOTS, ts.SAMPLING_RATE, ts.SAMPLING_SEED)])
        self.assertEqual(keys, [ts.trace_key(run) for run in sample(list(reversed(ROOTS)))])
        unshifted = ts.root_runs(ts.load_seed(shift_to_now=False))
        self.assertEqual(keys, [ts.trace_key(run) for run in sample(unshifted)])

    def test_another_seed_gives_another_draw_of_the_same_size(self):
        other = sample(ROOTS, seed=ts.SAMPLING_SEED + 1)
        self.assertEqual(len(other), len(sample(ROOTS)))
        self.assertNotEqual([run["id"] for run in other], [run["id"] for run in sample(ROOTS)])

    def test_rate_one_returns_every_run_and_rate_zero_none(self):
        self.assertEqual(len(sample(ROOTS, rate=1.0)), len(ROOTS))
        self.assertEqual(sample(ROOTS, rate=0.0), [])


class ErrorWindowsTest(unittest.TestCase):
    def setUp(self):
        self.result = error_windows(SEED)

    def test_the_background_maximum_the_burst_and_the_threshold_are_the_answer_key(self):
        answer = ANSWERS["s1_alert"]
        self.assertEqual(self.result["minutes"], 5)
        self.assertEqual(self.result["background"]["max_in_any_window"], answer["background_max_in_5_minutes"])
        self.assertEqual(self.result["burst"]["errors"], answer["burst_errors"])
        self.assertEqual(self.result["max_in_any_window"], answer["burst_errors"])
        self.assertEqual(self.result["smallest_safe_threshold"], answer["threshold"])
        self.assertEqual(self.result["burst"]["failing_tools"], [answer["failing_tool"]])

    def test_every_errored_root_run_is_listed_once_oldest_first(self):
        errors = self.result["errors"]
        self.assertEqual(len(errors), ANSWERS["s1_signals"]["errored_root_runs"])
        self.assertEqual([row["start_time"] for row in errors], sorted(row["start_time"] for row in errors))
        self.assertEqual(sum(row["in_burst"] for row in errors), self.result["burst"]["errors"])
        self.assertEqual(self.result["background"]["errors"], ANSWERS["reference"]["s1_alert"]["background_errors"])
        self.assertTrue(all(row["failing_tool"] and row["error"] for row in errors))
        self.assertEqual(sum(window["count"] for window in self.result["windows"]), len(errors))

    def test_the_burst_fits_in_three_minutes_and_lies_about_fifty_minutes_back(self):
        burst = self.result["burst"]
        self.assertAlmostEqual(burst["span_seconds"], ANSWERS["reference"]["s1_alert"]["burst_span_seconds"], places=3)
        self.assertLess(burst["span_seconds"], 180)
        now = datetime.now(timezone.utc)
        self.assertLess(now - burst["first"], timedelta(minutes=60))
        self.assertGreater(now - burst["last"], timedelta(minutes=45))

    def test_the_threshold_holds_however_the_windows_are_aligned(self):
        # Slide a 5-minute window in 10-second steps over the whole day: the background never reaches the
        # threshold, and the burst always crosses it in at least one window.
        threshold = self.result["smallest_safe_threshold"]
        times = [row["start_time"] for row in self.result["errors"]]
        background = [row["start_time"] for row in self.result["errors"] if not row["in_burst"]]
        start, end = min(times) - timedelta(minutes=5), max(times) + timedelta(minutes=5)
        for offset in range(0, 300, 10):
            best_all = best_background = 0
            edge = start + timedelta(seconds=offset)
            while edge < end:
                inside = lambda moment: edge <= moment < edge + timedelta(minutes=5)  # noqa: E731
                best_all = max(best_all, sum(map(inside, times)))
                best_background = max(best_background, sum(map(inside, background)))
                edge += timedelta(minutes=5)
            self.assertLess(best_background, threshold)
            self.assertGreaterEqual(best_all, threshold)

    def test_root_runs_alone_give_the_same_counts_without_tool_names(self):
        result = error_windows(ROOTS)
        self.assertEqual(result["smallest_safe_threshold"], self.result["smallest_safe_threshold"])
        self.assertEqual(result["burst"]["errors"], self.result["burst"]["errors"])
        self.assertEqual(result["burst"]["failing_tools"], [])

    def test_a_wider_window_and_no_errors(self):
        self.assertEqual(error_windows(SEED, minutes=15)["minutes"], 15)
        self.assertGreaterEqual(error_windows(SEED, minutes=15)["max_in_any_window"], self.result["max_in_any_window"])
        empty = error_windows([run for run in ROOTS if not run["error"]])
        self.assertEqual((empty["errors"], empty["windows"], empty["max_in_any_window"], empty["smallest_safe_threshold"]), ([], [], 0, 1))
        self.assertEqual(empty["burst"]["errors"], 0)

    def test_text_bars_show_every_window_with_its_count(self):
        lines = error_bars(self.result)
        self.assertEqual(len(lines), len(self.result["windows"]))
        for line, window in zip(lines, self.result["windows"]):
            self.assertTrue(line.endswith(f"{'#' * window['count']} {window['count']}"))
            self.assertIn("UTC", line)


class FiltersTest(unittest.TestCase):
    # The strings of the Section 1 table (PRD section 7, cells 15, 18 and 25) and the two tag filters.
    DOCUMENTED = {
        "root_runs": "eq(is_root, true)",
        "support_agent_root_runs": 'and(eq(is_root, true), eq(name, "deep_support_agent"))',
        "root_runs_on_1_5_0": 'and(eq(is_root, true), eq(metadata_key, "app_version"), eq(metadata_value, "1.5.0"))',
        "policy_specialist_runs": 'eq(name, "product-policy-specialist")',
        "flagged_wrong_return_window": 'and(eq(is_root, true), eq(feedback_key, "wrong_return_window"), gt(feedback_score, 0.5))',
        "seeded_runs": 'has(tags, "seed:m7")',
        "live_runs": 'has(tags, "live:m7")',
    }

    def test_the_filter_strings_are_the_documented_ones(self):
        self.assertEqual({name: entry.filter for name, entry in FILTERS.items()}, self.DOCUMENTED)
        for entry in FILTERS.values():
            self.assertTrue(entry.meaning and entry.source.count("https://docs.langchain.com/") >= 1)

    def test_each_predicate_selects_the_documented_count(self):
        answer = ANSWERS["s1_filter_sample"]
        self.assertEqual(len(select("root_runs", SEED)), answer["all_root_runs"]["scored"])
        self.assertEqual(len(select("support_agent_root_runs", SEED)), answer["all_root_runs"]["scored"])
        self.assertEqual(len(select("root_runs_on_1_5_0", SEED)), answer["app_version_1_5_0"]["scored"])
        self.assertEqual(len(select("flagged_wrong_return_window", SEED, ROWS)), ANSWERS["s1_routing"]["selected"])
        self.assertEqual(len(select("seeded_runs", SEED)), ANSWERS["reference"]["runs"])
        self.assertEqual(select("live_runs", SEED), [])

    def test_the_filters_catch_the_documented_number_of_wrong_answers(self):
        wrong = set(ANSWERS["s1_evaluator"]["flagged_trace_keys"])
        answer = ANSWERS["s1_filter_sample"]
        for name, key in (("root_runs", "all_root_runs"), ("root_runs_on_1_5_0", "app_version_1_5_0")):
            caught = sum(ts.trace_key(run) in wrong for run in select(name, SEED))
            self.assertEqual(caught, answer[key]["caught"], name)

    def test_the_routing_filter_selects_exactly_the_flagged_root_runs(self):
        selected = select("flagged_wrong_return_window", SEED["runs"], ROWS)
        self.assertEqual(sorted(ts.trace_key(run) for run in selected), ANSWERS["s1_evaluator"]["flagged_trace_keys"])
        self.assertTrue(all(run["parent_run_id"] is None for run in selected))
        # Without the evaluator's feedback nothing is selected: the seeded user scores have another key.
        self.assertEqual(select("flagged_wrong_return_window", SEED), [])
        self.assertEqual(select("flagged_wrong_return_window", SEED, SEED["feedback"]), [])
        self.assertEqual(len(select("flagged_wrong_return_window", SEED, [*SEED["feedback"], *ROWS])), len(selected))

    def test_the_specialist_filter_selects_child_runs_and_one_per_wrong_answer_among_them(self):
        runs = select("policy_specialist_runs", SEED)
        self.assertTrue(runs and all(run["parent_run_id"] is not None and run["name"] == "product-policy-specialist" for run in runs))
        wrong = set(ANSWERS["s1_evaluator"]["flagged_trace_keys"])
        self.assertEqual(sum(ts.trace_key(run) in wrong for run in runs), len(wrong))

    def test_feedback_by_run_and_an_unknown_filter_name(self):
        grouped = feedback_by_run([*SEED["feedback"], *ROWS])
        scored = next(row["run_id"] for row in SEED["feedback"])
        self.assertEqual(set(grouped[scored]), {"user_score", "wrong_return_window"})
        self.assertEqual(feedback_by_run(None), {})
        with self.assertRaises(KeyError):
            select("no_such_filter", SEED)


class CostTest(unittest.TestCase):
    def test_cost_of_is_tokens_times_the_illustrative_price_and_zero_for_other_runs(self):
        llm = next(run for run in SEED["runs"] if run["run_type"] == "llm")
        usage, model = llm["extra"]["metadata"]["usage_metadata"], llm["extra"]["metadata"]["ls_model_name"]
        price = SEED["meta"]["illustrative_prices_per_1m_tokens_usd"][model]
        expected = (usage["input_tokens"] * price["input"] + usage["output_tokens"] * price["output"]) / 1_000_000
        self.assertAlmostEqual(cost_of(llm), expected)
        self.assertGreater(cost_of(llm), 0)
        self.assertEqual(cost_of(ROOTS[0]), 0.0)
        doubled = {name: {"input": 2 * value["input"], "output": 2 * value["output"]} for name, value in SEED["meta"]["illustrative_prices_per_1m_tokens_usd"].items()}
        self.assertAlmostEqual(cost_of(llm, doubled), 2 * expected)

    def test_spend_by_customer_puts_the_documented_top_spender_first(self):
        spend = spend_by(SEED)
        self.assertEqual(next(iter(spend)), ANSWERS["reference"]["s4_spend"]["top_spender"])
        self.assertEqual(list(spend.values()), sorted(spend.values(), reverse=True))
        self.assertAlmostEqual(sum(spend.values()), sum(cost_of(run) for run in SEED["runs"]))
        by_version = spend_by(SEED, "app_version")
        self.assertEqual(set(by_version), set(ANSWERS["reference"]["root_runs_by_version"]))


class DocstringTest(unittest.TestCase):
    def test_every_public_function_says_it_is_a_calculation_and_not_the_product(self):
        public = [value for name, value in vars(local).items()
                  if not name.startswith("_") and inspect.isfunction(value) and value.__module__ == local.__name__]
        self.assertGreaterEqual(len(public), 8)
        for function in public:
            self.assertIn("calculation on seed data, not the product", " ".join((function.__doc__ or "").split()), function.__name__)
        self.assertIn("calculation on seed data, not the product", " ".join(local.LocalFilter.__doc__.split()))


if __name__ == "__main__":
    unittest.main()
