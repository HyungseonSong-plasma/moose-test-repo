"""No-network authorization and observation behavior."""
import unittest

from physics_harness.workflow.dispatcher import dispatch
from physics_harness.workflow.monitor import snapshot
from physics_harness.workflow.validator import WorkflowValidationError


class Stub:
    def __init__(self):
        self.called = []
        self.info = {"path": ".github/workflows/physics-cases.yml", "state": "active"}

    def workflow(self, filename):
        self.called.append(("lookup", filename))
        return self.info

    def dispatch(self, filename, ref):
        self.called.append(("dispatch", filename, ref))

    def run(self, run_id):
        return {"head_sha": "a" * 40, "event": "workflow_dispatch",
                "status": "completed", "conclusion": "failure",
                "html_url": "https://github.com/example/repo/actions/runs/99"}

    def jobs(self, run_id):
        return [{"id": 6, "name": "case (417)", "status": "completed", "conclusion": "failure"},
                {"id": 7, "name": "case (941)", "status": "completed", "conclusion": "success"}]


class DispatcherTests(unittest.TestCase):
    def test_no_implicit_authorization(self):
        backend = Stub()
        with self.assertRaises(WorkflowValidationError):
            dispatch(backend, workflow_file="physics-cases.yml", ref="reviewed", authorize=False)
        self.assertEqual(backend.called, [])

    def test_registered_workflow_only_and_run_id_not_fabricated(self):
        backend = Stub()
        response = dispatch(backend, workflow_file="physics-cases.yml", ref="reviewed", authorize=True)
        self.assertEqual(response["status"], "DISPATCH_ACCEPTED")
        self.assertIsNone(response["run_id"])
        self.assertIn(("dispatch", "physics-cases.yml", "reviewed"), backend.called)
        backend.info = {"path": ".github/workflows/other.yml", "state": "active"}
        with self.assertRaises(WorkflowValidationError):
            dispatch(backend, workflow_file="physics-cases.yml", ref="reviewed", authorize=True)

    def test_failed_case_does_not_become_success(self):
        status = snapshot(Stub(), 99)
        self.assertEqual(status["conclusion"], "failure")
        self.assertEqual(status["jobs"][0]["conclusion"], "failure")
        self.assertEqual(status["jobs"][1]["conclusion"], "success")
        self.assertEqual(status["scientific_status"], "UNVERIFIED")
