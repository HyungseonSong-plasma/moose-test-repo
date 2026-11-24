"""No-network reviewable YAML composition tests."""
from pathlib import Path
import json
import tempfile
import unittest

from physics_harness.workflow.generator import render
from physics_harness.workflow.spec import WorkflowSpec
from physics_harness.workflow.validator import WorkflowValidationError
from physics_harness.workflow.tests.test_planning import payload


class GeneratorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "ci").mkdir()
        (self.root / "ci" / "workflow-case.json").write_text(json.dumps(payload()))
        (self.root / "ci" / "native-build.py").write_text("pass\n")
        (self.root / "ci" / "native-case.py").write_text("pass\n")
        self.spec = WorkflowSpec.from_dict(payload(
            build_script="ci/native-build.py", case_script="ci/native-case.py"))

    def test_case_matrix_produces_two_independent_runner_jobs(self):
        workflow = render(self.spec, spec_path="ci/workflow-case.json", root=self.root)
        self.assertIn("  build:\n", workflow)
        self.assertIn("  cases:\n", workflow)
        self.assertIn("  aggregate:\n", workflow)
        self.assertEqual(workflow.count("      - name: Build once under reviewed OCI contract"), 1)
        self.assertIn("      fail-fast: false", workflow)
        self.assertIn("      max-parallel: 2", workflow)
        self.assertIn("          - case: '417'", workflow)
        self.assertIn("          - case: '941'", workflow)
        self.assertIn("name: Issue652 G6B Case Parallel", workflow)
        self.assertIn("ref: " + "a" * 40, workflow)
        self.assertIn("if-no-files-found: error", workflow)
        self.assertNotIn("secrets.", workflow)
        self.assertNotIn("pull_request:", workflow)
        self.assertNotIn("@@", workflow)

    def test_reviewed_scripts_mandatory(self):
        no_scripts = WorkflowSpec.from_dict(payload())
        with self.assertRaises(WorkflowValidationError):
            render(no_scripts, spec_path="ci/workflow-case.json", root=self.root)

    def test_missing_source_or_script_rejected(self):
        (self.root / "ci" / "native-case.py").unlink()
        with self.assertRaises(WorkflowValidationError):
            render(self.spec, spec_path="ci/workflow-case.json", root=self.root)
        with self.assertRaises(WorkflowValidationError):
            render(self.spec, spec_path="ci/../ci/workflow-case.json", root=self.root)
