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
    decide_native_P2_status,
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

    def test_W1_expected_is_exact_existing_D10_binary_not_new_build(self):
        self.assertEqual(W1_RUN, "45199787795")
        self.assertEqual(W1_SOURCE_HEAD, "05a3cf85bc5ed7d9c258b1377bd66d68d70f4e3e")
        self.assertEqual(len(W1_ELF_SHA), 64)


if __name__ == "__main__":
    unittest.main()
