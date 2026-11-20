"""Scope checks for the dedicated harness_code CI route."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github/workflows/harness-code.yml"
GENERAL = ROOT / ".github/workflows/ci.yml"
SOL = ROOT / ".github/workflows/sol-runtime-integration.yml"


class HarnessCodeCITests(unittest.TestCase):
    def test_dedicated_workflow_only_runs_code_local_pytest(self):
        source = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("name: Harness Code CI", source)
        self.assertIn("run: python -m pytest -q physics_harness/code/tests", source)
        self.assertEqual(source.count("      - name: Run only harness_code tests"), 1)
        self.assertNotIn("physics-opt", source)
        self.assertNotIn("cargo ", source)

    def test_repository_integration_runs_for_harness_only_and_sol_is_scoped(self):
        general = GENERAL.read_text(encoding="utf-8")
        sol = SOL.read_text(encoding="utf-8")
        self.assertNotIn("paths-ignore:", general)
        self.assertIn("  validate:\n", general)
        self.assertNotIn("  plasma_native_regression:\n", general)
        self.assertIn("      - 'physics_harness/ontology/**'", sol)
        self.assertIn("      - '.github/workflows/sol-runtime-integration.yml'", sol)


if __name__ == "__main__":
    unittest.main()
