"""No-network regression checks for case-matrix identity and safety."""
import unittest

from physics_harness.workflow.matrix import matrix_json
from physics_harness.workflow.planner import plan
from physics_harness.workflow.spec import WorkflowSpec
from physics_harness.workflow.validator import WorkflowValidationError

SHA = "a" * 40
OCI = "ghcr.io/test/build@sha256:" + "b" * 64


def payload(**overrides):
    data = {
        "schema_version": 1, "name": "Issue652 G6B Case Parallel",
        "profile": "parallel_cases", "source_sha": SHA, "oci_ref": OCI,
        "cases": [{"id": "417"}, {"id": "941"}],
        "max_parallel": 2, "timeout_minutes": 360,
        "artifact_prefix": "issue652-g6b", "end_time_s": 0.0001, "intervals": 460,
    }
    data.update(overrides)
    return data


class WorkflowPlanningTests(unittest.TestCase):
    def test_exact_two_independent_cases(self):
        spec = WorkflowSpec.from_dict(payload())
        execution = plan(spec)
        self.assertEqual(execution.matrix["include"], [{"case": "417"}, {"case": "941"}])
        self.assertEqual(execution.jobs, ("build", "cases", "aggregate"))
        self.assertEqual(execution.max_parallel, 2)
        self.assertEqual(execution.science_state, "HOLD")
        self.assertIn('"case":"417"', matrix_json(spec))

    def test_fail_closed(self):
        bad = [
            {"cases": [{"id": "417"}, {"id": "417"}]},
            {"cases": [{"id": "417"}]},
            {"max_parallel": 3},
            {"source_sha": "latest"},
            {"oci_ref": "ghcr.io/test/build:latest"},
            {"cases": [{"id": "../secret"}, {"id": "941"}]},
            {"timeout_minutes": 500},
            {"artifact_prefix": "../../unsafe"},
            {"build_script": "ci/build.py"},
            {"build_script": "ci/../build.py", "case_script": "ci/case.py"},
            {"end_time_s": 0.0001, "intervals": True},
            {"unknown": "field"},
        ]
        for override in bad:
            with self.subTest(override=override), self.assertRaises(WorkflowValidationError):
                WorkflowSpec.from_dict(payload(**override))

    def test_single_case_profile(self):
        spec = WorkflowSpec.from_dict(payload(
            profile="single_case", cases=[{"id": "417"}], max_parallel=1))
        self.assertEqual(spec.cases[0].id, "417")
        self.assertEqual(plan(spec).max_parallel, 1)
