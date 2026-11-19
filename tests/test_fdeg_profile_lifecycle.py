"""Pre-retirement immutable code1 Functional/Transition evidence and lifecycle controls."""
from __future__ import annotations
import copy
from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ci" / "guards"))
import fdeg_profile_lifecycle as lifecycle
import fdeg_retirement_snapshot as snapshot


class Code1ProfileLifecycleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.meta, cls.archive = lifecycle.load(ROOT)

    def test_source_and_active_profiles_match_frozen_archive(self):
        result = lifecycle.validate(ROOT)
        self.assertIn(result["lifecycle_status"], {"PRE_RETIREMENT", "RETIRED"})
        self.assertFalse(result["retirement_authorized_by_guard"])
        exists = result["lifecycle_status"] == "PRE_RETIREMENT"
        self.assertEqual((ROOT / self.archive["capture"]["source_file"]["path"]).exists(), exists)
        self.assertEqual((ROOT / self.archive["capture"]["header_file"]["path"]).exists(), exists)

    def test_historical_both_with_kernel_is_not_removal_parity(self):
        self.assertEqual(self.archive["capture"]["historical_qualification_scope"],
                         "BOTH_LANES_USED_KERNEL_NOT_KERNEL_REMOVAL_PARITY")
        self.assertEqual(len(self.archive["capture"]["qualified_runs"]), 2)
        self.assertEqual(self.meta["scientific_equivalence"], "NOT_PROVEN")
        self.assertEqual(self.meta["removal_approval"],
                         "NOT_GRANTED" if self.meta["status"] == "PRE_RETIREMENT"
                         else "EXPLICIT_OWNER_APPROVAL")

    def test_reject_changed_baseline_commit(self):
        meta = copy.deepcopy(self.meta)
        meta["baseline_commit"] = "a" * 40
        with self.assertRaisesRegex(ValueError, "LIFECYCLE_BASELINE_IDENTITY_MISMATCH"):
            lifecycle.validate(ROOT, meta=meta)

    def test_reject_false_parity_promotion(self):
        data = copy.deepcopy(self.archive)
        data["capture"]["historical_qualification_scope"] = "REMOVAL_PARITY_PASS"
        with self.assertRaisesRegex(ValueError, "LIFECYCLE_ARCHIVE_CONTENT_MISMATCH"):
            lifecycle.validate(ROOT, archive=data)

    def test_reject_modified_archived_contract(self):
        data = copy.deepcopy(self.archive)
        data["functional_profile"]["capability"] = "CHANGED"
        with self.assertRaisesRegex(ValueError, "LIFECYCLE_ARCHIVE_CONTENT_MISMATCH"):
            lifecycle.validate(ROOT, archive=data)

    def test_reject_inconsistent_lifecycle_state(self):
        meta = copy.deepcopy(self.meta)
        if meta["status"] == "PRE_RETIREMENT":
            meta["status"] = "RETIRED"
            reason = "LIFECYCLE_RETIRED_BUT_IMPLEMENTATION_ACTIVE"
        else:
            meta["status"] = "PRE_RETIREMENT"
            reason = "LIFECYCLE_PRE_RETIREMENT_SCOPE_INVALID"
        with self.assertRaisesRegex(ValueError, reason):
            lifecycle.validate(ROOT, meta=meta)

    def test_reject_unproven_numeric_pass(self):
        meta = copy.deepcopy(self.meta)
        meta["scientific_equivalence"] = "PASS"
        with self.assertRaisesRegex(ValueError, "LIFECYCLE_EQUIVALENCE_FALSE_PROMOTION"):
            lifecycle.validate(ROOT, meta=meta)

    def test_snapshot_serializer_keeps_hold(self):
        result = snapshot.serialized({"safe_delete":"HOLD","execution_status":"NOT_EXECUTED"})
        self.assertIn(b'"safe_delete": "HOLD"', result)
        self.assertIn(b'"execution_status": "NOT_EXECUTED"', result)


if __name__ == "__main__":
    unittest.main()
