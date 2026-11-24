"""The wrong-return-window online evaluator: right on the Module 7 seed, and self-contained as pasted text.

`evaluators/online_evaluators.py::perform_eval` is the function a learner pastes into a LangSmith
Code Evaluator, where it runs as source text on its own. The tests therefore check two things:

1. The answer. On the 260 root runs of the seed it flags exactly the 11 traces of the answer key
   (`workshop_modules/module_7/data/answers.json`), while a naive "the reply contains 30 days"
   check flags 23. These are design constants of sections 6.3 and 6.6 of
   ``docs/2026-11-19-module-7-monitoring-governance-prd.md``.
2. The packaging. `WRONG_RETURN_WINDOW_SOURCE` compiles with nothing else around it, defines
   `perform_eval(run, example=None)`, imports standard-library modules only, and behaves like the
   imported function on every root run.

Nothing here uses the network: every socket connect is refused.

Run: uv run python -m unittest tests.test_online_evaluators
"""

import ast
import builtins
import dis
import inspect
import json
import socket
import sys
import unittest
from unittest import mock

import evaluators
from evaluators import WRONG_RETURN_WINDOW_SOURCE, wrong_return_window_evaluator
from evaluators import online_evaluators
from utils import trace_seeding as ts

KEY = "wrong_return_window"
FLAGGED = {KEY: True}
NOT_FLAGGED = {KEY: False}

_no_network = mock.patch.object(socket.socket, "connect", side_effect=AssertionError("this test must not open a socket"))


def setUpModule():
    _no_network.start()


def tearDownModule():
    _no_network.stop()


def naive_perform_eval(run, example=None):
    """The first attempt Section 1 shows before the reference: flag every reply that contains "30 days"."""
    messages = (run.get("outputs") or {}).get("messages") or []
    return {KEY: bool(messages) and "30 days" in str(messages[-1].get("content") or "")}


def compiled_copy():
    """`perform_eval` built from the exported source text alone, as LangSmith would build it."""
    namespace = {}
    exec(compile(WRONG_RETURN_WINDOW_SOURCE, "<WRONG_RETURN_WINDOW_SOURCE>", "exec"), namespace)
    return namespace


def run_with(question, reply, reply_type="ai"):
    return {
        "inputs": {"messages": [{"role": "user", "content": question}]},
        "outputs": {"messages": [{"type": "human", "content": question}, {"type": reply_type, "content": reply}], "files": {}},
    }


OPENED_QUESTION = "I opened my laptop from order ORD-2024-0078 last week. How long do I have to return it?"
THIRTY_DAYS_REPLY = "You have 30 days from delivery to return your laptop."


class SeedAnswerTest(unittest.TestCase):
    """The evaluator against the committed seed and its answer key."""

    @classmethod
    def setUpClass(cls):
        cls.seed = ts.load_seed()
        cls.roots = ts.root_runs(cls.seed)
        cls.answers = json.loads((ts.DATA / ts.ANSWERS_FILE).read_text(encoding="utf-8"))

    def flagged_keys(self, perform_eval, runs=None):
        return sorted(ts.trace_key(run) for run in (self.roots if runs is None else runs) if perform_eval(run)[KEY])

    def test_the_seed_has_260_root_runs(self):
        self.assertEqual(len(self.roots), 260)

    def test_naive_check_flags_23_root_runs(self):
        flagged = self.flagged_keys(naive_perform_eval)
        self.assertEqual(len(flagged), 23)
        self.assertEqual(len(flagged), self.answers["reference"]["s1_evaluator"]["naive_flagged"])

    def test_reference_flags_the_11_traces_of_the_answer_key(self):
        flagged = self.flagged_keys(wrong_return_window_evaluator)
        self.assertEqual(len(flagged), 11)
        self.assertEqual(flagged, sorted(self.answers["s1_evaluator"]["flagged_trace_keys"]))

    def test_the_11_are_a_subset_of_the_naive_23_and_the_other_12_are_about_unopened_items(self):
        naive = set(self.flagged_keys(naive_perform_eval))
        reference = set(self.flagged_keys(wrong_return_window_evaluator))
        self.assertLess(reference, naive)
        self.assertEqual(len(naive - reference), self.answers["reference"]["s1_evaluator"]["naive_flagged_correct_answers"])
        by_key = {ts.trace_key(run): run for run in self.roots}
        for key in naive - reference:
            question = by_key[key]["inputs"]["messages"][-1]["content"].lower()
            self.assertTrue("unopened" in question or "sealed" in question, f"{key}: {question}")

    def test_every_result_is_one_boolean_under_the_feedback_key(self):
        for run in self.roots:
            result = wrong_return_window_evaluator(run)
            self.assertEqual(list(result), [KEY], ts.trace_key(run))
            self.assertIs(type(result[KEY]), bool, ts.trace_key(run))

    def test_agrees_with_the_rule_behind_the_answer_key_on_every_root_run(self):
        # `utils/trace_seeding.py` computes the answer key with its own private rule; its docstring
        # promises that a unit test compares the two. This is that test.
        for run in self.roots:
            self.assertEqual(wrong_return_window_evaluator(run)[KEY], ts._is_wrong_return_window(run), ts.trace_key(run))

    def test_the_13_failed_root_runs_have_empty_outputs_and_are_not_flagged(self):
        failed = [run for run in self.roots if run.get("error")]
        self.assertEqual(len(failed), 13)
        for run in failed:
            self.assertFalse(run["outputs"], ts.trace_key(run))
            self.assertEqual(wrong_return_window_evaluator(run), NOT_FLAGGED, ts.trace_key(run))

    def test_no_run_of_the_seed_raises_and_child_runs_are_flagged_only_inside_the_11_traces(self):
        # A rule without a root-run filter hands every span to the evaluator, so it must cope with
        # all of them. Some child runs are flagged as well, because a specialist's run carries the
        # same question and the same wrong reply in the same `messages` shape as the root run. That
        # is expected, and it is why Section 1 attaches the evaluator with a filter on the root run:
        # without the filter one wrong answer would be counted several times.
        children = [run for run in self.seed["runs"] if run["parent_run_id"] is not None]
        self.assertGreater(len(children), 3000)
        flagged = [run for run in children if wrong_return_window_evaluator(run)[KEY]]
        self.assertEqual(sorted({ts.trace_key(run) for run in flagged}), sorted(self.answers["s1_evaluator"]["flagged_trace_keys"]))
        self.assertEqual({run["run_type"] for run in flagged}, {"chain"})
        self.assertIn("product-policy-specialist", {run["name"] for run in flagged})

    def test_follow_up_sets_4_flagged_before_the_fix_and_0_after(self):
        follow = ts.load_followups(self.seed)
        expected = self.answers["reference"]["s3_followup"]
        before = self.flagged_keys(wrong_return_window_evaluator, ts.root_runs(follow["before_fix"]["runs"]))
        after = self.flagged_keys(wrong_return_window_evaluator, ts.root_runs(follow["after_fix"]["runs"]))
        self.assertEqual((len(before), len(after)), (4, 0))
        self.assertEqual((len(before), len(after)), (expected["before_fix_flagged"], expected["after_fix_flagged"]))

    def test_the_compiled_source_gives_the_same_result_on_every_root_run(self):
        pasted = compiled_copy()["perform_eval"]
        self.assertIsNot(pasted, wrong_return_window_evaluator)
        for run in self.roots:
            self.assertEqual(pasted(run), wrong_return_window_evaluator(run), ts.trace_key(run))
        self.assertEqual(self.flagged_keys(pasted), sorted(self.answers["s1_evaluator"]["flagged_trace_keys"]))


class ContractTest(unittest.TestCase):
    """Small hand-made runs: the rule itself, and the shapes that must not raise."""

    def test_opened_question_with_a_30_day_reply_is_flagged(self):
        self.assertEqual(wrong_return_window_evaluator(run_with(OPENED_QUESTION, THIRTY_DAYS_REPLY)), FLAGGED)

    def test_used_counts_like_opened(self):
        question = "I've already used the mouse a few times. What is the return window?"
        self.assertEqual(wrong_return_window_evaluator(run_with(question, THIRTY_DAYS_REPLY)), FLAGGED)

    def test_opened_question_with_a_14_day_reply_is_not_flagged(self):
        reply = "Because your laptop has been opened, our Return Policy gives you 14 days from delivery to return it."
        self.assertEqual(wrong_return_window_evaluator(run_with(OPENED_QUESTION, reply)), NOT_FLAGGED)

    def test_unopened_and_unused_are_not_opened_or_used(self):
        for question in (
            "My laptop is still unopened. How long do I have to return it?",
            "I never took it out of its box; it is unused and sealed. How many days do I have to return it?",
            "I'd like to return an UNOPENED laptop. By when do I need to send it back?",
        ):
            self.assertEqual(wrong_return_window_evaluator(run_with(question, THIRTY_DAYS_REPLY)), NOT_FLAGGED, question)

    def test_wording_variants(self):
        self.assertEqual(wrong_return_window_evaluator(run_with("The box has been OPENED. Can I return it?", "There is a 30-day return window.")), FLAGGED)
        self.assertEqual(wrong_return_window_evaluator(run_with(OPENED_QUESTION, "Your order shipped 30 minutes ago; delivery takes 3 days.")), NOT_FLAGGED)
        self.assertEqual(wrong_return_window_evaluator(run_with(OPENED_QUESTION, "Order 30 arrives in 130 days.")), NOT_FLAGGED)

    def test_outputs_of_none_returns_false(self):
        run = {"inputs": {"messages": [{"role": "user", "content": OPENED_QUESTION}]}, "outputs": None}
        self.assertEqual(wrong_return_window_evaluator(run), NOT_FLAGGED)

    def test_shapes_that_must_not_raise(self):
        question = {"role": "user", "content": OPENED_QUESTION}
        for run in (
            {},
            {"inputs": None, "outputs": None},
            {"inputs": {}, "outputs": {}},
            {"inputs": {"messages": [question]}},
            {"inputs": {"messages": [question]}, "outputs": {}},
            {"inputs": {"messages": [question]}, "outputs": {"messages": []}},
            {"inputs": {"messages": [question]}, "outputs": {"messages": None}},
            {"inputs": {"messages": [question]}, "outputs": {"messages": [None]}},
            {"inputs": {"messages": [question]}, "outputs": {"messages": ["30 days"]}},
            {"inputs": {"messages": [question]}, "outputs": {"messages": [{"type": "ai", "content": None}]}},
            {"inputs": {"messages": [question]}, "outputs": {"messages": [{"type": "ai"}]}},
            {"inputs": {"messages": []}, "outputs": {"messages": [{"type": "ai", "content": THIRTY_DAYS_REPLY}]}},
            {"inputs": {"messages": "not a list"}, "outputs": {"messages": [{"type": "ai", "content": THIRTY_DAYS_REPLY}]}},
            {"inputs": {"input": OPENED_QUESTION}, "outputs": {"output": THIRTY_DAYS_REPLY}},
            {"inputs": "text", "outputs": "text"},
            None,
        ):
            self.assertEqual(wrong_return_window_evaluator(run), NOT_FLAGGED, repr(run)[:80])

    def test_a_turn_that_does_not_end_on_an_agent_reply_is_not_flagged(self):
        # For example a turn that stops on a tool message: there is no reply to judge yet.
        self.assertEqual(wrong_return_window_evaluator(run_with(OPENED_QUESTION, THIRTY_DAYS_REPLY, reply_type="tool")), NOT_FLAGGED)

    def test_only_the_newest_customer_message_and_the_last_reply_are_read(self):
        # Second turn of a conversation: the inputs hold the new message only, the outputs hold the whole conversation.
        run = {
            "inputs": {"messages": [{"role": "user", "content": "Thanks, that's all I needed."}]},
            "outputs": {
                "messages": [
                    {"type": "human", "content": OPENED_QUESTION},
                    {"type": "ai", "content": THIRTY_DAYS_REPLY},
                    {"type": "human", "content": "Thanks, that's all I needed."},
                    {"type": "ai", "content": "You're welcome! Is there anything else I can help you with?"},
                ]
            },
        }
        self.assertEqual(wrong_return_window_evaluator(run), NOT_FLAGGED)

    def test_other_message_shapes_are_read(self):
        blocks = {"inputs": {"messages": [{"role": "user", "content": [{"type": "text", "text": OPENED_QUESTION}]}]}, "outputs": {"messages": [{"role": "assistant", "content": [{"type": "text", "text": THIRTY_DAYS_REPLY}]}]}}
        self.assertEqual(wrong_return_window_evaluator(blocks), FLAGGED)
        serialized = {
            "inputs": {"messages": [{"lc": 1, "type": "constructor", "id": ["langchain", "schema", "messages", "HumanMessage"], "kwargs": {"content": OPENED_QUESTION, "type": "human"}}]},
            "outputs": {"messages": [{"lc": 1, "type": "constructor", "id": ["langchain", "schema", "messages", "AIMessage"], "kwargs": {"content": THIRTY_DAYS_REPLY, "type": "ai"}}]},
        }
        self.assertEqual(wrong_return_window_evaluator(serialized), FLAGGED)

    def test_accepts_the_second_argument_langsmith_passes(self):
        run = run_with(OPENED_QUESTION, THIRTY_DAYS_REPLY)
        self.assertEqual(wrong_return_window_evaluator(run, None), FLAGGED)
        self.assertEqual(wrong_return_window_evaluator(run, {"inputs": {}, "outputs": {}}), FLAGGED)

    def test_does_not_change_the_run(self):
        run = run_with(OPENED_QUESTION, THIRTY_DAYS_REPLY)
        before = json.dumps(run, sort_keys=True)
        wrong_return_window_evaluator(run)
        self.assertEqual(json.dumps(run, sort_keys=True), before)


class SourceTest(unittest.TestCase):
    """`WRONG_RETURN_WINDOW_SOURCE` is what runs in LangSmith, so it has to stand alone."""

    def test_the_package_exports_an_alias_of_perform_eval(self):
        self.assertIs(wrong_return_window_evaluator, online_evaluators.perform_eval)
        self.assertIn("wrong_return_window_evaluator", evaluators.__all__)
        self.assertIn("WRONG_RETURN_WINDOW_SOURCE", evaluators.__all__)
        self.assertNotIn("perform_eval", evaluators.__all__)

    def test_source_is_the_source_of_the_function(self):
        self.assertEqual(WRONG_RETURN_WINDOW_SOURCE, inspect.getsource(online_evaluators.perform_eval))
        self.assertTrue(WRONG_RETURN_WINDOW_SOURCE.startswith("def perform_eval(run, example=None):\n"))
        self.assertTrue(WRONG_RETURN_WINDOW_SOURCE.endswith("\n"))

    def test_source_compiles_on_its_own_and_defines_perform_eval(self):
        namespace = compiled_copy()
        self.assertTrue(callable(namespace.get("perform_eval")))
        parameters = inspect.signature(namespace["perform_eval"]).parameters
        self.assertEqual(list(parameters), ["run", "example"])
        self.assertIs(parameters["example"].default, None)
        self.assertEqual(namespace["perform_eval"](run_with(OPENED_QUESTION, THIRTY_DAYS_REPLY)), FLAGGED)

    def test_source_is_one_top_level_function_and_nothing_else(self):
        body = ast.parse(WRONG_RETURN_WINDOW_SOURCE).body
        self.assertEqual([type(node).__name__ for node in body], ["FunctionDef"])
        self.assertEqual(body[0].name, "perform_eval")
        self.assertEqual(body[0].decorator_list, [])

    def test_source_imports_standard_library_modules_only(self):
        imported = set()
        for node in ast.walk(ast.parse(WRONG_RETURN_WINDOW_SOURCE)):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                self.assertEqual(node.level, 0, "no relative import in pasted code")
                imported.add((node.module or "").split(".")[0])
        self.assertLessEqual(imported, set(sys.stdlib_module_names), f"not standard library: {sorted(imported - set(sys.stdlib_module_names))}")

    def test_source_uses_no_name_from_outside_its_own_body(self):
        # A helper or constant defined at module level in `online_evaluators.py` would not exist in
        # LangSmith and would raise NameError there, possibly only on a rarely taken path. So every
        # global name the function's bytecode loads (nested functions included) must be a builtin.
        code = compile(WRONG_RETURN_WINDOW_SOURCE, "<WRONG_RETURN_WINDOW_SOURCE>", "exec")
        function_code = next(const for const in code.co_consts if inspect.iscode(const))

        def global_names(code_object):
            names = {instruction.argval for instruction in dis.get_instructions(code_object) if instruction.opname in ("LOAD_GLOBAL", "LOAD_NAME")}
            for const in code_object.co_consts:
                if inspect.iscode(const):
                    names |= global_names(const)
            return names

        loaded = global_names(function_code)
        self.assertTrue(loaded, "expected the function to use at least one builtin, such as isinstance")
        self.assertLessEqual(loaded, set(dir(builtins)), f"names from outside the function: {sorted(loaded - set(dir(builtins)))}")

    def test_the_module_itself_imports_standard_library_modules_only(self):
        tree = ast.parse(inspect.getsource(online_evaluators))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add((node.module or "").split(".")[0])
        self.assertLessEqual(imported, set(sys.stdlib_module_names))


if __name__ == "__main__":
    unittest.main()
