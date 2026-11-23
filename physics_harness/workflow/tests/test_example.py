"""Literal S6-417/941 public plan is plan-only and SCIENCE_HOLD."""
from pathlib import Path
import unittest

from physics_harness.workflow.spec import load_spec
from physics_harness.workflow.planner import plan
from physics_harness.workflow.validator import WorkflowValidationError
from physics_harness.workflow.generator import render

ROOT = Path(__file__).resolve().parents[3]
EXAMPLE = ROOT / "physics_harness/workflow/examples/issue652-g6b-publicd100-plan.json"


class ConcreteCasePlanTests(unittest.TestCase):
    def test_original_100row_series_417_941_plan_not_authorized(self):
        spec = load_spec(EXAMPLE)
        self.assertEqual([case.id for case in spec.cases], ["417", "941"])
        self.assertEqual((spec.end_time_s, spec.intervals), (0.0001, 460))
        self.assertEqual(plan(spec).max_parallel, 2)
        self.assertEqual(plan(spec).science_state, "HOLD")
        with self.assertRaises(WorkflowValidationError, msg="unreviewed case scripts cannot generate"):
            render(spec, spec_path=EXAMPLE.relative_to(ROOT).as_posix(), root=ROOT)
