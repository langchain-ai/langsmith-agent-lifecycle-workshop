"""jev_correctness_evaluator: one score per rubric question, and correct only if all clear the threshold.

Uses a fake Jev, so no network or key. Run: uv run python -m unittest tests.test_jev_correctness_evaluator
"""

import unittest
from types import SimpleNamespace
from unittest import mock

import utils.jev
from evaluators import jev_correctness_evaluator
from evaluators.evaluators import JEV_RUBRIC_QUESTIONS, JEV_THRESHOLD


def fake_jev(probabilities):
    seen = {}

    class Fake:
        def invoke(self, request):
            seen.update(request)
            return SimpleNamespace(nouls={k: SimpleNamespace(noul=p) for k, p in probabilities.items()})

    return Fake(), seen


def grade(probabilities):
    fake, seen = fake_jev(probabilities)
    with mock.patch.object(utils.jev, "jev_classifier", lambda: fake):
        result = jev_correctness_evaluator(
            inputs={"messages": [{"role": "user", "content": "Q?"}]},
            outputs={"messages": [{"role": "assistant", "content": "A."}]},
            reference_outputs={"messages": [{"role": "assistant", "content": "R."}]},
        )
    return {r["key"]: r["score"] for r in result["results"]}, seen


class JevCorrectnessEvaluatorTest(unittest.TestCase):
    def test_all_questions_clear_the_threshold(self):
        scores, seen = grade({k: 0.9 for k in JEV_RUBRIC_QUESTIONS})
        self.assertEqual(scores["correctness"], 1)
        self.assertEqual(set(seen["questions"]), set(JEV_RUBRIC_QUESTIONS))
        self.assertIn("Agent answer:\nA.", seen["state"])

    def test_one_low_question_fails_the_answer(self):
        probabilities = {k: 0.9 for k in JEV_RUBRIC_QUESTIONS} | {"possible_actions": JEV_THRESHOLD - 0.01}
        scores, _ = grade(probabilities)
        self.assertEqual(scores["correctness"], 0)
        self.assertEqual(scores["possible_actions"], JEV_THRESHOLD - 0.01)

    def test_refusals_count_as_answering(self):
        false_meaning = JEV_RUBRIC_QUESTIONS["answers_question"].criteria.false
        self.assertIn("belongs to a different customer", false_meaning)


if __name__ == "__main__":
    unittest.main()
