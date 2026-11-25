"""Scope checks for the dedicated harness_code CI route."""

from pathlib import Path
from fnmatch import fnmatchcase
import re
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

    def test_controller_execution_control_plane_changes_trigger_code_tests(self):
        source = WORKFLOW.read_text(encoding="utf-8")
        header = source.split("\npermissions:", 1)[0]
        for event in ("push", "pull_request"):
            section = header.split(f"\n  {event}:\n", 1)[1]
            section = re.split(r"(?m)^  [a-z_]+:", section, maxsplit=1)[0]
            entries = section.split("    paths:\n", 1)[1].strip("\n").splitlines()
            patterns = []
            for entry in entries:
                if not entry.strip():
                    continue
                match = re.fullmatch(r"      - '([^'\n]+)'", entry)
                self.assertIsNotNone(match, entry)
                patterns.append(match.group(1))
            for path in ("physics_harness/execution/controller_orchestrator.py",
                         "physics_harness/execution/controller_durable_state.py",
                         "physics_harness/execution/connector_policy_probe.py"):
                included = False
                for pattern in patterns:
                    if fnmatchcase(path, pattern.removeprefix("!")):
                        included = not pattern.startswith("!")
                self.assertTrue(included, f"{event}: {path}")

    def test_shared_cli_library_changes_trigger_code_consumer_tests(self):
        source = WORKFLOW.read_text(encoding="utf-8")
        self.assertEqual(source.count("      - 'libs/command_execution/**'"), 2)

    def test_shared_evidence_library_changes_trigger_code_consumer_tests(self):
        source = WORKFLOW.read_text(encoding="utf-8")
        self.assertEqual(source.count("      - 'libs/git_evidence/**'"), 2)

    def test_shared_test_verification_changes_trigger_code_consumer_tests(self):
        source = WORKFLOW.read_text(encoding="utf-8")
        self.assertEqual(source.count("      - 'libs/test_verification/**'"), 2)

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
