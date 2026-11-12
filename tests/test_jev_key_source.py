"""Jev's key comes from the Jev-capable sources first, and only names are ever printed.

Run: uv run python -m unittest tests.test_jev_key_source
"""

import os
import tempfile
import unittest
from unittest import mock

from utils.jev import jev_key_source

ALL = ("JEV_API_KEY", "JEV_WORKSPACE_ID", "LC_GATEWAY_KEY", "GATEWAY_ENV_FILE",
       "LANGSMITH_GATEWAY_API_KEY", "LANGSMITH_API_KEY_GATEWAY", "LANGSMITH_API_KEY")


def source(**env):
    clean = {k: v for k, v in os.environ.items() if k not in ALL}
    with mock.patch.dict(os.environ, {**clean, **env}, clear=True):
        found = jev_key_source()
    return found[0] if found else None


class JevKeySourceTest(unittest.TestCase):
    def test_jev_api_key_wins(self):
        self.assertEqual(source(JEV_API_KEY="a", LC_GATEWAY_KEY="b", LANGSMITH_GATEWAY_API_KEY="c"), "JEV_API_KEY")

    def test_lc_gateway_key_beats_the_project_gateway_key(self):
        # The 424 case: the project's Gateway key belongs to a workspace without Jev
        self.assertEqual(source(LC_GATEWAY_KEY="b", LANGSMITH_GATEWAY_API_KEY="c"), "LC_GATEWAY_KEY")

    def test_workspace_option_uses_the_langsmith_key(self):
        self.assertEqual(source(JEV_WORKSPACE_ID="ws", LANGSMITH_API_KEY="k", LC_GATEWAY_KEY="b"),
                         "LANGSMITH_API_KEY + JEV_WORKSPACE_ID")

    def test_gateway_env_file(self):
        with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as f:
            f.write("OPENAI_API_KEY=x\nexport LC_GATEWAY_KEY=from-file\n")
        try:
            self.assertEqual(source(GATEWAY_ENV_FILE=f.name, LANGSMITH_GATEWAY_API_KEY="c"), "LC_GATEWAY_KEY (GATEWAY_ENV_FILE)")
        finally:
            os.unlink(f.name)

    def test_falls_back_to_the_gateway_chain(self):
        self.assertEqual(source(LANGSMITH_GATEWAY_API_KEY="c", LANGSMITH_API_KEY="k"), "LANGSMITH_GATEWAY_API_KEY")

    def test_nothing_set(self):
        self.assertIsNone(source())


if __name__ == "__main__":
    unittest.main()
