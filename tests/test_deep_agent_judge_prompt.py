"""The aligned deep-agent judge prompt keeps the base rubric and adds each rule once, in place.

Run: uv run python -m unittest tests.test_deep_agent_judge_prompt
"""

import unittest

from evaluators.evaluators import (
    CORRECTNESS_PROMPT,
    DEEP_AGENT_CORRECTNESS_PROMPT,
    RULE_ANSWER_WHAT_WAS_ASKED,
    RULE_NO_INVENTED_ACTIONS,
)


class DeepAgentJudgePromptTest(unittest.TestCase):
    def test_is_the_base_prompt_plus_the_two_rules(self):
        self.assertEqual(
            len(DEEP_AGENT_CORRECTNESS_PROMPT),
            len(CORRECTNESS_PROMPT) + len(RULE_NO_INVENTED_ACTIONS) + len(RULE_ANSWER_WHAT_WAS_ASKED),
        )

    def test_rules_sit_in_the_rubric(self):
        rubric = DEEP_AGENT_CORRECTNESS_PROMPT.split("<Rubric>")[1].split("</Rubric>")[0]
        self.assertIn(RULE_NO_INVENTED_ACTIONS, rubric)
        self.assertIn(RULE_ANSWER_WHAT_WAS_ASKED, rubric)

    def test_formats_with_the_evaluator_arguments(self):
        text = DEEP_AGENT_CORRECTNESS_PROMPT.format(inputs="Q", outputs="A", reference_outputs="R")
        self.assertIn("<input>\nQ\n</input>", text)
        self.assertNotIn("{", text.split("<input>")[0])  # no stray placeholders in the rubric


if __name__ == "__main__":
    unittest.main()
