"""P0 positive and fail-closed controls for Native FVKernel full-type census."""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ci/guards"))
from fvkernel_native_usage_census import (  # noqa: E402
    source_owners, summarize_clean_registration_trace,
)

RAW = (b"P5X_PRELOAD_READY\n"
       b"P5X_REGISTER\tFVKernel\tneutral\tNeutralKernel\n"
       b"P5X_REGISTER\tFVKernel\texternal\tFrameworkKernel\n"
       b"P5X_REGISTER\tFVBC\twall\tWallBC\n"
       b"P5X_REGISTER\tFEBoundaryCondition\te_wall\tElectronBC\n")


class NativeSourceUsageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        (self.folder / "Neutral.C").write_text(
            'registerMooseObject("PhysicsApp", NeutralKernel);\n'
        )
        (self.folder / "Unused.C").write_text(
            'registerMooseObject("PhysicsApp", UnusedKernel);\n'
        )

    def check(self, raw=RAW, *, digest=None, count=4):
        return summarize_clean_registration_trace(
            raw, self.folder,
            source_head="a"*40, binary_sha256="b"*64,
            registration_log_sha256=digest or hashlib.sha256(raw).hexdigest(),
            reported_event_count=count,
        )

    def test_full_trace_and_unobserved_are_not_safe_to_delete(self):
        result = self.check()
        self.assertEqual(result["observed_all_events"], 4)
        self.assertEqual(result["event_family_counts"]["FVKernel"], 2)
        self.assertEqual(result["other_source_or_framework_type_counts"],
                         {"FrameworkKernel": 1})
        rows = {row["source_file"].split("/")[-1]: row
                for row in result["source_files"]}
        self.assertEqual(rows["Neutral.C"]["observed_fvkernel_instances"], 1)
        self.assertEqual(rows["Unused.C"]["observed_fvkernel_instances"], 0)
        self.assertFalse(rows["Unused.C"]["deletion_approved"])
        self.assertFalse(result["safe_to_delete"])
        self.assertFalse(result["global_consumer_closed"])
        self.assertFalse(result["protected_data_exported"])

    def test_trace_integrity_and_truncation_fail(self):
        with self.assertRaisesRegex(ValueError, "SHA_MISMATCH"):
            self.check(RAW + b" ", digest=hashlib.sha256(RAW).hexdigest())
        with self.assertRaisesRegex(ValueError, "COUNT_OR_OBSERVER"):
            self.check(count=5)
        with self.assertRaisesRegex(ValueError, "COUNT_OR_OBSERVER"):
            self.check(RAW.replace(b"P5X_PRELOAD_READY\n", b""))
        with self.assertRaisesRegex(ValueError, "INVALID_REGISTRATION_EVENT"):
            self.check(RAW.replace(b"\tFVKernel\t", b"\tUNKNOWN\t", 1))

    def test_factory_source_alias_collision_rejected(self):
        (self.folder / "Duplicate.C").write_text(
            'registerMooseObject("PhysicsApp", NeutralKernel);\n'
        )
        with self.assertRaisesRegex(ValueError, "DUPLICATE_FACTORY_OWNER"):
            self.check()

    def test_real_newonly_branch_factory_inventory_includes_thermal(self):
        rows = source_owners(ROOT / "physics_app/src/fvkernels")
        self.assertEqual(len(rows), 13)
        self.assertEqual(sum(len(x["registered_factory_types"]) for x in rows), 18)
        by_file = {r["source_file"].split("/")[-1]: r for r in rows}
        self.assertEqual(by_file["PhysicsFVThermalDiffusion.C"]["registered_factory_types"],
                         ["PhysicsFVThermalDiffusion"])
        self.assertEqual(len(by_file["PhysicsFVLogMolarElectronTransport.C"]["registered_factory_types"]), 4)
        self.assertEqual(len(by_file["FVLogMolarTransport.C"]["registered_factory_types"]), 3)


if __name__ == "__main__":
    unittest.main()
