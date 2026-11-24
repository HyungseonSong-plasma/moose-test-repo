"""Issue774 New-only source/CI closure, fail-closed negative controls."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ci/guards"))
import issue774_newonly_fvkernel_retirement as d9  # noqa: E402
from fvkernel_native_usage_census import source_owners  # noqa: E402


class NewOnlyRetirementCIContract(unittest.TestCase):
    def test_actual_newonly_uses_old_support_waiver_not_factory_compat(self):
        head = subprocess.check_output(
            ("git", "rev-parse", "HEAD"), cwd=ROOT, text=True).strip()
        receipt = d9.audit(ROOT, expected_head=head)
        self.assertEqual(receipt["schema"], d9.SCHEMA)
        self.assertFalse(receipt["legacy_inputs_supported"])
        self.assertEqual(receipt["retired_factories"], [d9.RETIRED, d9.HEAVY, d9.JOULE, d9.CODE1, d9.CODE3])
        self.assertEqual(receipt["current_newonly_factory"]["source_files"], 8)
        self.assertEqual(receipt["current_newonly_factory"]["registered_factory_types"], 13)
        self.assertTrue(receipt["newonly_ci"]["workflow_template_bytes_equal"])
        self.assertFalse(receipt["newonly_ci"]["historical_fdeg_ci_imported"])
        self.assertEqual(receipt["reference_audit"]["active_retired_type_references"], [])
        self.assertFalse(receipt["safe_to_delete"])
        self.assertFalse(receipt["merge_to_main"])
        self.assertEqual(receipt["global_dynamic_and_external_consumers"],
                         "NOT_INDEPENDENTLY_ATTESTED")

    def test_input_dynamic_generator_cpp_and_workflow_regressions_are_blocked(self):
        cases = [
            "experiments/Issue402_plasma_dsl_g1/legacy.i",
            "physics_app/ci/new_generator.py",
            "experiments/Issue402_plasma_dsl_g1/rates.json",
            "physics_app/src/fvkernels/NewKernel.C",
            "physics_app/include/fvkernels/NewKernel.h",
            ".github/workflows/native.yml",
            "ci/workflow_templates/general-ci.yml",
        ]
        for path in cases:
            self.assertIsNotNone(d9.active_surface(path), path)
            with self.assertRaisesRegex(ValueError, "ACTIVE_RETIRED_FACTORY_REINTRODUCED"):
                d9.check_route_rows([{
                    "path": path, "source_blob_sha": "a"*40,
                    "active_surface": d9.active_surface(path),
                    "line_numbers": [5],
                }])

    def test_negative_fdeg_docs_and_old_census_are_not_live_consumers(self):
        paths = [
            "docs/development/old_source.md",
            "reports/issue774/newonly_d5_ab_verified.md",
            "tests/test_fvkernel_native_usage_census.py",
            "ci/guards/fvkernel_native_usage_census.py",
        ]
        rows = [{"path": path, "active_surface": d9.active_surface(path)}
                for path in paths]
        self.assertEqual(d9.check_route_rows(rows)["active_retired_type_references"], [])
        self.assertTrue(all(x["active_surface"] is None for x in rows))
        self.assertIsNone(d9.active_surface("experiments/QPX/history.md"))
        for historical in d9.HISTORICAL_ALLOWED:
            self.assertIsNone(d9.active_surface(historical))
        self.assertIsNotNone(d9.active_surface(
            "experiments/newonly/reattached_heavy_mass.py"))
        with self.assertRaisesRegex(ValueError, "ACTIVE_RETIRED_FACTORY_REINTRODUCED"):
            d9.check_route_rows([{"path": "experiments/newonly/reattached_heavy_mass.py",
                                  "active_surface": "GENERATOR_OR_RUNTIME_JSON"}])

    def test_mixed_historical_and_live_reintroduction_fails_closed(self):
        rows = [
            {"path": "docs/development/old.md", "active_surface": None},
            {"path": "experiments/newonly/new_joule.py",
             "active_surface": "GENERATOR_OR_RUNTIME_JSON"},
        ]
        with self.assertRaisesRegex(ValueError, "ACTIVE_RETIRED_FACTORY_REINTRODUCED"):
            d9.check_route_rows(rows)
        good = d9.check_route_rows([rows[0]])
        self.assertEqual(good["reference_classes"], {"NON_ACTIVE_REFERENCE": 1})

    def test_reintroduced_cpp_source_or_wrong_blob_fails(self):
        rows = source_owners(ROOT / "physics_app/src/fvkernels")
        tracked = {r["source_file"]: {"sha": r["source_blob_sha"]} for r in rows}
        source = d9.SOURCE
        changed = dict(tracked, **{source: {"sha": "0"*40}})
        with self.assertRaisesRegex(ValueError, "RETIRED_SOURCE_OR_HEADER_REINTRODUCED"):
            d9.check_factory_inventory(ROOT, changed)
        for retired_path in d9.RETIRED_PATHS:
            with self.assertRaisesRegex(ValueError, "RETIRED_SOURCE_OR_HEADER_REINTRODUCED"):
                d9.check_factory_inventory(ROOT, dict(tracked, **{retired_path: {"sha": "0"*40}}))
        bad_sha = dict(tracked)
        bad_sha[rows[0]["source_file"]] = {"sha": "0"*40}
        with self.assertRaisesRegex(ValueError, "EXACT_TREE_SOURCE_BLOB_MISMATCH"):
            d9.check_factory_inventory(ROOT, bad_sha)
        correct = d9.check_factory_inventory(ROOT, tracked)
        self.assertEqual(correct["registered_factory_types"], 13)

    def test_historical_research_identity_is_immutable(self):
        good = {path: {"sha": sha} for path, sha in d9.HISTORICAL_ALLOWED.items()}
        self.assertEqual(d9.check_historical_sources(good), d9.HISTORICAL_ALLOWED)
        for path in good:
            bad = {name: dict(meta) for name, meta in good.items()}
            bad[path]["sha"] = "0" * 40
            with self.assertRaisesRegex(ValueError, "HISTORICAL_SOURCE_PIN_DRIFT"):
                d9.check_historical_sources(bad)

    def test_code2_original_joule_smoke_is_byte_pinned_and_not_active(self):
        import hashlib
        raw = (ROOT / d9.JOULE_ARCHIVE).read_bytes()
        actual = hashlib.sha1(
            b"blob " + str(len(raw)).encode() + b"\0" + raw
        ).hexdigest()
        self.assertEqual(actual, d9.JOULE_SMOKE_BLOB)
        self.assertFalse((ROOT / d9.JOULE_SMOKE).exists())

    def test_code2_historical_runtime_generators_only_by_pinned_blob(self):
        for path in (
            "experiments/fem_fvm_plasma_discriminator/prepare_cases.py",
            "experiments/Issue351_frozen_heavy_driver_parity/control.py",
        ):
            self.assertIn(path, d9.HISTORICAL_ALLOWED)
            self.assertIsNone(d9.active_surface(path))
        self.assertEqual(len(d9.RETIRED_FACTORIES), 5)

    def test_missing_workflow_owner_and_forbidden_historical_fdeg_import(self):
        paths = [d9.NEWONLY_CI, d9.TEMPLATE, d9.SAFETY, d9.EXISTING_TEST,
                 d9.NEW_TEST, d9.SELF]
        fake = {path: {"sha": "0"*40} for path in paths}
        fake[d9.JOULE_ARCHIVE] = {"sha": d9.JOULE_SMOKE_BLOB}
        fake[d9.OLD_HISTORICAL_CI[0]] = {"sha": "0"*40}
        with self.assertRaisesRegex(ValueError, "HISTORICAL_FDEG_CI_IMPORTED"):
            d9.check_ci_tree(ROOT, fake)
        fake.pop(d9.OLD_HISTORICAL_CI[0])
        fake.pop(d9.NEW_TEST)
        with self.assertRaisesRegex(ValueError, "CI_OWNER_MISSING"):
            d9.check_ci_tree(ROOT, fake)

    def test_pinned_code1_history_rejects_archive_and_generator_drift(self):
        tracked = {
            d9.CODE1_ARCHIVE: {"sha": d9.CODE1_ARCHIVE_BLOB},
            d9.CODE1_HISTORIC_GENERATOR: {"sha": d9.CODE1_HISTORIC_SHA},
        }
        report = d9.check_code1_archive(ROOT, tracked)
        self.assertFalse(report["current_binary_legacy_replay_proven"])
        for path in (d9.CODE1_ARCHIVE, d9.CODE1_HISTORIC_GENERATOR):
            modified = dict(tracked, **{path: {"sha": "0"*40}})
            expected = ("CODE1_ARCHIVE_BLOB_DRIFT" if path == d9.CODE1_ARCHIVE
                        else "CODE1_HISTORICAL_GENERATOR_CHANGED")
            with self.assertRaisesRegex(ValueError, expected):
                d9.check_code1_archive(ROOT, modified)

    def test_s5r_pins_and_code3_reference_scope(self):
        tracked = {d9.S5R_ARCHIVE: {"sha": d9.S5R_ORIGINAL_BLOB},
                   d9.S5R: {"sha": d9.S5R_MIGRATED_BLOB}}
        self.assertEqual(d9.check_s5r_lineage(tracked)["original"], d9.S5R_ORIGINAL_BLOB)
        for path in tracked:
            bad = dict(tracked, **{path: {"sha": "0"*40}})
            with self.assertRaisesRegex(ValueError, "S5R_.*_DRIFT"):
                d9.check_s5r_lineage(bad)
        self.assertIsNone(d9.reference_surface(d9.S5R, d9.HEAVY))
        self.assertIsNotNone(d9.reference_surface(d9.S5R, d9.CODE3))
        for path, assertion in d9.CODE3_ASSERTIONS.items():
            self.assertIsNone(d9.reference_surface(path, assertion))
            self.assertIsNotNone(d9.reference_surface(path, "type = " + d9.CODE3))

    def test_bad_source_sha_rejected_even_when_active_type_absent(self):
        with self.assertRaisesRegex(ValueError, "EXACT_HEAD_MISMATCH"):
            d9.audit(ROOT, expected_head="f"*40)
        with self.assertRaisesRegex(ValueError, "BAD_EXACT_SOURCE_HEAD"):
            d9.audit(ROOT, expected_head="main")


if __name__ == "__main__":
    unittest.main()
