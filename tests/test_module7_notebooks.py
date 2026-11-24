"""The four Module 7 notebooks are well formed and are exactly what their builder writes.

Checks, per notebook: valid nbformat 4; no outputs and no execution counts; cell ids `cell-000`,
`cell-001`, ...; every code cell compiles (top-level `await` allowed); every local `<img src>` and
relative Markdown link resolves; the first cell starts with the title of PRD section 5 and the last
cell holds the Recap; no em or en dash in the prose; no code cell calls `generate_insights` or passes
`priority=`. A last test runs the builder into a temporary folder and compares the bytes with the
committed notebooks, so an edit made to a notebook instead of the builder fails here.

The notebooks are not executed here: `scripts/verify_module7_offline.py` does that. No network.

Run: uv run python -m unittest tests.test_module7_notebooks
"""

import ast
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import nbformat

REPO = Path(__file__).resolve().parents[1]
MODULE_DIR = REPO / "workshop_modules" / "module_7"
BUILDER = REPO / "scripts" / "notebook_builders" / "build_module7.py"

# PRD section 5: notebook -> title line of its first cell.
TITLES = {
    "section_1_online_evals_and_alerts.ipynb": "# Module 7, Section 1: Online Evals, Alerts and Routing",
    "section_2_insights.ipynb": "# Module 7, Section 2: Insights",
    "section_3_engine.ipynb": "# Module 7, Section 3: Engine",
    "section_4_gateway_and_governance.ipynb": "# Module 7, Section 4: LLM Gateway and Governance",
}

IMG_SRC = re.compile(r'<img src="([^"]+)"')
MD_LINK = re.compile(r"\]\(([^)\s]+)\)")


def _local(target: str) -> bool:
    return not re.match(r"[a-z][a-z0-9+.-]*:|#|/", target)


class TestModule7Notebooks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.notebooks = {name: nbformat.read(MODULE_DIR / name, as_version=4) for name in TITLES}

    def test_valid_nbformat(self):
        for name, nb in self.notebooks.items():
            with self.subTest(notebook=name):
                nbformat.validate(nb)
                self.assertEqual(nb.metadata["kernelspec"]["name"], "python3")

    def test_no_outputs(self):
        for name, nb in self.notebooks.items():
            for index, cell in enumerate(nb.cells):
                if cell.cell_type == "code":
                    with self.subTest(notebook=name, cell=index):
                        self.assertEqual(cell.outputs, [])
                        self.assertIsNone(cell.execution_count)

    def test_stable_cell_ids(self):
        for name, nb in self.notebooks.items():
            with self.subTest(notebook=name):
                self.assertEqual([cell.id for cell in nb.cells], [f"cell-{i:03d}" for i in range(len(nb.cells))])

    def test_code_cells_compile(self):
        for name, nb in self.notebooks.items():
            for index, cell in enumerate(nb.cells):
                if cell.cell_type == "code":
                    with self.subTest(notebook=name, cell=index):
                        compile(cell.source, f"{name}:cell-{index:03d}", "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)

    def test_images_and_relative_links_resolve(self):
        checked = 0
        for name, nb in self.notebooks.items():
            for index, cell in enumerate(nb.cells):
                if cell.cell_type != "markdown":
                    continue
                for target in IMG_SRC.findall(cell.source) + MD_LINK.findall(cell.source):
                    if not _local(target):
                        continue
                    path = (MODULE_DIR / target.split("#")[0]).resolve()
                    with self.subTest(notebook=name, cell=index, target=target):
                        self.assertTrue(path.exists(), f"{target} does not exist")
                    checked += 1
        self.assertGreater(checked, 0, "expected at least one local image or link")

    def test_first_cell_and_recap(self):
        for name, nb in self.notebooks.items():
            with self.subTest(notebook=name):
                self.assertEqual(nb.cells[0].cell_type, "markdown")
                self.assertTrue(nb.cells[0].source.startswith(TITLES[name]), nb.cells[0].source.splitlines()[0])
                self.assertEqual(nb.cells[-1].cell_type, "markdown")
                self.assertIn("## Recap", nb.cells[-1].source)

    def test_section_4_ends_with_where_to_go_next(self):
        nb = self.notebooks["section_4_gateway_and_governance.ipynb"]
        headings = [line for cell in nb.cells if cell.cell_type == "markdown" for line in cell.source.splitlines()
                    if re.match(r"## \d+\. ", line)]
        self.assertEqual(headings[-1], "## 8. Where to go next")

    def test_no_dashes_in_prose(self):
        for name, nb in self.notebooks.items():
            for index, cell in enumerate(nb.cells):
                if cell.cell_type == "markdown":
                    with self.subTest(notebook=name, cell=index):
                        self.assertNotRegex(cell.source, "[–—]")

    def test_no_forbidden_calls(self):
        # CLAUDE.md, Module 7: never call generate_insights; never pass priority= to list_project_issues.
        for name, nb in self.notebooks.items():
            for index, cell in enumerate(nb.cells):
                if cell.cell_type == "code":
                    with self.subTest(notebook=name, cell=index):
                        self.assertNotIn("generate_insights(", cell.source)
                        self.assertNotIn("poll_insights(", cell.source)
                        self.assertNotIn("priority=", cell.source)

    def test_builder_reproduces_committed_notebooks(self):
        with tempfile.TemporaryDirectory() as out:
            result = subprocess.run([sys.executable, str(BUILDER), out], cwd=REPO, capture_output=True, text=True, timeout=120)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            built = sorted(p.name for p in Path(out).glob("*.ipynb"))
            self.assertEqual(built, sorted(TITLES))
            for name in built:
                with self.subTest(notebook=name):
                    self.assertEqual((Path(out) / name).read_bytes(), (MODULE_DIR / name).read_bytes(),
                                     f"{name} differs from the builder's output: edit build_module7.py and rebuild")


if __name__ == "__main__":
    unittest.main()
