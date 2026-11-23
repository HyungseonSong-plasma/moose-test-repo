"""#774 D12 Native P2 fail-closed public factory/secret provenance controls."""
from __future__ import annotations
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ci/guards"))
from issue774_d12_public_d_native_p2 import (  # noqa: E402
    W1_ELF_SHA, W1_RUN, W1_SOURCE_HEAD, classify_native, stage_W1,
    decide_native_P2_status, classify_four_way, check_complete_public_tree,
)


class D12NativeP2Controls(unittest.TestCase):
    def test_only_real_rc_zero_and_moose_syntax_ok_accept(self):
        self.assertTrue(classify_native(0, "Syntax OK")["syntax_ok"])
        self.assertFalse(classify_native(1, "Syntax OK")["syntax_ok"])
        self.assertFalse(classify_native(0, "MPI init finished")["syntax_ok"])

    def test_missing_factory_never_passes_as_intended_rejection(self):
        outcome = classify_native(
            1, "*** ERROR *** A 'PhysicsFVThermalDiffusion' is not a registered object.")
        self.assertFalse(outcome["syntax_ok"])
        self.assertTrue(outcome["safe_error_categories"]["unregistered_factory"])
        self.assertTrue(outcome["safe_error_categories"]["native_error"])

    def test_other_failures_classified_not_reported_as_factory_compat(self):
        outcome = classify_native(42, "No such file or directory")
        self.assertFalse(outcome["syntax_ok"])
        self.assertTrue(outcome["safe_error_categories"]["missing_file"])
        self.assertFalse(outcome["safe_error_categories"]["syntax_ok"])

    def test_protected_log_not_included_in_receipt(self):
        log = "secret-token-NOT-FOR-ARTIFACT Syntax OK"
        outcome = classify_native(0, log)
        self.assertNotIn("secret-token-NOT-FOR-ARTIFACT", json.dumps(outcome))
        self.assertEqual(len(outcome["log_sha256"]), 64)

    def test_safe_fixed_native_error_diagnostics_are_not_full_logs(self):
        log = "*** ERROR ***\nChemistry material transport unknown parameter in /private/token/456\n"
        outcome = classify_native(1, log)
        self.assertFalse(outcome["syntax_ok"])
        self.assertTrue(outcome["safe_error_categories"]["chemistry_contract"])
        self.assertTrue(outcome["safe_error_categories"]["transport_lookup"])
        self.assertIn("Chemistry", outcome["public_error_vocab_hits"])
        self.assertNotIn("/private/token/456", json.dumps(outcome))

    def test_wrong_W1_identity_refused_before_unpacking(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "identity.json").write_text(
                json.dumps({"source_head": "f"*40, "run_id": W1_RUN}))
            with self.assertRaisesRegex(ValueError, "W1_SOURCE_AND_BUILD_PROVENANCE"):
                stage_W1(root, root / "bin")
            self.assertFalse((root / "bin").exists())

    def test_public_d_cannot_pass_without_both_reference_42row_controls(self):
        ref = {"417": {"syntax_ok": True}, "941": {"syntax_ok": True}}
        public = {"417": {"syntax_ok": True}, "941": {"syntax_ok": True}}
        self.assertEqual(decide_native_P2_status(public, ref), "PASS_BOTH_PUBLIC_D_INPUTS")
        self.assertEqual(decide_native_P2_status(public, {"417": ref["417"]}),
                         "HOLD_NATIVE_42ROW_BASELINE_SETUP")
        self.assertEqual(decide_native_P2_status(public,
                         {"417": {"syntax_ok": False}, "941": ref["941"]}),
                         "HOLD_NATIVE_42ROW_BASELINE_SETUP")
        self.assertEqual(decide_native_P2_status(
            {"417": {"syntax_ok": False}, "941": public["941"]}, ref),
            "HOLD_PUBLIC_D_100ROW_CONSTRUCTION")

    def test_causal_matrix_distinguishes_table_binding_interaction(self):
        mk = lambda b, t, j, f: {
            "baseline_42row": {"syntax_ok": b},
            "table_only_100row": {"syntax_ok": t},
            "json_binding_only_42row": {"syntax_ok": j},
            "full_public_d_100row": {"syntax_ok": f},
        }
        signatures = {
            (True, False, True, False): "100ROW_ELECTRON_TABLE_EFFECT",
            (True, True, False, False): "PUBLIC_D_JSON_BINDING_EFFECT",
            (True, False, False, False): "BOTH_INDEPENDENT_CHANGES_FAIL",
            (True, True, True, False): "TABLE_AND_JSON_INTERACTION",
            (True, True, True, True): "FULL_PUBLIC_D_NATIVE_PASS",
            (False, True, True, False): "UNRELIABLE_42ROW_BASELINE",
        }
        for outcomes, expected in signatures.items():
            both = {"417": mk(*outcomes), "941": mk(*outcomes)}
            self.assertEqual(classify_four_way(both),
                             {"417": expected, "941": expected})

    def test_missing_diagonal_case_never_claims_causal_completion(self):
        fragment = {"417": {"baseline_42row": {"syntax_ok": True}}}
        labels = classify_four_way(fragment)
        self.assertEqual(labels["417"], "INCOMPLETE_DIAGNOSTIC_MATRIX")
        self.assertEqual(labels["941"], "INCOMPLETE_DIAGNOSTIC_MATRIX")

    def test_complete_stage_preserves_every_support_file(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder) / "baseline"
            out = Path(folder) / "composed"
            base.mkdir()
            out.mkdir()
            for name, data in (("overlaid.i", b"old"),
                               ("table.txt", b"42rows"),
                               ("more/auxiliary.dat", b"public support")):
                (base / name).parent.mkdir(parents=True, exist_ok=True)
                (out / name).parent.mkdir(parents=True, exist_ok=True)
                (base / name).write_bytes(data)
                (out / name).write_bytes(data)
            (out / "overlaid.i").write_bytes(b"new")
            (out / "table.txt").write_bytes(b"100rows")
            (out / "new.json").write_bytes(b"{}")
            accepted = check_complete_public_tree(
                base, out,
                modified={"overlaid.i", "table.txt"},
                added={"new.json"},
            )
            self.assertTrue(accepted["all_unchanged_public_support_sha_preserved"])
            self.assertEqual(accepted["staged_baseline_public_file_count"], 3)
            (out / "more/auxiliary.dat").unlink()
            with self.assertRaisesRegex(ValueError, "INCOMPLETE_PUBLIC_STAGING_FILE_SET"):
                check_complete_public_tree(
                    base, out,
                    modified={"overlaid.i", "table.txt"},
                    added={"new.json"},
                )

    def test_W1_expected_is_exact_existing_D10_binary_not_new_build(self):
        self.assertEqual(W1_RUN, "45199787795")
        self.assertEqual(W1_SOURCE_HEAD, "05a3cf85bc5ed7d9c258b1377bd66d68d70f4e3e")
        self.assertEqual(len(W1_ELF_SHA), 64)


if __name__ == "__main__":
    unittest.main()
