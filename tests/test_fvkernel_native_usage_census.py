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
            self.check(RAW.replace(b"NeutralKernel", b"AlienKernel"), digest=hashlib.sha256(RAW).hexdigest())
        with self.assertRaisesRegex(ValueError, "COUNT_OR_OBSERVER"):
            self.check(count=5)
        with self.assertRaisesRegex(ValueError, "COUNT_OR_OBSERVER"):
            self.check(RAW.replace(b"P5X_PRELOAD_READY\n", b""))
        with self.assertRaisesRegex(ValueError, "INVALID_REGISTRATION_EVENT"):
            self.check(RAW.replace(b"\tFVKernel\t", b"\tUNKNOWN\t", 1))

    def test_repeated_preload_markers_preserve_registration_integrity(self):
        # Multiple loader processes may initialize the same observer.
        repeated = RAW.replace(
            b"P5X_PRELOAD_READY\n",
            b"P5X_PRELOAD_READY\nP5X_PRELOAD_READY\n",
        )
        result = self.check(repeated)
        self.assertEqual(result["observer_marker_count"], 2)
        self.assertEqual(result["observed_all_events"], 4)
        self.assertEqual(result["fvkernel_type_counts"],
                         {"NeutralKernel": 1, "FrameworkKernel": 1})
        self.assertFalse(result["safe_to_delete"])
        # Multiprocess markers cannot bypass unique-event and presence gates.
        with self.assertRaisesRegex(ValueError, "COUNT_OR_OBSERVER"):
            self.check(repeated, count=5)
        with self.assertRaisesRegex(ValueError, "COUNT_OR_OBSERVER"):
            self.check(repeated.replace(b"P5X_PRELOAD_READY\n", b""))

    def test_factory_source_alias_collision_rejected(self):
        (self.folder / "Duplicate.C").write_text(
            'registerMooseObject("PhysicsApp", NeutralKernel);\n'
        )
        with self.assertRaisesRegex(ValueError, "DUPLICATE_FACTORY_OWNER"):
            self.check()

    def test_real_newonly_branch_factory_inventory_includes_thermal(self):
        rows = source_owners(ROOT / "physics_app/src/fvkernels")
        self.assertEqual(len(rows), 11)
        self.assertEqual(sum(len(x["registered_factory_types"]) for x in rows), 16)
        by_file = {r["source_file"].split("/")[-1]: r for r in rows}
        self.assertNotIn("PhysicsFVThermalDiffusion.C", by_file)
        self.assertFalse((ROOT / "physics_app/include/fvkernels/PhysicsFVThermalDiffusion.h").exists())
        self.assertEqual(len(by_file["PhysicsFVLogMolarElectronTransport.C"]["registered_factory_types"]), 4)
        self.assertEqual(len(by_file["FVLogMolarTransport.C"]["registered_factory_types"]), 3)


class NativeABComparisonTest(unittest.TestCase):
    """Synthetic A/B receipts test failure behavior without actual P3 execution."""

    def fixture(self):
        from fvkernel_native_usage_census import THERMAL_SOURCE, THERMAL_BLOB
        row = dict(source_file="physics_app/src/fvkernels/Other.C",
                   source_blob_sha="c"*40, registered_factory_types=["Other"],
                   observed_factory_counts={"Other": 1},
                   observed_fvkernel_instances=1,
                   run_usage="OBSERVED_VIA_FEProblemBase_addFVKernel",
                   deletion_approved=False)
        t = dict(source_file=THERMAL_SOURCE, source_blob_sha=THERMAL_BLOB,
                 registered_factory_types=["PhysicsFVThermalDiffusion"],
                 observed_factory_counts={}, observed_fvkernel_instances=0,
                 run_usage="NOT_OBSERVED_IN_INSTRUMENTED_API",
                 deletion_approved=False)
        def make(head, rows, nfactories):
            owner = dict(
                schema="fvkernel.native_source_usage.v0.1",
                source_head=head, binary_sha256=("1" if head[0]=="a" else "2")*64,
                trace_scope="POST_ORIGINAL_CALLS_NOT_WHOLE_WAREHOUSE",
                safe_to_delete=False, global_consumer_closed=False,
                protected_data_exported=False, observer_marker_count=1,
                observed_all_events=77,
                event_family_counts={"FVKernel": 35, "FVBC": 24, "FEBoundaryCondition": 18},
                fvkernel_type_counts={"Other": 1}, other_source_or_framework_type_counts={},
                source_files=rows, local_registered_factory_types=nfactories,
            )
            filtered=dict(recorded_all_events=77, observed_FVKernel=[["FVKernel","O2p_time","X"]],
                          observed_FVBC=[], observed_electron_FE_BC=[],
                          actual_registered_count={"FVKernel":12,"FVBC":12,"electron_FE_BC":8})
            return dict(source_head=head, binary_sha256=owner["binary_sha256"],
                        status="PASS_16_INTENDED_NATIVE_REJECTIONS",
                        native_tests_completed=16,native_expected_rejections=16,
                        science="SCIENCE_HOLD",private_data_in_artifacts=False,
                        tmpfs_cleanup_verified=True, OCI="same-oci",
                        one_build_bundle={"source_head":head, "W1_elf_sha256":owner["binary_sha256"],"build_count":1},
                        cases={c:dict(source_layer_sha256={str(i):"x" for i in range(11)},
                                      JSON_sha256="j",parent_mesh_sha256="m",
                                      clean_syntax_ok=True,clean_exit=0,
                                      source_restoration="SHA_ALL_PUBLIC_FILES_UNCHANGED")
                               for c in ["417","941"]},
                        full_fvkernel_source_usage={c:dict(owner) for c in ["417","941"]},
                        owner_registration={c:dict(filtered) for c in ["417","941"]})
        extras = [
            dict(row, source_file=f"physics_app/src/fvkernels/Extra{i}.C",
                 source_blob_sha=f"{i:040x}",
                 registered_factory_types=[f"Extra{i}"],
                 observed_factory_counts={},
                 observed_fvkernel_instances=0,
                 run_usage="NOT_OBSERVED_IN_INSTRUMENTED_API")
            for i in range(11)
        ]
        return make("a"*40,[t,row,*extras],18), make("b"*40,[row,*extras],17)

    def test_positive_proves_observed_scope_only(self):
        from fvkernel_native_usage_census import compare_p05_source_usage
        a,b=self.fixture()
        result=compare_p05_source_usage(a,b)
        self.assertEqual(result["status"],"PASS_SCOPE_ONLY_NOT_DELETION_APPROVAL")
        self.assertEqual(set(result["cases"]),{"417","941"})
        self.assertFalse(result["safe_to_delete"])
        self.assertEqual(result["actual_P3_parity"],"NOT_TESTED")

    def test_multiple_preload_markers_are_audited_not_ignored(self):
        from fvkernel_native_usage_census import compare_p05_source_usage
        a,b=self.fixture()
        for case in ("417","941"):
            a["full_fvkernel_source_usage"][case]["observer_marker_count"]=2
            b["full_fvkernel_source_usage"][case]["observer_marker_count"]=3
        result=compare_p05_source_usage(a,b)
        self.assertEqual(result["status"],"PASS_SCOPE_ONLY_NOT_DELETION_APPROVAL")
        self.assertFalse(result["safe_to_delete"])
        for case in ("417","941"):
            a["full_fvkernel_source_usage"][case]["observer_marker_count"]=0
        with self.assertRaisesRegex(ValueError,"A_CENSUS_INVALID"):
            compare_p05_source_usage(a,b)

    def test_thermal_was_active_rejected(self):
        from fvkernel_native_usage_census import compare_p05_source_usage, THERMAL_SOURCE
        a,b=self.fixture()
        for c in ("417","941"):
            t=next(x for x in a["full_fvkernel_source_usage"][c]["source_files"]
                   if x["source_file"]==THERMAL_SOURCE)
            t["observed_fvkernel_instances"]=1
        with self.assertRaisesRegex(ValueError,"THERMAL_RUNTIME_OBSERVED"):
            compare_p05_source_usage(a,b)

    def test_inconsistent_input_and_oci_hold(self):
        from fvkernel_native_usage_census import compare_p05_source_usage
        a,b=self.fixture()
        b["cases"]["941"]["JSON_sha256"]="tampered"
        with self.assertRaisesRegex(ValueError,"INPUT_SHA_MISMATCH"):
            compare_p05_source_usage(a,b)
        a,b=self.fixture()
        b["OCI"]="unrelated"
        with self.assertRaisesRegex(ValueError,"SOURCE_HEAD_OR_OCI_INVALID"):
            compare_p05_source_usage(a,b)


if __name__ == "__main__":
    unittest.main()
