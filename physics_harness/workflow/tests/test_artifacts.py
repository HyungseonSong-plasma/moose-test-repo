"""Binary-only closure, cross-run provenance and science-HOLD tests."""
from pathlib import Path
import tempfile
import unittest

from physics_harness.workflow.aggregator import aggregate
from physics_harness.workflow.artifacts import record_build, record_case, verify_build
from physics_harness.workflow.spec import WorkflowSpec
from physics_harness.workflow.validator import WorkflowValidationError
from physics_harness.workflow.tests.test_planning import payload


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.spec = WorkflowSpec.from_dict(payload())
        self.binary = self.root / "build" / "physics-opt"
        self.binary.parent.mkdir()
        self.binary.write_bytes(b"\x7fELF" + b"binary-test-only")
        record_build(self.binary.parent, self.spec)

    def test_shared_source_bound_elf(self):
        digest = verify_build(self.binary.parent, self.spec)
        self.assertEqual(len(digest), 64)
        self.binary.write_bytes(b"\x7fELF" + b"modified")
        with self.assertRaises(WorkflowValidationError):
            verify_build(self.binary.parent, self.spec)

    def test_protected_plaintext_not_allowed_in_build_artifact(self):
        (self.binary.parent / "private_rates.txt").write_text("secret-rate-placeholder")
        with self.assertRaises(WorkflowValidationError):
            verify_build(self.binary.parent, self.spec)

    def test_two_cases_zero_exit_does_not_approve_science(self):
        digest = verify_build(self.binary.parent, self.spec)
        receipts = self.root / "receipts"
        receipts.mkdir()
        for case in ("417", "941"):
            record_case(receipts / f"physics-case-receipt-{case}.json",
                        spec=self.spec, case_id=case, exit_code=0,
                        build_manifest_sha256=digest)
        result = aggregate(self.spec, receipts)
        self.assertEqual(result["execution_status"], "EXIT_ZERO_UNVERIFIED")
        self.assertEqual(result["science_status"], "HOLD")
        self.assertEqual(result["time_coverage_status"], "UNVERIFIED")
        (receipts / "physics-case-receipt-941.json").unlink()
        self.assertEqual(aggregate(self.spec, receipts)["cases"]["941"], "MISSING")
        self.assertEqual(aggregate(self.spec, receipts)["execution_status"], "HOLD")
