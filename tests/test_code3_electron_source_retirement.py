"""P0 guards for code3 electron-only Custom -> FVCoupledForce preparation.

No Native execution or numerical parity claim.
"""
from __future__ import annotations

import unittest

from experiments.Code3_electron_source_retirement import run as code3
from physics_harness.adapters.moose import parameters as mp


def fixture(*, mode: str | None = "normalized", n_ref: str | None = "4") -> str:
    settings = ("    state_form = " + mode + "\n") if mode is not None else ""
    scaling = ("    n_ref = " + n_ref + "\n") if n_ref is not None else ""
    return (
        "[FVKernels]\n"
        "  [s5r_electron_source]\n"
        "    type = PhysicsFVElectronReactionSource\n"
        "    variable = n_e\n"
        "    number_source = signed_electron_functor\n"
        + settings + scaling +
        "    block = plasma\n"
        "  []\n"
        "  [heavy_source]\n"
        "    type = PhysicsFVSpeciesReactionSource\n"
        "    variable = w_O\n"
        "    source = S_O\n"
        "  []\n"
        "[]\n"
        "[FunctorMaterials]\n"
        "  [signed_electron]\n"
        "    type = ADParsedFunctorMaterial\n"
        "    property_name = signed_electron_functor\n"
        "  []\n"
        "[]\n"
    )


class Code3ElectronOnlyP0Test(unittest.TestCase):
    def test_normalized_replacement_changes_only_target_block(self):
        original = fixture(n_ref="4")
        changed, evidence = code3.replace_electron_only(original)
        self.assertEqual(code3._outside_target(original),
                         code3._outside_target(changed))
        self.assertEqual(evidence["mode"], "normalized")
        self.assertEqual(evidence["coefficient"], 0.25)
        self.assertEqual(mp.get_parameter(changed, code3.TARGET, "v"),
                         "signed_electron_functor")
        self.assertEqual(mp.get_parameter(changed, code3.TARGET, "coef"), "0.25")
        self.assertEqual(mp.get_parameter(changed, code3.TARGET, "variable"), "n_e")
        self.assertEqual(mp.get_parameter(changed, code3.TARGET, "block"), "plasma")
        self.assertNotIn("n_ref =", changed)
        self.assertNotIn("number_source =", changed)
        self.assertIn("type = PhysicsFVSpeciesReactionSource", changed)

    def test_physical_and_default_modes(self):
        changed, evidence = code3.replace_electron_only(fixture(mode="physical", n_ref=None))
        self.assertEqual(evidence["coefficient"], 1.0)
        self.assertEqual(evidence["mode"], "physical")
        self.assertEqual(mp.get_parameter(changed, code3.TARGET, "coef"), "1")
        default, evidence = code3.replace_electron_only(fixture(mode=None, n_ref="4"))
        self.assertEqual(evidence["mode"], "normalized")
        self.assertEqual(mp.get_parameter(default, code3.TARGET, "coef"), "0.25")

    def test_bad_normalized_reference_fails_closed(self):
        for value in (None, "0", "-3", "nan", "inf", "abc", "1e-500"):
            with self.subTest(n_ref=value):
                with self.assertRaises(code3.Code3ParityError):
                    code3.replace_electron_only(fixture(n_ref=value))

    def test_unexpected_type_mode_or_missing_source_fails_closed(self):
        with self.assertRaisesRegex(code3.Code3ParityError, "UNKNOWN_STATE_FORM"):
            code3.replace_electron_only(fixture(mode="log", n_ref="4"))
        with self.assertRaisesRegex(code3.Code3ParityError, "EXPECTED_CUSTOM"):
            code3.replace_electron_only(
                fixture().replace("PhysicsFVElectronReactionSource", "FVCoupledForce"))
        with self.assertRaisesRegex(code3.Code3ParityError, "MISSING_SIGNED"):
            code3.replace_electron_only(
                fixture().replace("number_source = signed_electron_functor\n", ""))

    def test_real_w5_single_object_scope_and_hold(self):
        result = code3.self_test()
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["numeric_equivalence"], "NOT_PROVEN")
        self.assertEqual(result["safe_delete"], "HOLD")
        self.assertTrue(result["checks"]["electron_only"])


if __name__ == "__main__":
    unittest.main()
