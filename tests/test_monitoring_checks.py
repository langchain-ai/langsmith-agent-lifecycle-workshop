"""utils/monitoring_checks.py and workshop_modules/module_7/exercises/: one checker, with and without the answer file.

What is proven here:

- every answer of `answers.json` passes its check and every changed answer fails with the field named;
- every reference solution passes and every untouched stub fails with a message a learner can act on;
- the verdicts are the same when `answers.json` is absent and only `answer_hashes.json` is left,
  both in this process and in a copy of the repository laid out like the Instruqt sandbox (no
  `solutions/` folder, no `answers.json`);
- `exercises/check.py` prints one PASS or FAIL line and sets the exit code;
- a function that calls `sys.exit()` is a failed check, never an exit code 0 without a result line;
- the loader runs the blocks at the top of an exercise file and names a top-level line it skipped;
- `perform_eval` has to pass from its own source alone, as LangSmith runs a code evaluator: no name
  from the rest of its file (an import, a helper, a type annotation), and no import of this
  repository or of an installed package;
- a data file that was edited or deleted is named as the problem before any function is blamed,
  and `check.py --restore-data` regenerates it without writing an answer file that was not there;
- `show_report.py` fits the width it is given and does not print the answer of an exercise;
- nothing calls a model or the network: the whole module runs inside `refuse_non_local_connects()`.

Run: uv run python -m unittest tests.test_monitoring_checks
"""

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import utils.monitoring_checks as checks
import utils.trace_seeding as ts
from evaluators import WRONG_RETURN_WINDOW_SOURCE, wrong_return_window_evaluator
from utils.monitoring_checks import (
    ANSWER_FIELDS,
    COMMAND_LINE_IDS,
    EXERCISE_FILES,
    EXERCISE_IDS,
    VERIFIED,
    check,
    check_file,
    expected_line,
)
from utils.monitoring_local import apply_evaluator
from utils.offline_capture import refuse_non_local_connects

REPO_ROOT = ts.REPO_ROOT
EXERCISES = REPO_ROOT / "workshop_modules" / "module_7" / "exercises"
SOLUTIONS = EXERCISES / "solutions"
CHECK_PY = EXERCISES / "check.py"
ANSWERS = json.loads((ts.DATA / ts.ANSWERS_FILE).read_text(encoding="utf-8"))
EXERCISE_FILE_NAMES = ("masking.py", "read_the_report.py", "return_window_evaluator.py", "triage.py")
FUNCTION_IDS = tuple(EXERCISE_FILES)

NON_LOCAL_ATTEMPTS: list = []


def setUpModule():
    global NON_LOCAL_ATTEMPTS
    guard = refuse_non_local_connects()
    NON_LOCAL_ATTEMPTS = guard.__enter__()
    unittest.addModuleCleanup(guard.__exit__, None, None, None)


def tearDownModule():
    assert NON_LOCAL_ATTEMPTS == [], f"a test tried to leave the machine: {NON_LOCAL_ATTEMPTS}"


def without_answer_file():
    """Grade from the hashes, as in the Instruqt sandbox: point the checker at an answer file that does not exist."""
    return mock.patch.object(checks, "ANSWERS_PATH", ts.DATA / "answers-file-removed.json")


def stripped_env(**extra) -> dict:
    """The environment of the build rules: PATH, HOME and tracing off, plus what a test adds."""
    env = {name: os.environ[name] for name in ("PATH", "HOME") if name in os.environ}
    return {**env, "LANGSMITH_TRACING": "false", **extra}


def run_check_py(*ids, check_py=CHECK_PY, cwd=REPO_ROOT, **extra_env):
    done = subprocess.run([sys.executable, str(check_py), *ids], cwd=cwd, env=stripped_env(**extra_env), capture_output=True, text=True, timeout=120)
    return done.returncode, done.stdout.strip().splitlines(), done.stderr


def changed(value):
    """A value of the same type that is certainly not the answer."""
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1
    if isinstance(value, float):
        return round(value + 0.011, 3) if value < 0.9 else round(value - 0.011, 3)
    if isinstance(value, str):
        return "something-else"
    if isinstance(value, list):
        return value[:-1] if len(value) > 1 else [*value, *value]
    if isinstance(value, dict):
        first = next(iter(value))
        return {**value, first: changed(value[first])}
    raise TypeError(type(value))


class EveryModeTestCase(unittest.TestCase):
    """Runs each test body twice: with answers.json, and with only the hashes."""

    def both_modes(self):
        yield "answers", mock.patch.object(checks, "ANSWERS_PATH", checks.ANSWERS_PATH)
        yield "hashes", without_answer_file()


class AnswerKeyTest(EveryModeTestCase):
    def test_the_checker_knows_every_id_of_the_answer_key_and_nothing_else(self):
        graded = [key for key in ANSWERS if key not in ("_about", "reference")]
        self.assertEqual(list(ANSWER_FIELDS), graded)
        self.assertEqual(EXERCISE_IDS, ("setup", *graded))
        for exercise_id, fields in ANSWER_FIELDS.items():
            self.assertEqual(list(fields), list(ANSWERS[exercise_id]), exercise_id)
        hashes = json.loads((ts.DATA / ts.HASHES_FILE).read_text(encoding="utf-8"))
        self.assertEqual(set(hashes["fields"]), set(graded))

    def test_grading_source_follows_the_answer_file(self):
        self.assertEqual(checks.grading_source(), "answers")
        with without_answer_file():
            self.assertEqual(checks.grading_source(), "hashes")
            with mock.patch.object(checks, "HASHES_PATH", ts.DATA / "hashes-file-removed.json"):
                self.assertEqual(checks.grading_source(), "none")
                ok, message = check("s1_routing", ANSWERS["s1_routing"])
                self.assertFalse(ok)
                self.assertIn("cannot grade s1_routing", message)

    def test_every_answer_passes_and_prints_the_expected_line(self):
        for mode, patch in self.both_modes():
            with patch:
                for exercise_id in ANSWER_FIELDS:
                    with self.subTest(mode=mode, exercise_id=exercise_id):
                        ok, message = check(exercise_id, ANSWERS[exercise_id])
                        self.assertTrue(ok, message)
                        self.assertEqual(message, expected_line(exercise_id, ANSWERS))
                        self.assertTrue(message.startswith(VERIFIED))
                        self.assertNotIn("\n", message)

    def test_every_changed_field_fails_and_is_named_without_giving_the_answer(self):
        for mode, patch in self.both_modes():
            with patch:
                for exercise_id, fields in ANSWER_FIELDS.items():
                    if exercise_id == "s3_assertions":
                        continue  # a wrong pick gets a message about that candidate: see TriageAndAssertionsTest
                    for field in fields:
                        with self.subTest(mode=mode, exercise_id=exercise_id, field=field):
                            answer = ANSWERS[exercise_id]
                            ok, message = check(exercise_id, {**answer, field: changed(answer[field])})
                            self.assertFalse(ok, message)
                            self.assertIn(f"`{field}`", message)
                            self.assertNotIn(VERIFIED, message)
                            for other in fields:
                                if other != field:
                                    self.assertNotIn(f"`{other}`", message)
                            if isinstance(answer[field], str):
                                self.assertNotIn(answer[field], message)

    def test_the_expected_lines_state_the_numbers_of_the_answer_key(self):
        lines = {exercise_id: expected_line(exercise_id) for exercise_id in ANSWER_FIELDS}
        self.assertIn("13 root runs errored; 25 conversations got a thumbs-down, 16 of them", lines["s1_signals"])
        self.assertIn("exactly the 11 planted traces", lines["s1_evaluator"])
        self.assertIn("260 scored, 11 caught", lines["s1_filter_sample"])
        self.assertIn("104 scored, 11 caught", lines["s1_filter_sample"])
        self.assertIn("65 scored, 3 caught", lines["s1_filter_sample"])
        self.assertIn("at most 2 in any 5 minutes and the burst has 8, so 3 is the smallest threshold", lines["s1_alert"])
        self.assertIn("get_order_status", lines["s1_alert"])
        self.assertIn("selects 11 root runs", lines["s1_routing"])
        self.assertIn("Order status and tracking (78 conversations, 39%)", lines["s2_report"])
        self.assertIn("Where is my order (19.6%)", lines["s2_report"])
        self.assertIn("27 conversations", lines["s2_claim"])
        self.assertIn("flags 11 of them", lines["s2_claim"])
        self.assertIn("no search_policy_docs call under product-policy-specialist", lines["s3_evidence"])
        self.assertIn("issue 1 apply_fix_and_add_examples; issue 2 review_pull_request; issue 3 save_for_later", lines["s3_triage"])
        self.assertIn("no_30_day_claim and states_14_day_window", lines["s3_assertions"])
        self.assertIn("1 root run contains a raw email address: 1 in inputs, 0 in outputs", lines["s4_leak"])
        self.assertIn("0 payloads contain it", lines["s4_masking"])
        self.assertIn("https://gateway.smith.langchain.com/openai/v1", lines["s4_routes"])
        self.assertIn("402 is a spend limit block (APIStatusError)", lines["s4_blocks"])
        self.assertIn("429 is a rate limit block (RateLimitError)", lines["s4_blocks"])
        self.assertIn("403 is a model access block (PermissionDeniedError)", lines["s4_blocks"])
        self.assertIn("retries only 429", lines["s4_blocks"])

    def test_shorthand_forms_of_single_field_answers(self):
        seed = ts.load_seed()
        roots = ts.root_runs(seed)
        rows = apply_evaluator(wrong_return_window_evaluator, roots)
        wrong = ANSWERS["s1_evaluator"]["flagged_trace_keys"]
        wrong_runs = [run for run in roots if ts.trace_key(run) in wrong]
        for mode, patch in self.both_modes():
            with patch, self.subTest(mode=mode):
                self.assertTrue(check("s1_evaluator", wrong)[0])
                self.assertTrue(check("s1_evaluator", set(wrong))[0])
                self.assertTrue(check("s1_evaluator", list(reversed(wrong)))[0])
                self.assertTrue(check("s1_evaluator", wrong_runs)[0])
                self.assertTrue(check("s1_evaluator", rows)[0])
                self.assertTrue(check("s1_routing", 11)[0])
                self.assertTrue(check("s1_routing", wrong_runs)[0])
                self.assertTrue(check("s3_triage", ANSWERS["s3_triage"]["actions"])[0])
                self.assertTrue(check("s3_assertions", ["states_14_day_window", "no_30_day_claim"])[0])
                self.assertTrue(check("s3_assertions", {"no_30_day_claim", "states_14_day_window"})[0])
                self.assertTrue(check("s4_routes", ANSWERS["s4_routes"]["base_url"] + "/")[0])
                self.assertTrue(check("s4_masking", {"middleware_only": 8, "with_anonymizer": 0, "control_string_unchanged": True})[0])
                self.assertTrue(check("s4_blocks", {**{int(k) if k.isdigit() else k: v for k, v in ANSWERS["s4_blocks"].items()}})[0])
                ok, message = check("s1_evaluator", wrong[:-1])
                self.assertFalse(ok)
                self.assertEqual(message, "10 traces are flagged, expected 11.")
                ok, message = check("s1_evaluator", [*wrong[:-1], "t-0001"])
                self.assertIn("that is the right number, but they are not the 11 wrong answers", message)
                self.assertFalse(check("s3_triage", list(reversed(ANSWERS["s3_triage"]["actions"])))[0])

    def test_wrong_types_missing_fields_and_unknown_ids_are_explained(self):
        ok, message = check("s9_nothing", 1)
        self.assertFalse(ok)
        self.assertIn("unknown exercise id 's9_nothing'", message)
        self.assertIn("nothing to check", check("s1_alert")[1])
        self.assertIn("missing burst_errors, threshold, failing_tool", check("s1_alert", {"background_max_in_5_minutes": 2})[1])
        self.assertIn("`threshold` should be a whole number", check("s1_alert", {**ANSWERS["s1_alert"], "threshold": "three"})[1])
        self.assertIn("`threshold` should be a whole number", check("s1_alert", {**ANSWERS["s1_alert"], "threshold": True})[1])
        self.assertIn("not a percentage", check("s2_report", {**ANSWERS["s2_report"], "highest_error_rate": 19.6})[1])
        self.assertIn("`all_root_runs` is missing caught", check("s1_filter_sample", {**ANSWERS["s1_filter_sample"], "all_root_runs": {"scored": 260}})[1])
        self.assertIn("not an action code", check("s3_triage", ["apply_fix_and_add_examples", "merge_it", "save_for_later"])[1])
        # Numbers that differ only in how they are written are the same answer.
        self.assertTrue(check("s2_claim", {"conversations": 27.0, "error_rate": 0, "flagged": 11})[0])
        self.assertTrue(check("s2_report", {**ANSWERS["s2_report"], "largest_category_share": 78 / 200, "highest_error_rate": 9 / 46})[0])

    def test_check_never_raises(self):
        for exercise_id in EXERCISE_IDS:
            for junk in (object(), 3.5, "text", [1, 2], {"unexpected": None}, lambda *args, **kwargs: 1 / 0):
                with self.subTest(exercise_id=exercise_id, junk=repr(junk)[:30]):
                    ok, message = check(exercise_id, junk)
                    self.assertFalse(ok)
                    self.assertTrue(message and "\n" not in message)


class ExerciseFilesTest(unittest.TestCase):
    def test_stubs_and_solutions_have_the_same_four_file_names(self):
        self.assertEqual(sorted(path.name for path in SOLUTIONS.glob("*.py")), list(EXERCISE_FILE_NAMES))
        self.assertEqual(sorted(path.name for path in EXERCISES.glob("*.py")), sorted([*EXERCISE_FILE_NAMES, "check.py", "show_report.py"]))
        self.assertEqual(sorted({file for file, _, _ in EXERCISE_FILES.values()}), list(EXERCISE_FILE_NAMES))
        self.assertEqual(COMMAND_LINE_IDS, ("setup", "s1_evaluator", "s2_report", "s2_claim", "s3_triage", "s4_masking"))

    def test_every_stub_function_has_a_docstring_and_raises_not_implemented(self):
        arguments = {"s1_evaluator": ({},), "s2_report": ({"clusters": []},), "s2_claim": ("x", {}, {}, None), "s3_triage": ({},), "s4_masking": ()}
        for exercise_id, (file_name, function_name, definition) in EXERCISE_FILES.items():
            with self.subTest(exercise_id=exercise_id):
                function = checks.load_exercise_function(exercise_id, EXERCISES)
                self.assertEqual(function.__name__, function_name)
                self.assertGreater(len(function.__doc__ or ""), 200)
                self.assertIn(f"def {definition}:", (EXERCISES / file_name).read_text(encoding="utf-8"))
                with self.assertRaises(NotImplementedError):
                    function(*arguments[exercise_id])

    def test_the_evaluator_solution_is_the_exported_source_byte_for_byte(self):
        solution = (SOLUTIONS / "return_window_evaluator.py").read_bytes()
        self.assertEqual(solution, WRONG_RETURN_WINDOW_SOURCE.encode("utf-8"))
        self.assertNotIn(b"import", solution)

    def test_no_exercise_file_holds_a_graded_answer(self):
        # The stubs are what a learner (and a coding agent) reads first: no trace key of the answer, no topic count.
        secrets = [*ANSWERS["s1_evaluator"]["flagged_trace_keys"], ANSWERS["s1_alert"]["failing_tool"], ANSWERS["s2_report"]["largest_category"],
                   ANSWERS["s2_report"]["highest_error_rate_subcategory"], ANSWERS["s3_evidence"]["missing_tool"], ANSWERS["s3_evidence"]["under_run"],
                   ANSWERS["s4_routes"]["base_url"], *(ANSWERS["s4_blocks"][status]["exception"] for status in ("402", "429", "403"))]
        for name in (*EXERCISE_FILE_NAMES, "check.py", "show_report.py"):
            text = (EXERCISES / name).read_text(encoding="utf-8")
            for secret in secrets:
                self.assertNotIn(secret, text, name)
        source = Path(checks.__file__).read_text(encoding="utf-8")
        for secret in secrets:
            self.assertNotIn(secret, source)


class SolutionsAndStubsTest(EveryModeTestCase):
    def test_every_solution_passes_its_check(self):
        for mode, patch in self.both_modes():
            with patch:
                for exercise_id in FUNCTION_IDS:
                    with self.subTest(mode=mode, exercise_id=exercise_id):
                        ok, message = check_file(exercise_id, SOLUTIONS)
                        self.assertTrue(ok, message)
                        self.assertTrue(message.startswith(expected_line(exercise_id, ANSWERS)), message)

    def test_every_stub_fails_with_a_message_that_names_what_is_wrong(self):
        for mode, patch in self.both_modes():
            with patch:
                for exercise_id, (file_name, function_name, definition) in EXERCISE_FILES.items():
                    with self.subTest(mode=mode, exercise_id=exercise_id):
                        ok, message = check_file(exercise_id, EXERCISES)
                        self.assertFalse(ok, message)
                        self.assertIn(f"{function_name} is not implemented yet", message)
                        self.assertIn("NotImplementedError", message)
                        self.assertIn(definition, message)
                        self.assertIn(file_name, message)
                        self.assertNotIn(VERIFIED, message)

    def test_the_masking_stub_message_shows_the_leak_first(self):
        ok, message = check_file("s4_masking", EXERCISES)
        self.assertFalse(ok)
        self.assertRegex(message, r"^With PIIMiddleware alone, [1-9]\d* of \d+ uploaded payloads contain jordan\.lee@example\.com\.")


def reference(run, example=None):
    return wrong_return_window_evaluator(run, example)


class EvaluatorDiagnosticsTest(EveryModeTestCase):
    def messages_for(self, function):
        seen = set()
        for mode, patch in self.both_modes():
            with patch:
                ok, message = check("s1_evaluator", function)
                self.assertFalse(ok, f"{mode}: {message}")
                seen.add(message)
        self.assertEqual(len(seen), 1, "the two grading modes disagree")
        return seen.pop()

    def test_the_reference_function_passes(self):
        for mode, patch in self.both_modes():
            with patch, self.subTest(mode=mode):
                ok, message = check("s1_evaluator", reference)
                self.assertTrue(ok, message)
                self.assertIn("flags 11 of 260 root runs", message)

    def test_a_function_that_takes_only_the_run(self):
        message = self.messages_for(lambda run: {"wrong_return_window": False})
        self.assertIn("define the function as perform_eval(run, example=None)", message)

    def test_the_naive_check_flags_a_correct_answer_about_an_unopened_item(self):
        def naive(run, example=None):
            return {"wrong_return_window": "30 days" in ts.reply_text(run)}

        self.assertIn("it also flags a correct answer about an unopened item", self.messages_for(naive))

    def test_substring_matching_takes_unused_for_used(self):
        def substrings(run, example=None):
            question = ts.question_text(run)
            return {"wrong_return_window": ("opened" in question.replace("unopened", "") or "used" in question) and "30 days" in ts.reply_text(run)}

        self.assertIn("'unused' is not 'used'", self.messages_for(substrings))

    def test_missing_the_word_used(self):
        def opened_only(run, example=None):
            return {"wrong_return_window": " opened" in ts.question_text(run) and "30 days" in ts.reply_text(run)}

        self.assertIn("it misses a wrong answer: the customer says the product was used", self.messages_for(opened_only))

    def test_ignoring_the_reply(self):
        def question_only(run, example=None):
            words = ts.question_text(run).replace(".", " ").replace(";", " ").split()
            return {"wrong_return_window": "opened" in words or "used" in words}

        self.assertIn("the reply gives 14 days, which is the policy", self.messages_for(question_only))

    def test_raising_on_a_failed_run(self):
        def fragile(run, example=None):
            reply = run["outputs"]["messages"][-1]["content"]
            return {"wrong_return_window": reference(run)["wrong_return_window"] and bool(reply)}

        message = self.messages_for(fragile)
        self.assertIn("perform_eval raised KeyError", message.replace("fragile", "perform_eval"))
        self.assertIn("a run that failed (error set, outputs empty)", message)

    def test_raising_when_outputs_is_none(self):
        def fragile(run, example=None):
            run["outputs"].get("messages")
            return reference(run)

        self.assertIn("a run that failed (its outputs are None)", self.messages_for(fragile))

    def test_a_wrong_return_shape(self):
        self.assertIn('must return {"wrong_return_window": True} or {"wrong_return_window": False}', self.messages_for(lambda run, example=None: True))
        self.assertIn('must return {"wrong_return_window": True}', self.messages_for(lambda run, example=None: {"score": 1}))
        self.assertIn("must be True or False", self.messages_for(lambda run, example=None: {"wrong_return_window": "yes"}))

    def test_right_on_the_control_cases_but_not_on_the_seed(self):
        def misses_one_product(run, example=None):
            return {"wrong_return_window": reference(run)["wrong_return_window"] and "ThinkPad" not in ts.question_text(run)}

        message = self.messages_for(misses_one_product)
        self.assertRegex(message, r"flags (\d|10) of 260 root runs of the seed, expected 11\.$")

    def test_a_stub_like_function(self):
        def perform_eval(run, example=None):
            raise NotImplementedError

        message = self.messages_for(perform_eval)
        self.assertIn("perform_eval is not implemented yet", message)
        self.assertIn("return_window_evaluator.py", message)


class ReportDiagnosticsTest(EveryModeTestCase):
    def setUp(self):
        self.solution = checks.load_exercise_function("s2_report", SOLUTIONS)
        self.count = checks.load_exercise_function("s2_claim", SOLUTIONS)

    def failure(self, exercise_id, function):
        seen = set()
        for mode, patch in self.both_modes():
            with patch:
                ok, message = check(exercise_id, function)
                self.assertFalse(ok, f"{mode}: {message}")
                seen.add(message)
        self.assertEqual(len(seen), 1, "the two grading modes disagree")
        return seen.pop()

    def test_the_public_report_cases_are_what_the_solution_returns(self):
        for what, report, expected in checks.REPORT_CASES:
            self.assertEqual(self.solution(report), expected, what)

    def test_summarise_that_ranks_every_cluster_returns_a_category_as_subcategory(self):
        def all_clusters(report):
            result = self.solution(report)
            worst = max(report["clusters"], key=lambda cluster: cluster["stats"]["error_rate"])
            return {**result, "highest_error_rate_subcategory": worst["name"], "highest_error_rate": worst["stats"]["error_rate"]}

        message = self.failure("s2_report", all_clusters)
        self.assertIn("`highest_error_rate_subcategory` should be \"Return labels\", it returned \"Returns\"", message)
        self.assertIn("That is a top-level category", message)

    def test_summarise_that_divides_by_every_cluster(self):
        def double_counted(report):
            result = self.solution(report)
            total = sum(cluster["num_runs"] for cluster in report["clusters"])
            return {**result, "largest_category_share": round(result["largest_category_conversations"] / total, 2)}

        message = self.failure("s2_report", double_counted)
        self.assertIn("`largest_category_share` should be 0.6, it returned 0.3", message)
        self.assertIn("top-level categories only", message)

    def test_summarise_with_a_missing_key_a_wrong_type_and_a_hard_coded_answer(self):
        self.assertIn("missing highest_error_rate", self.failure("s2_report", lambda report: {k: v for k, v in self.solution(report).items() if k != "highest_error_rate"}))
        self.assertIn("it returned str", self.failure("s2_report", lambda report: "Order status and tracking"))
        self.assertIn("is not right on a small test report with two categories", self.failure("s2_report", lambda report: dict(ANSWERS["s2_report"])))
        self.assertIn("raised AttributeError", self.failure("s2_report", lambda report: report.clusters))

    def test_flagged_in_subcategory_hard_coded(self):
        message = self.failure("s2_claim", lambda name, seed, labels, perform_eval: 11)
        self.assertIn("returned 11 for an evaluator that flags nothing", message)

    def test_flagged_in_subcategory_that_counts_root_runs(self):
        def counts_runs(name, seed, labels, perform_eval):
            keys = {key for conversation in labels["conversations"] if conversation["subcategory"] == name for key in conversation["trace_keys"]}
            return sum(perform_eval(run)["wrong_return_window"] for run in ts.root_runs(seed) if ts.trace_key(run) in keys)

        message = self.failure("s2_claim", counts_runs)
        self.assertIn("a conversation with two turns counts once", message)

    def test_flagged_in_subcategory_that_ignores_the_name(self):
        def every_conversation(name, seed, labels, perform_eval):
            return sum(any(perform_eval(run)["wrong_return_window"] for run in ts.root_runs(seed) if ts.trace_key(run) in conversation["trace_keys"])
                       for conversation in labels["conversations"])

        message = self.failure("s2_claim", every_conversation)
        self.assertRegex(message, r"returned 200 for '.+' with an evaluator that flags every run; that subcategory has \d+ conversations")

    def test_flagged_in_subcategory_that_returns_something_else(self):
        self.assertIn("must return a whole number", self.failure("s2_claim", lambda name, seed, labels, perform_eval: [1, 2]))
        self.assertIn("must return a whole number", self.failure("s2_claim", lambda name, seed, labels, perform_eval: True))


class TriageAndAssertionsTest(EveryModeTestCase):
    def setUp(self):
        self.solution = checks.load_exercise_function("s3_triage", SOLUTIONS)

    def failure(self, exercise_id, obj):
        seen = set()
        for mode, patch in self.both_modes():
            with patch:
                ok, message = check(exercise_id, obj)
                self.assertFalse(ok, f"{mode}: {message}")
                seen.add(message)
        self.assertEqual(len(seen), 1, "the two grading modes disagree")
        return seen.pop()

    def test_the_reference_rule_of_the_generator_and_the_solution_agree_on_every_case(self):
        issues = ts.load_engine_issues()["issues"]
        self.assertEqual([self.solution(issue) for issue in issues], ANSWERS["s3_triage"]["actions"])
        for what, issue, expected, why in checks.TRIAGE_CASES:
            self.assertEqual(self.solution(issue), expected, what)
            self.assertEqual(ts.next_action_for(issue), expected, what)
            self.assertIn(expected, ts.TRIAGE_ACTIONS)

    def test_a_rule_keyed_on_severity_fails_an_extra_case(self):
        def by_severity(issue):
            return {1: "apply_fix_and_add_examples", 2: "review_pull_request", 3: "save_for_later"}[issue["severity"]]

        message = self.failure("s3_triage", by_severity)
        self.assertIn("the next action is review_pull_request", message)
        self.assertIn("whatever the severity", message)

    def test_a_rule_keyed_on_status_fails_the_open_finding(self):
        def by_status(issue):
            return {"open": "apply_fix_and_add_examples", "fixing": "review_pull_request", "watching": "save_for_later"}[issue["status"]]

        self.assertIn("a finding is an observation with nothing to fix yet", self.failure("s3_triage", by_status))

    def test_a_rule_that_passes_the_extra_cases_but_not_the_board(self):
        def closes_hallucinations(issue):
            return "close_incorrectly_flagged" if "Hallucination" in issue.get("tags", []) and not issue.get("fixes") else self.solution(issue)

        message = self.failure("s3_triage", closes_hallucinations)
        self.assertIn("not right for at least one of the three issues on the board", message)
        self.assertIn("issue 1 (type actionable, status open, 0 entries in fixes) -> close_incorrectly_flagged", message)
        self.assertIn("issue 2 (type actionable, status fixing, 1 entry in fixes) -> review_pull_request", message)

    def test_an_unknown_action_code(self):
        self.assertIn("Return one of the four action codes", self.failure("s3_triage", lambda issue: "merge_it"))

    def test_six_candidates_two_separate_two_hold_for_both_two_fail_for_both(self):
        case = checks.assertion_case()
        self.assertIn("30 days", case["recorded_answer"])
        self.assertIn("14 days", case["corrected_answer"])
        self.assertFalse(wrong_return_window_evaluator({"inputs": {"messages": [{"role": "user", "content": case["question"]}]},
                                                        "outputs": {"messages": [{"type": "ai", "content": case["corrected_answer"]}]}})["wrong_return_window"])
        table = checks.assertion_table(case)
        self.assertEqual(len(table), 6)
        self.assertEqual(len({row["key"] for row in table}), 6)
        kinds = [(row["holds_for_recorded"], row["holds_for_corrected"]) for row in table]
        self.assertEqual(kinds.count((False, True)), 2)
        self.assertEqual(kinds.count((True, True)), 2)
        self.assertEqual(kinds.count((False, False)), 2)
        separating = sorted(row["key"] for row in table if row["separates"])
        self.assertEqual(separating, ANSWERS["s3_assertions"]["assertions"])
        self.assertEqual(set(separating), set(ts.ASSERTION_KEYS))

    def test_the_two_right_candidates_carry_the_comments_of_the_sample_board(self):
        board = ts.load_engine_issues()
        proposed = {a["key"]: a["comment"] for a in board["offline_examples"][board["issues"][0]["id"]][0]["assertions"]}
        ours = {candidate["key"]: candidate["comment"] for candidate in checks.ASSERTION_CANDIDATES}
        for key, comment in proposed.items():
            self.assertEqual(ours[key], comment)

    def test_assertion_picks_are_explained(self):
        self.assertIn("holds for the recorded answer too", self.failure("s3_assertions", ["states_14_day_window", "counts_from_delivery"]))
        self.assertIn("fails for the corrected answer", self.failure("s3_assertions", ["no_30_day_claim", "gives_the_last_return_date"]))
        self.assertIn("pick exactly two", self.failure("s3_assertions", ["no_30_day_claim"]))
        self.assertIn("pick exactly two", self.failure("s3_assertions", ["no_30_day_claim", "no_30_day_claim"]))
        self.assertIn("is not one of the six candidate keys", self.failure("s3_assertions", ["no_30_day_claim", "be_nice"]))
        self.assertIn("give the keys of the two assertions", self.failure("s3_assertions", "no_30_day_claim"))


class MaskingDiagnosticsTest(EveryModeTestCase):
    def failure(self, function):
        seen = set()
        for mode, patch in self.both_modes():
            with patch:
                ok, message = check("s4_masking", function)
                self.assertFalse(ok, f"{mode}: {message}")
                seen.add(message)
        self.assertEqual(len(seen), 1, "the two grading modes disagree")
        return seen.pop()

    def test_the_capture_shows_the_leak_and_the_reference_anonymizer_removes_it(self):
        base = checks.masking_capture()
        self.assertGreater(base["with_email"], 0)
        self.assertGreater(base["with_control"], 0)
        masked = checks.masking_capture(checks.load_exercise_function("s4_masking", SOLUTIONS)())
        self.assertEqual((masked["with_email"], masked["payloads"], masked["with_control"]), (0, base["payloads"], base["with_control"]))

    def test_hiding_everything_does_not_pass(self):
        def build_anonymizer():
            return lambda data: {}

        message = self.failure(build_anonymizer)
        self.assertIn("the email address is gone, but so is text that is not PII", message)
        self.assertIn("ORD-2025-0050", message)

    def test_an_anonymizer_that_masks_nothing(self):
        def build_anonymizer():
            return lambda data: data

        self.assertRegex(self.failure(build_anonymizer), r"With your anonymizer, [1-9]\d* of \d+ still contain it; the target is 0\.")

    def test_a_rule_written_for_one_address(self):
        def build_anonymizer():
            from langsmith.anonymizer import create_anonymizer

            return create_anonymizer([{"pattern": "jordan\\.lee@example\\.com", "replace": "<email>"}])

        message = self.failure(build_anonymizer)
        self.assertIn("on a second address it is not right", message)
        self.assertIn("returns.desk@techhub.example is still in", message)

    def test_an_anonymizer_that_raises_or_returns_nothing(self):
        def raises():
            def anonymizer(data):
                raise RuntimeError("boom")

            return anonymizer

        with self.assertLogs(level="ERROR"), mock.patch("sys.stderr"):
            self.assertIn("uploaded 0 payloads where", self.failure(raises))

    def test_build_anonymizer_that_returns_no_function_or_raises(self):
        self.assertIn("must return an anonymizer", self.failure(lambda: None))
        self.assertIn("raised ZeroDivisionError", self.failure(lambda: 1 / 0))


class SetupCheckTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        self.state = self.folder / "state.json"

    def write(self, **state):
        self.state.write_text(json.dumps(state), encoding="utf-8")
        return self.state

    def test_skipped_and_verified_pass_and_a_key_is_never_required(self):
        ok, message = check("setup", self.write(langsmith="skipped", seed_verified=True))
        self.assertTrue(ok, message)
        self.assertIn("without a LangSmith key, which is fine", message)
        ok, message = check("setup", str(self.write(langsmith="verified", seed_verified=True)))
        self.assertTrue(ok, message)
        self.assertIn("LangSmith is connected", message)
        self.assertTrue(check("setup", {"langsmith": "skipped", "seed_verified": True})[0])

    def test_the_recorded_seed_hash_must_be_the_files(self):
        actual = hashlib.sha256((ts.DATA / ts.SEED_FILE).read_bytes()).hexdigest()
        self.assertTrue(check("setup", {"langsmith": "skipped", "seed_verified": True, "seed_sha256": actual})[0])
        ok, message = check("setup", {"langsmith": "skipped", "seed_verified": True, "seed_sha256": "0" * 64})
        self.assertFalse(ok)
        self.assertIn("SHA-256 no longer matches", message)

    def test_a_missing_or_broken_state_file_and_wrong_values(self):
        ok, message = check("setup", self.folder / "absent.json")
        self.assertFalse(ok)
        self.assertIn("setup has not run yet", message)
        self.assertIn("scripts/module7_connect_langsmith.py --skip", message)
        self.state.write_text("{not json", encoding="utf-8")
        self.assertIn("is not valid JSON", check("setup", self.state)[1])
        self.assertIn("`seed_verified` is not true", check("setup", self.write(langsmith="skipped", seed_verified=False))[1])
        self.assertIn("`seed_verified` is not true", check("setup", self.write(langsmith="skipped"))[1])
        self.assertIn("expected 'verified' or 'skipped'", check("setup", self.write(langsmith="failed", seed_verified=True))[1])

    def test_a_changed_seed_file_fails(self):
        (self.folder / ts.SEED_FILE).write_bytes((ts.DATA / ts.SEED_FILE).read_bytes()[:-2] + b" }")
        with mock.patch.object(ts, "DATA", self.folder):
            ok, message = check("setup", {"langsmith": "skipped", "seed_verified": True})
        self.assertFalse(ok)
        self.assertIn("SHA-256 no longer matches the generated seed", message)
        with mock.patch.object(ts, "DATA", self.folder / "nowhere"):
            self.assertIn("is missing", check("setup", {"langsmith": "skipped", "seed_verified": True})[1])

    def test_the_default_state_file_comes_from_the_environment(self):
        with mock.patch.dict(os.environ, {"M7_STATE_FILE": str(self.write(langsmith="skipped", seed_verified=True))}):
            self.assertTrue(check_file("setup")[0])
        with mock.patch.dict(os.environ, {"M7_STATE_FILE": str(self.folder / "absent.json")}):
            self.assertIn("setup has not run yet", check_file("setup")[1])

    def test_recovery_advice_names_the_one_seed_file_and_works_without_the_answer_key(self):
        # The hands-on sandbox has no answers.json and no git history. Advice that restores the whole data folder
        # brings the answer key back where git exists, and `module7_seed.py verify` prints it and fails without it.
        seed_rel = f"workshop_modules/module_7/data/{ts.SEED_FILE}"
        (self.folder / ts.SEED_FILE).write_bytes((ts.DATA / ts.SEED_FILE).read_bytes()[:-2] + b" }")
        with mock.patch.object(ts, "DATA", self.folder):
            changed_seed = check("setup", {"langsmith": "skipped", "seed_verified": True})[1]
        with mock.patch.object(ts, "DATA", self.folder / "nowhere"):
            missing_seed = check("setup", {"langsmith": "skipped", "seed_verified": True})[1]
        for message in (changed_seed, missing_seed):
            self.assertIn(f"`git checkout -- {seed_rel}`", message)
            # The first advice is a command that works without git and in every challenge of the hands-on track.
            self.assertIn("run `uv run python workshop_modules/module_7/exercises/check.py --restore-data`", message)
            self.assertIn("Skip on the challenge you are in runs the same command", message)
            self.assertNotIn("Skip on the Setup challenge", message, "a learner who is past the Setup challenge cannot click its Skip")
            self.assertIn("scripts/module7_connect_langsmith.py", message)
        not_verified = check("setup", self.write(langsmith="skipped", seed_verified=False))[1]
        self.assertIn("scripts/module7_connect_langsmith.py", not_verified)
        with mock.patch.object(ts, "seed_files", side_effect=RuntimeError("no database")):
            cannot_generate = check("setup", {"langsmith": "skipped", "seed_verified": True})[1]
        self.assertIn("could not regenerate the seed", cannot_generate)
        self.assertIn("scripts/module7_connect_langsmith.py --skip", cannot_generate)
        with without_answer_file(), mock.patch.object(checks, "HASHES_PATH", self.folder / "no-hashes.json"):
            cannot_grade = check("s1_routing", 11)[1]
        self.assertIn(f"workshop_modules/module_7/data/{ts.HASHES_FILE}", cannot_grade)
        for message in (changed_seed, missing_seed, not_verified, cannot_generate, cannot_grade):
            self.assertNotIn("module7_seed.py", message)
            self.assertNotRegex(message, r"git checkout -- workshop_modules/module_7/data(?!/)", "the advice must not restore the whole data folder")
        # No message anywhere in the checker sends a learner to either.
        source = Path(checks.__file__).read_text(encoding="utf-8")
        self.assertNotIn("module7_seed.py verify", source)
        self.assertNotIn("Restore the data folder", source)


class LoaderTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)

    def write(self, name, text):
        (self.folder / name).write_text(text, encoding="utf-8")

    def test_only_definitions_run_and_imports_and_helpers_are_kept(self):
        marker = self.folder / "ran.txt"
        self.write("triage.py", f'''"""A learner's file with code around the function."""
import re
from pathlib import Path

FINDING = re.compile(r"^finding$")
Path({str(marker)!r}).write_text("module-level statement ran")
print("printed while loading")


def is_finding(issue):
    return bool(FINDING.match(issue.get("type") or ""))


def next_action(issue):
    print("printed while deciding")
    if is_finding(issue):
        return "save_for_later"
    if issue.get("status") == "fixing" and issue.get("fixes"):
        return "review_pull_request"
    return "apply_fix_and_add_examples"


assert next_action({{"type": "finding"}}) == "no such action", "a test call at the bottom ran"
if __name__ == "__main__":
    raise SystemExit("the main block ran")
raise SystemExit("a statement after the function ran")
''')
        ok, message = check_file("s3_triage", self.folder)
        self.assertTrue(ok, message)
        self.assertFalse(marker.exists(), "a module-level call ran during the check")
        self.assertNotIn("Note:", message, "a passed check says nothing about skipped lines")

    def test_blocks_at_the_top_of_the_file_run_as_they_do_on_import(self):
        # Three correct solutions that a loader keeping only imports, assignments and definitions would fail.
        self.write("masking.py", '''import re

try:
    from langsmith.anonymizer import create_anonymizer
except ImportError:  # an older langsmith
    create_anonymizer = None

RULES = []
for pattern, replacement in [(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}", "<email>")]:
    RULES.append({"pattern": re.compile(pattern), "replace": replacement})


def build_anonymizer():
    return create_anonymizer(RULES)
''')
        ok, message = check_file("s4_masking", self.folder)
        self.assertTrue(ok, message)
        self.write("triage.py", '''FINDINGS = ["finding"]
FINDINGS += ["observation"]
if True:
    IN_FLIGHT = "fixing"
with open(__file__, encoding="utf-8") as handle:
    FIRST_LINE = handle.readline()


def next_action(issue):
    if issue.get("type") in FINDINGS:
        return "save_for_later"
    return "review_pull_request" if issue.get("status") == IN_FLIGHT and issue.get("fixes") else "apply_fix_and_add_examples"
''')
        ok, message = check_file("s3_triage", self.folder)
        self.assertTrue(ok, message)

    def test_a_failed_check_names_the_top_level_lines_that_did_not_run(self):
        # Correct when imported, because line 5 fills RULES; the loader skips a bare top-level call.
        self.write("masking.py", '''import re
from langsmith.anonymizer import create_anonymizer

RULES = []
RULES.append({"pattern": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}"), "replace": "<email>"})


def build_anonymizer():
    return create_anonymizer(RULES)


print(build_anonymizer())
''')
        ok, message = check_file("s4_masking", self.folder)
        self.assertFalse(ok, message)
        self.assertIn("still contain it; the target is 0.", message)
        self.assertIn("Note: the check did not run lines 5 and 12 of masking.py.", message)
        self.assertIn("move it into the function", message)
        self.assertNotIn("\n", message)
        # A file with nothing but a docstring around its function gets no note: the stub's message stays as it was.
        self.assertNotIn("Note:", check_file("s4_masking", EXERCISES)[1])
        # A top-level name that only a skipped line would define: the load error carries the note too.
        self.write("triage.py", "import json\njson.loads('{}')\nACTION = undefined_name\n\ndef next_action(issue):\n    return ACTION\n")
        message = check_file("s3_triage", self.folder)[1]
        self.assertIn("triage.py could not be loaded: NameError", message)
        self.assertIn("Note: the check did not run line 2 of triage.py.", message)

    EVALUATOR_BODY = '''    messages = (run.get("outputs") or {}).get("messages") or []
    reply = messages[-1].get("content", "") if messages else ""
    question = run["inputs"]["messages"][-1]["content"]
'''

    def test_the_evaluator_has_to_pass_from_its_own_source_alone(self):
        # LangSmith runs the pasted function without the rest of the file, so a top-level import is not there.
        self.write("return_window_evaluator.py", "import re\n\n\ndef perform_eval(run, example=None):\n" + self.EVALUATOR_BODY
                   + '''    return {"wrong_return_window": bool(re.search(r"\\b(opened|used)\\b", question)) and bool(re.search(r"\\b30 days\\b", reply))}\n''')
        for mode, patch in (("answers", mock.patch.object(checks, "ANSWERS_PATH", checks.ANSWERS_PATH)), ("hashes", without_answer_file())):
            with patch, self.subTest(mode=mode):
                self.assertTrue(check("s1_evaluator", checks.load_exercise_function("s1_evaluator", self.folder))[0], "inside its file the function is right")
                ok, message = check_file("s1_evaluator", self.folder)
                self.assertFalse(ok, message)
                self.assertIn("perform_eval passes inside return_window_evaluator.py, but not when its source is run on its own", message)
                self.assertIn("NameError: name 're' is not defined", message)
                self.assertIn("Move every import, constant and helper function it uses inside the function body.", message)
                self.assertNotIn("\n", message)

    def test_the_evaluator_may_not_lean_on_a_helper_or_a_constant_of_the_file(self):
        self.write("return_window_evaluator.py", '''OPENED = ("opened", "used")


def _words(text):
    return "".join(ch if ch.isalnum() else " " for ch in text.lower()).split()


def perform_eval(run, example=None):
''' + self.EVALUATOR_BODY + '''    asked, said = _words(question), _words(reply)
    return {"wrong_return_window": any(word in asked for word in OPENED) and any(a == "30" and b in ("day", "days") for a, b in zip(said, said[1:]))}
''')
        ok, message = check_file("s1_evaluator", self.folder)
        self.assertFalse(ok, message)
        self.assertIn("not when its source is run on its own", message)
        self.assertIn("NameError: name '_words' is not defined", message)

    def test_a_self_contained_evaluator_passes_with_its_import_inside_the_body(self):
        self.write("return_window_evaluator.py", "def perform_eval(run, example=None):\n    import re\n\n" + self.EVALUATOR_BODY
                   + '''    return {"wrong_return_window": bool(re.search(r"\\b(opened|used)\\b", question)) and bool(re.search(r"\\b30 days\\b", reply))}\n''')
        ok, message = check_file("s1_evaluator", self.folder)
        self.assertTrue(ok, message)
        self.assertIn("flags 11 of 260 root runs", message)

    def test_an_evaluator_that_is_not_a_top_level_def_cannot_be_pasted(self):
        self.write("return_window_evaluator.py", "def make():\n    def perform_eval(run, example=None):\n        import re\n\n"
                   + self.EVALUATOR_BODY.replace("    ", "        ")
                   + '''        return {"wrong_return_window": bool(re.search(r"\\b(opened|used)\\b", question)) and bool(re.search(r"\\b30 days\\b", reply))}\n    return perform_eval\n\n\nperform_eval = make()\n''')
        ok, message = check_file("s1_evaluator", self.folder)
        self.assertFalse(ok, message)
        self.assertIn("does not define it with a `def` at the top level of the file", message)
        # A default value that needs a name from the file fails when the definition is run alone.
        self.write("return_window_evaluator.py", "WINDOW = '30 days'\n\n\ndef perform_eval(run, example=None, window=WINDOW):\n" + self.EVALUATOR_BODY
                   + '''    words = question.replace(".", " ").replace(",", " ").split()\n    return {"wrong_return_window": ("opened" in words or "used" in words) and window in reply}\n''')
        ok, message = check_file("s1_evaluator", self.folder)
        self.assertFalse(ok, message)
        self.assertIn("its definition cannot be run on its own (NameError: name 'WINDOW' is not defined)", message)

    RULE = '''    return {"wrong_return_window": bool(re.search(r"\\b(opened|used)\\b", question)) and bool(re.search(r"\\b30 days\\b", reply))}\n'''

    def test_the_evaluator_may_not_import_the_repository_or_an_installed_package(self):
        # Each of these is right when it is called here, because the repository root and its packages can be imported
        # in this process. LangSmith has neither, so a learner who pastes the function gets an error after a PASS.
        # The first one is also the cheapest way around the exercise: it calls the repo's reference evaluator.
        variants = {
            "the reference evaluator of the repo": (
                "    from evaluators.online_evaluators import perform_eval as reference\n\n    return reference(run, example)\n",
                "it imports evaluators.online_evaluators, which is not part of Python's standard library"),
            "helpers of the repo and an installed package": (
                "    from utils.trace_seeding import question_text, reply_text\n    import langsmith\n    import re\n\n"
                "    if run.get('error') or not run.get('outputs'):\n        return {'wrong_return_window': False}\n"
                "    question, reply = question_text(run), reply_text(run)\n" + self.RULE,
                "it imports utils.trace_seeding and langsmith, which are not part of Python's standard library"),
            "__import__ with a module name": (
                "    reference = __import__('evaluators.online_evaluators', fromlist=['perform_eval']).perform_eval\n    return reference(run, example)\n",
                "it imports evaluators.online_evaluators, which is not"),
            "importlib.import_module with a module name": (
                "    import importlib\n\n    return importlib.import_module('evaluators.online_evaluators').perform_eval(run, example)\n",
                "it imports evaluators.online_evaluators, which is not"),
            "a module name put together at run time": (
                "    import importlib\n\n    name = 'evaluators.' + 'online_evaluators'\n    return importlib.import_module(name).perform_eval(run, example)\n",
                "it imports a module chosen at run time, which is not"),
            "an import inside a helper that is defined in the body": (
                "    def reference():\n        import evaluators.online_evaluators as module\n\n        return module.perform_eval\n\n    return reference()(run, example)\n",
                "it imports evaluators.online_evaluators, which is not"),
        }
        for what, (body, expected) in variants.items():
            self.write("return_window_evaluator.py", "def perform_eval(run, example=None):\n" + body)
            for mode, patch in (("answers", mock.patch.object(checks, "ANSWERS_PATH", checks.ANSWERS_PATH)), ("hashes", without_answer_file())):
                with patch, self.subTest(what=what, mode=mode):
                    self.assertTrue(check("s1_evaluator", checks.load_exercise_function("s1_evaluator", self.folder))[0], "called here, the function is right")
                    ok, message = check_file("s1_evaluator", self.folder)
                    self.assertFalse(ok, message)
                    self.assertIn(expected, message)
                    self.assertIn("LangSmith runs a code evaluator without this repository and without the packages installed here", message)
                    self.assertIn("Use the standard library only", message)
                    self.assertNotIn("\n", message)
        # The standard library is fine, however it is imported.
        for what, imports in {
            "import re": "    import re\n\n",
            "from re import search, with other standard modules": "    import json, datetime\n    from collections import Counter\n    import re\n\n",
            "importlib.import_module('re')": "    import importlib\n\n    re = importlib.import_module('re')\n",
            "__import__('re')": "    re = __import__('re')\n",
        }.items():
            with self.subTest(what=what):
                self.write("return_window_evaluator.py", "def perform_eval(run, example=None):\n" + imports + self.EVALUATOR_BODY + self.RULE)
                ok, message = check_file("s1_evaluator", self.folder)
                self.assertTrue(ok, message)
        self.assertTrue(check_file("s1_evaluator", SOLUTIONS)[0], "the reference solution imports nothing")

    def test_an_annotation_that_needs_a_name_from_the_file_cannot_be_pasted(self):
        # The checker's own file starts with `from __future__ import annotations`. Compiled with that flag inherited, a
        # learner's annotations were never evaluated, and a function that needs `typing` names from the top of its
        # file passed the stand-alone step. Pasted alone, its `def` raises NameError.
        typed = ("def perform_eval(run: Dict[str, Any], example: Optional[dict] = None) -> Dict[str, bool]:\n    import re\n\n"
                 + self.EVALUATOR_BODY + self.RULE)
        for what, top in {
            "typing names imported at the top of the file": "from typing import Any, Dict, Optional\n\n\n",
            "the same file with its own future import": '"""A typed evaluator."""\nfrom __future__ import annotations\n\nfrom typing import Any, Dict, Optional\n\n\n',
        }.items():
            with self.subTest(what=what):
                self.write("return_window_evaluator.py", top + typed)
                self.assertTrue(check("s1_evaluator", checks.load_exercise_function("s1_evaluator", self.folder))[0], "inside its file the function is right")
                ok, message = check_file("s1_evaluator", self.folder)
                self.assertFalse(ok, message)
                self.assertIn("its definition cannot be run on its own (NameError: name 'Dict' is not defined)", message)
                self.assertIn("no type annotation that needs a name from outside the function", message)
        # Without the typing import the file itself does not load: the learner's code is compiled as Python compiles it.
        self.write("return_window_evaluator.py", typed)
        self.assertIn("return_window_evaluator.py could not be loaded: NameError: name 'Dict' is not defined", check_file("s1_evaluator", self.folder)[1])
        # Annotations made of built-in names need nothing from the file.
        self.write("return_window_evaluator.py", "def perform_eval(run: dict, example: dict | None = None) -> dict[str, bool]:\n    import re\n\n"
                   + self.EVALUATOR_BODY + self.RULE)
        ok, message = check_file("s1_evaluator", self.folder)
        self.assertTrue(ok, message)

    def test_sys_exit_in_a_learners_code_is_a_failed_check(self):
        # SystemExit is not an Exception. Uncaught, it ended check.py with exit code 0 and no result line.
        exits = {
            "s1_evaluator": ("return_window_evaluator.py", "def perform_eval(run, example=None):\n    raise SystemExit(0)\n", "perform_eval called sys.exit()"),
            "s2_report": ("read_the_report.py", "import sys\n\n\ndef summarise(report):\n    sys.exit()\n\n\ndef flagged_in_subcategory(name, seed, labels, perform_eval):\n    sys.exit(0)\n", "summarise called sys.exit()"),
            "s2_claim": ("read_the_report.py", None, "flagged_in_subcategory called sys.exit()"),
            "s3_triage": ("triage.py", "def next_action(issue):\n    raise SystemExit\n", "next_action called sys.exit()"),
            "s4_masking": ("masking.py", "def build_anonymizer():\n    raise SystemExit(0)\n", "build_anonymizer() called sys.exit()"),
        }
        for exercise_id, (file_name, text, expected) in exits.items():
            with self.subTest(exercise_id=exercise_id):
                if text is not None:
                    self.write(file_name, text)
                ok, message = check_file(exercise_id, self.folder)
                self.assertFalse(ok, message)
                self.assertIn(expected, message)
                self.assertIn("remove the call to sys.exit()", message)
        # At the top of the file, inside a block that the loader runs.
        self.write("triage.py", "import sys\n\nif True:\n    sys.exit(0)\n\n\ndef next_action(issue):\n    return 'save_for_later'\n")
        ok, message = check_file("s3_triage", self.folder)
        self.assertFalse(ok, message)
        self.assertIn("triage.py could not be loaded: its top-level code called sys.exit()", message)
        # Inside the anonymizer, which the LangSmith client calls while the trace is recorded.
        self.write("masking.py", "def build_anonymizer():\n    def anonymizer(data):\n        raise SystemExit(0)\n\n    return anonymizer\n")
        ok, message = check_file("s4_masking", self.folder)
        self.assertFalse(ok, message)
        self.assertNotIn(VERIFIED, message)

    def test_check_itself_reports_sys_exit_for_a_function_given_directly(self):
        def perform_eval(run, example=None):
            raise SystemExit(0)

        ok, message = check("s1_evaluator", perform_eval)
        self.assertFalse(ok)
        self.assertIn("perform_eval called sys.exit() (it raised SystemExit) on a customer who opened the product", message)

    def test_a_byte_order_mark_and_windows_line_ends_are_not_a_syntax_error(self):
        text = (SOLUTIONS / "triage.py").read_text(encoding="utf-8").replace("\n", "\r\n")
        (self.folder / "triage.py").write_bytes(b"\xef\xbb\xbf" + text.encode("utf-8"))
        ok, message = check_file("s3_triage", self.folder)
        self.assertTrue(ok, message)

    def test_what_a_learner_prints_does_not_reach_stdout(self):
        self.write("triage.py", 'def next_action(issue):\n    print("debug", issue["status"])\n    return "save_for_later"\n')
        with mock.patch("sys.stdout") as stdout:
            ok, _ = check_file("s3_triage", self.folder)
        self.assertFalse(ok)
        stdout.write.assert_not_called()

    def test_missing_file_syntax_error_missing_function_and_import_error(self):
        ok, message = check_file("s3_triage", self.folder)
        self.assertFalse(ok)
        self.assertIn("triage.py is missing from", message)
        self.write("triage.py", "def next_action(issue)\n    return 'save_for_later'\n")
        self.assertIn("triage.py has a syntax error on line 1", check_file("s3_triage", self.folder)[1])
        self.write("triage.py", "def triage(issue):\n    return 'save_for_later'\n")
        self.assertIn("triage.py does not define next_action. Define it as next_action(issue).", check_file("s3_triage", self.folder)[1])
        self.write("triage.py", "import a_package_that_does_not_exist\n\ndef next_action(issue):\n    return 'save_for_later'\n")
        self.assertIn("triage.py could not be loaded: ModuleNotFoundError", check_file("s3_triage", self.folder)[1])

    def test_ids_that_are_not_checked_from_files(self):
        ok, message = check_file("s1_alert", self.folder)
        self.assertFalse(ok)
        self.assertIn("is checked inside its notebook, not from the command line", message)
        self.assertIn("unknown exercise id 'nope'", check_file("nope", self.folder)[1])


class DataFilesTest(unittest.TestCase):
    """A data file that was edited or deleted is the checker's first finding, and `--restore-data` regenerates it.

    Each test works on a copy of the data folder. Before, a seed file with one trace less passed
    the evaluator check and blamed a correct `flagged_in_subcategory`, and a truncated seed or an
    emptied label file was reported as "a bug in the checker".
    """

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.data = Path(folder.name) / "data"
        shutil.copytree(ts.DATA, self.data)
        for patcher in (mock.patch.object(ts, "DATA", self.data), mock.patch.object(checks, "ANSWERS_PATH", self.data / ts.ANSWERS_FILE),
                        mock.patch.object(checks, "HASHES_PATH", self.data / ts.HASHES_FILE)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def damage(self, how):
        seed, labels = self.data / ts.SEED_FILE, self.data / ts.LABELS_FILE
        if how == "one trace less":
            stored = json.loads(seed.read_text(encoding="utf-8"))
            stored["traces"].pop()
            seed.write_text(json.dumps(stored), encoding="utf-8")
            return [ts.SEED_FILE]
        if how == "truncated seed":
            seed.write_bytes(seed.read_bytes()[:5000])
            return [ts.SEED_FILE]
        if how == "emptied labels":
            labels.write_text("{}", encoding="utf-8")
            return [ts.LABELS_FILE]
        if how == "report and board deleted":
            (self.data / ts.INSIGHTS_FILE).unlink()
            (self.data / ts.ENGINE_FILE).unlink()
            return [ts.INSIGHTS_FILE, ts.ENGINE_FILE]
        raise ValueError(how)

    def test_intact_files_are_not_reported(self):
        self.assertEqual(checks.changed_data_files(), [])
        self.assertTrue(check_file("s3_triage", SOLUTIONS)[0])
        # A checkout with Windows line endings, or a file that was only re-indented, holds the same data.
        labels = self.data / ts.LABELS_FILE
        labels.write_bytes(labels.read_bytes().replace(b"\n", b"\r\n"))
        report = self.data / ts.INSIGHTS_FILE
        report.write_text(json.dumps(json.loads(report.read_text(encoding="utf-8"))), encoding="utf-8")
        self.assertEqual(checks.changed_data_files(), [])
        # A restore is exact all the same: the setup check compares the seed file byte for byte.
        original = (REPO_ROOT / "workshop_modules" / "module_7" / "data" / ts.LABELS_FILE).read_bytes()
        self.assertEqual(sorted(checks.restore_data_files()), sorted([ts.LABELS_FILE, ts.INSIGHTS_FILE]))
        self.assertEqual(labels.read_bytes(), original)
        # The hands-on track removes the answer file on purpose: its absence is not damage.
        (self.data / ts.ANSWERS_FILE).unlink()
        self.assertEqual(checks.changed_data_files(), [])
        self.assertTrue(check_file("s2_report", SOLUTIONS)[0])

    def test_a_damaged_data_file_is_named_before_any_function_is_blamed(self):
        for how in ("one trace less", "truncated seed", "emptied labels", "report and board deleted"):
            with self.subTest(how=how):
                shutil.rmtree(self.data)
                shutil.copytree(REPO_ROOT / "workshop_modules" / "module_7" / "data", self.data)
                names = self.damage(how)
                self.assertEqual(sorted(checks.changed_data_files()), sorted(names))
                for exercise_id in FUNCTION_IDS:
                    ok, message = check_file(exercise_id, SOLUTIONS)  # a correct function
                    self.assertFalse(ok, f"{exercise_id}: {message}")
                    for name in names:
                        self.assertIn(f"workshop_modules/module_7/data/{name}", message)
                    self.assertIn("missing or", message)
                    self.assertIn("This is not about your function.", message)
                    self.assertIn("Run `uv run python workshop_modules/module_7/exercises/check.py --restore-data` in the terminal", message)
                    self.assertNotIn("bug in the checker", message)
                    self.assertNotIn("git checkout", message, "the hands-on sandbox has no git history")
                    self.assertNotIn("\n", message)
                # A stub gets the same message: the data comes first, whatever the function does.
                self.assertIn("--restore-data", check_file("s1_evaluator", EXERCISES)[1])

    def test_a_notebook_check_that_trips_over_a_damaged_file_does_not_call_it_a_bug(self):
        # `check` (the notebooks) does not compare the files on every call; it does when the checker itself fails.
        claim = checks.load_exercise_function("s2_claim", SOLUTIONS)
        self.damage("emptied labels")
        ok, message = check("s2_claim", claim)
        self.assertFalse(ok)
        self.assertIn(f"workshop_modules/module_7/data/{ts.LABELS_FILE}", message)
        self.assertIn("--restore-data", message)
        self.assertNotIn("bug in the checker", message)
        # With intact files a failure inside the checker is still reported as one.
        self.assertEqual(checks.restore_data_files(), [ts.LABELS_FILE])
        with mock.patch.object(ts, "load_labels", side_effect=RuntimeError("boom")):
            self.assertIn("This is a bug in the checker", check("s2_claim", claim)[1])
        # And if the generator cannot run, the comparison is skipped and the check goes on.
        with mock.patch.object(ts, "seed_files", side_effect=RuntimeError("no database")):
            self.assertIsNone(checks._data_problem())
            self.assertTrue(check_file("s3_triage", SOLUTIONS)[0])

    def test_restore_data_regenerates_what_differs_and_never_adds_the_answer_file(self):
        original = {path.name: path.read_bytes() for path in self.data.iterdir()}
        self.assertEqual(checks.restore_data_files(), [], "nothing to do on intact files")
        self.damage("one trace less")
        self.damage("emptied labels")
        self.damage("report and board deleted")
        (self.data / ts.ANSWERS_FILE).unlink()  # as in the hands-on sandbox
        (self.data / "gateway_blocked_responses.json").write_text("[]", encoding="utf-8")  # written by hand, not generated: not touched
        restored = checks.restore_data_files()
        self.assertEqual(sorted(restored), sorted([ts.SEED_FILE, ts.LABELS_FILE, ts.INSIGHTS_FILE, ts.ENGINE_FILE]))
        for name in restored:
            self.assertEqual((self.data / name).read_bytes(), original[name], name)
        self.assertFalse((self.data / ts.ANSWERS_FILE).exists(), "the answer key must not come back where it was removed")
        self.assertEqual((self.data / "gateway_blocked_responses.json").read_text(encoding="utf-8"), "[]")
        self.assertEqual(checks.changed_data_files(), [])
        for exercise_id in FUNCTION_IDS:
            ok, message = check_file(exercise_id, SOLUTIONS)
            self.assertTrue(ok, f"{exercise_id}: {message}")
        # Where the answer file exists and was edited (a developer's checkout), it is regenerated too.
        (self.data / ts.ANSWERS_FILE).write_text("{}", encoding="utf-8")
        self.assertEqual(checks.restore_data_files(), [ts.ANSWERS_FILE])
        self.assertEqual((self.data / ts.ANSWERS_FILE).read_bytes(), original[ts.ANSWERS_FILE])

    def test_the_restore_command_prints_what_it_did(self):
        def run(*argv):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = checks.main(list(argv))
            return code, out.getvalue()

        self.assertEqual(run("--restore-data"), (0, "Nothing to restore: the data files in workshop_modules/module_7/data are intact.\n"))
        self.damage("truncated seed")
        code, printed = run("--restore-data")
        self.assertEqual((code, printed), (0, f"Restored workshop_modules/module_7/data/{ts.SEED_FILE} from the generator.\n"))
        self.assertEqual(checks.changed_data_files(), [])
        code, printed = run("--restore-data", "s1_evaluator")
        self.assertEqual(code, 2)
        self.assertIn("--restore-data takes no id", printed)
        with mock.patch.object(ts, "seed_files", side_effect=RuntimeError("no database")):
            code, printed = run("--restore-data")
        self.assertEqual(code, 1)
        self.assertTrue(printed.startswith("FAIL: the data files could not be regenerated (RuntimeError: no database)"), printed)
        self.assertIn("--restore-data", checks._USAGE)


class ShowReportTest(unittest.TestCase):
    """`exercises/show_report.py`: the reading version of Sections 2 and 3, read in a terminal pane of unknown width."""

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("m7_show_report", EXERCISES / "show_report.py")
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def printed(self, width=None, columns=None):
        out = io.StringIO()
        environment = {"COLUMNS": str(columns)} if columns else {}
        with contextlib.redirect_stdout(out), mock.patch.dict(os.environ, environment):
            if not columns:
                os.environ.pop("COLUMNS", None)
            code = self.module.main(width)
        self.assertEqual(code, 0)
        return out.getvalue()

    def test_the_four_categories_and_the_three_issues_are_printed_at_every_width(self):
        report, board = ts.load_insights_report(), ts.load_engine_issues()
        categories = [cluster["name"] for cluster in report["clusters"] if cluster["parent_id"] is None]
        subcategories = [cluster["name"] for cluster in report["clusters"] if cluster["parent_id"] is not None]
        self.assertEqual((len(categories), len(board["issues"])), (4, 3))
        for width in (60, 72, 80, 86, 87, 100):
            with self.subTest(width=width):
                text = self.printed(width)
                lines = text.splitlines()
                self.assertLessEqual(max(len(line) for line in lines), width, "a line is wider than the page")
                for name in (*categories, *subcategories):
                    self.assertIn(name, text)
                for number in (1, 2, 3):
                    self.assertTrue(any(line.startswith(f"Issue {number}  [") for line in lines), f"issue {number}")
                for cluster in report["clusters"]:  # the numbers of each row survive both table layouts
                    self.assertRegex(text, rf"{cluster['num_runs']:>3}( convs)? +{100 * cluster['num_runs'] / 200:.1f}%")
                self.assertIn("pull request 42 on branch engine/normalise-order-ids", " ".join(text.split()))

    def test_the_width_follows_the_terminal_between_60_and_100_columns(self):
        widest = lambda text: max(len(line) for line in text.splitlines())  # noqa: E731
        self.assertEqual(widest(self.printed(columns=64)), 64)
        self.assertEqual(widest(self.printed(columns=100)), 100)
        self.assertEqual(widest(self.printed(columns=200)), 100, "wider than 100 columns is not used")
        self.assertEqual(widest(self.printed(columns=30)), 60, "below 60 columns the terminal wraps the lines itself")
        # Output that is not a terminal (piped, or run by a coding agent) gets 80 columns.
        with mock.patch.object(self.module.shutil, "get_terminal_size", wraps=self.module.shutil.get_terminal_size) as asked:
            self.assertLessEqual(widest(self.printed()), 80)
        self.assertEqual(asked.call_args.kwargs["fallback"][0], 80)
        # The one-line table is used only where it fits.
        self.assertIn("latency p50", self.printed(87))
        self.assertNotIn("latency p50", self.printed(86))
        self.assertIn(" convs  ", self.printed(86))

    def test_the_assertions_of_the_proposed_example_are_not_printed(self):
        # They are the graded answer of `s3_assertions`; the exercise docstrings send the learner to this script first.
        board = ts.load_engine_issues()
        examples = [example for group in board["offline_examples"].values() for example in group]
        self.assertTrue(examples and all(example["assertions"] for example in examples), "the board file still proposes an example")
        text = " ".join(self.printed(100).split())
        for key in ANSWERS["s3_assertions"]["assertions"]:
            self.assertNotIn(key, text)
        for candidate in checks.ASSERTION_CANDIDATES:  # no candidate at all, right or wrong
            self.assertNotIn(candidate["key"], text)
            self.assertNotIn(candidate["comment"], text)
        for example in examples:
            for assertion in example["assertions"]:
                self.assertNotIn(assertion["comment"], text)
            self.assertIn(f"Built from trace {example['seed_trace_key']}, with {len(example['assertions'])} assertions", text)
        self.assertIn("choosing them is an exercise of Section 3", text)
        source = (EXERCISES / "show_report.py").read_text(encoding="utf-8")
        self.assertNotIn('assertion["key"]', source)
        self.assertNotIn("assertion['key']", source)


class CommandLineTest(unittest.TestCase):
    """`exercises/check.py` as the plan's check runs it: a new process, stripped environment, repository root."""

    def test_every_stub_prints_one_fail_line_and_exits_1(self):
        for exercise_id in FUNCTION_IDS:
            with self.subTest(exercise_id=exercise_id):
                code, lines, stderr = run_check_py(exercise_id)
                self.assertEqual(code, 1, stderr)
                self.assertEqual(len(lines), 1)
                self.assertTrue(lines[0].startswith("FAIL: "), lines[0])
                self.assertIn("is not implemented yet", lines[0])

    def test_every_solution_prints_one_pass_line_and_exits_0(self):
        for exercise_id in FUNCTION_IDS:
            with self.subTest(exercise_id=exercise_id):
                code, lines, stderr = run_check_py(exercise_id, M7_EXERCISES_DIR="workshop_modules/module_7/exercises/solutions")
                self.assertEqual(code, 0, stderr)
                self.assertEqual(len(lines), 1)
                self.assertTrue(lines[0].startswith("PASS: "), lines[0])
                self.assertTrue(lines[0].isascii(), lines[0])

    def test_several_ids_in_one_call_and_from_another_working_directory(self):
        with tempfile.TemporaryDirectory() as elsewhere:
            code, lines, stderr = run_check_py("s2_report", "s2_claim", "s3_triage", cwd=elsewhere, M7_EXERCISES_DIR=str(SOLUTIONS))
            self.assertEqual((code, [line[:5] for line in lines]), (0, ["PASS:", "PASS:", "PASS:"]), stderr)
            code, lines, _ = run_check_py("s2_report", "s3_triage", cwd=elsewhere)
            self.assertEqual((code, [line[:5] for line in lines]), (1, ["FAIL:", "FAIL:"]))

    def test_sys_exit_never_gives_exit_code_0(self):
        # What the track's Check button runs. Exit code 0 means "passed" to it, so an exit raised by the learner's code must not get there.
        variants = {
            "s1_evaluator": ("return_window_evaluator.py", "def perform_eval(run, example=None):\n    raise SystemExit(0)\n"),
            "s2_report": ("read_the_report.py", "import sys\n\n\ndef summarise(report):\n    sys.exit()\n"),
            "s3_triage": ("triage.py", "import sys\n\n\ndef next_action(issue):\n    sys.exit(0)\n"),
            "s4_masking": ("masking.py", "def build_anonymizer():\n    raise SystemExit(0)\n"),
        }
        with tempfile.TemporaryDirectory() as folder:
            for exercise_id, (file_name, text) in variants.items():
                with self.subTest(exercise_id=exercise_id):
                    (Path(folder) / file_name).write_text(text, encoding="utf-8")
                    code, lines, stderr = run_check_py(exercise_id, M7_EXERCISES_DIR=folder)
                    self.assertEqual(code, 1, stderr)
                    self.assertEqual(len(lines), 1, lines)
                    self.assertRegex(lines[0], r"^FAIL: .*called sys\.exit\(\)")

    def test_setup_reads_the_state_file(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder) / "state.json"
            code, lines, _ = run_check_py("setup", M7_STATE_FILE=str(state))
            self.assertEqual(code, 1)
            self.assertTrue(lines[0].startswith("FAIL: setup has not run yet"), lines[0])
            state.write_text(json.dumps({"langsmith": "skipped", "seed_verified": True}), encoding="utf-8")
            code, lines, stderr = run_check_py("setup", M7_STATE_FILE=str(state))
            self.assertEqual(code, 0, stderr)
            self.assertTrue(lines[0].startswith("PASS: the seed is intact and verified"), lines[0])

    def test_usage_list_and_unknown_ids(self):
        code, lines, _ = run_check_py()
        self.assertEqual(code, 2)
        self.assertTrue(lines[0].startswith("usage: check.py"))
        code, lines, _ = run_check_py("--list")
        self.assertEqual(code, 0)
        self.assertEqual([line.split()[0] for line in lines], list(COMMAND_LINE_IDS))
        code, lines, _ = run_check_py("s1_alert")
        self.assertEqual(code, 2)
        self.assertIn("checked inside its notebook", lines[0])
        code, lines, _ = run_check_py("nope")
        self.assertEqual(code, 2)
        self.assertTrue(lines[0].startswith("FAIL: unknown exercise id 'nope'"))


class SandboxLayoutTest(unittest.TestCase):
    """The Instruqt sandbox (PRD section 14.3 item 5): `solutions/` and `data/answers.json` are gone from the workshop folder.

    A copy of the files the checker needs is laid out in a temporary folder without those two,
    and `check.py` runs there in a new process. The solutions come from a second folder, as the
    track's solve scripts copy them from a place outside the workshop folder.
    """

    @classmethod
    def setUpClass(cls):
        folder = tempfile.TemporaryDirectory()
        cls.addClassCleanup(folder.cleanup)
        cls.root = Path(folder.name) / "workshop"
        cls.kept_solutions = Path(folder.name) / "m7-solutions"
        (cls.root / "utils").mkdir(parents=True)
        for name in ("__init__.py", "trace_seeding.py", "monitoring_checks.py", "monitoring_local.py", "offline_capture.py"):
            shutil.copy(REPO_ROOT / "utils" / name, cls.root / "utils" / name)
        (cls.root / "evaluators").mkdir()
        shutil.copy(REPO_ROOT / "evaluators" / "online_evaluators.py", cls.root / "evaluators" / "online_evaluators.py")
        (cls.root / "data" / "structured").mkdir(parents=True)
        shutil.copy(REPO_ROOT / "data" / "structured" / "techhub.db", cls.root / "data" / "structured" / "techhub.db")
        shutil.copytree(REPO_ROOT / "data" / "documents", cls.root / "data" / "documents")
        # The seed generator reads one constant from the agent's retry middleware (for the s4_blocks answer).
        (cls.root / "agents" / "middleware").mkdir(parents=True)
        shutil.copy(REPO_ROOT / "agents" / "middleware" / "fault_tolerance.py", cls.root / "agents" / "middleware" / "fault_tolerance.py")
        module = cls.root / "workshop_modules" / "module_7"
        shutil.copytree(REPO_ROOT / "workshop_modules" / "module_7" / "data", module / "data")
        shutil.copytree(EXERCISES, module / "exercises", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(module / "exercises" / "solutions", cls.kept_solutions)
        shutil.rmtree(module / "exercises" / "solutions")
        (module / "data" / ts.ANSWERS_FILE).unlink()
        cls.exercises = module / "exercises"
        cls.check_py = cls.exercises / "check.py"

    def run_here(self, *ids, **extra_env):
        return run_check_py(*ids, check_py=self.check_py, cwd=self.root, **extra_env)

    def test_1_the_layout_has_no_answer_file_and_no_solutions(self):
        self.assertFalse((self.root / "workshop_modules" / "module_7" / "data" / ts.ANSWERS_FILE).exists())
        self.assertFalse((self.exercises / "solutions").exists())
        self.assertTrue((self.root / "workshop_modules" / "module_7" / "data" / ts.HASHES_FILE).exists())

    def test_2_stubs_fail_with_the_learner_facing_message(self):
        code, lines, stderr = self.run_here(*FUNCTION_IDS)
        self.assertEqual(code, 1, stderr)
        self.assertEqual(len(lines), len(FUNCTION_IDS))
        for line in lines:
            self.assertTrue(line.startswith("FAIL: "), line)
            self.assertIn("is not implemented yet", line)

    def test_3_setup_passes_without_a_key(self):
        code, lines, _ = self.run_here("setup")
        self.assertEqual(code, 1)
        self.assertIn("setup has not run yet", lines[0])
        (self.root / ".m7_state.json").write_text(json.dumps({"langsmith": "skipped", "seed_verified": True}), encoding="utf-8")
        code, lines, stderr = self.run_here("setup")
        self.assertEqual(code, 0, stderr)
        self.assertTrue(lines[0].startswith("PASS: "), lines[0])

    def test_4_a_wrong_implementation_still_gets_its_diagnostic(self):
        (self.exercises / "return_window_evaluator.py").write_text(
            "def perform_eval(run, example=None):\n"
            "    messages = (run.get('outputs') or {}).get('messages') or []\n"
            "    return {'wrong_return_window': bool(messages) and '30 days' in str(messages[-1].get('content'))}\n",
            encoding="utf-8",
        )
        code, lines, _ = self.run_here("s1_evaluator")
        self.assertEqual(code, 1)
        self.assertIn("it also flags a correct answer about an unopened item", lines[0])

    def test_4b_sys_exit_and_a_function_that_is_not_self_contained_fail_here_too(self):
        (self.exercises / "return_window_evaluator.py").write_text("def perform_eval(run, example=None):\n    raise SystemExit(0)\n", encoding="utf-8")
        code, lines, stderr = self.run_here("s1_evaluator")
        self.assertEqual((code, len(lines)), (1, 1), stderr)
        self.assertIn("perform_eval called sys.exit()", lines[0])
        (self.exercises / "return_window_evaluator.py").write_text(
            "import re\n\n\n"
            "def perform_eval(run, example=None):\n"
            "    messages = (run.get('outputs') or {}).get('messages') or []\n"
            "    reply = messages[-1].get('content', '') if messages else ''\n"
            "    question = run['inputs']['messages'][-1]['content']\n"
            "    return {'wrong_return_window': bool(re.search(r'\\b(opened|used)\\b', question)) and bool(re.search(r'\\b30 days\\b', reply))}\n",
            encoding="utf-8",
        )
        code, lines, stderr = self.run_here("s1_evaluator")
        self.assertEqual((code, len(lines)), (1, 1), stderr)
        self.assertIn("not when its source is run on its own", lines[0])
        self.assertIn("name 're' is not defined", lines[0])

    def test_4c_importing_the_reference_evaluator_does_not_pass_here_either(self):
        # The sandbox keeps evaluators/online_evaluators.py (the check of s2_claim loads it), so the import works there.
        (self.exercises / "return_window_evaluator.py").write_text(
            "def perform_eval(run, example=None):\n    from evaluators.online_evaluators import perform_eval as reference\n\n    return reference(run, example)\n",
            encoding="utf-8",
        )
        code, lines, stderr = self.run_here("s1_evaluator")
        self.assertEqual((code, len(lines)), (1, 1), stderr)
        self.assertIn("it imports evaluators.online_evaluators, which is not part of Python's standard library", lines[0])

    def test_4d_a_damaged_data_file_is_named_and_restore_data_brings_it_back_without_the_answer_file(self):
        data = self.root / "workshop_modules" / "module_7" / "data"
        labels, original = data / ts.LABELS_FILE, (data / ts.LABELS_FILE).read_bytes()
        labels.write_text("{}", encoding="utf-8")
        code, lines, stderr = self.run_here("s2_report", "s2_claim", "s3_triage")
        self.assertEqual((code, len(lines)), (1, 3), stderr)
        for line in lines:
            self.assertIn(f"FAIL: the data file workshop_modules/module_7/data/{ts.LABELS_FILE} is missing or was changed", line)
            self.assertIn("check.py --restore-data", line)
        code, lines, stderr = self.run_here("--restore-data")
        self.assertEqual((code, lines), (0, [f"Restored workshop_modules/module_7/data/{ts.LABELS_FILE} from the generator."]), stderr)
        self.assertEqual(labels.read_bytes(), original)
        self.assertFalse((data / ts.ANSWERS_FILE).exists(), "the sandbox has no answer file, and the restore must not write one")
        code, lines, _ = self.run_here("s3_triage")
        self.assertIn("is not implemented yet", lines[0])

    def test_5_after_the_solve_step_every_check_passes(self):
        for name in EXERCISE_FILE_NAMES:  # what a solve script does: copy the kept solution over the stub
            shutil.copy(self.kept_solutions / name, self.exercises / name)
        code, lines, stderr = self.run_here(*FUNCTION_IDS)
        self.assertEqual(code, 0, stderr)
        self.assertEqual([line[:6] for line in lines], ["PASS: "] * len(FUNCTION_IDS))
        self.assertIn("flags 11 of 260 root runs", lines[0])


if __name__ == "__main__":
    unittest.main()
