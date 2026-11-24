"""Code3 #817 active signed source ownership/normalization negative controls."""
from __future__ import annotations
import unittest
from ci.guards import issue817_code3_production_migration as gate
from physics_harness.adapters.moose import parameters as mp

TARGET = "FVKernels/n_e_source"
FIXTURE = '''[FVKernels]
  [n_e_source]
    type = FVCoupledForce
    variable = n_e
    v = signed_electron_source
    coef = 1
  []
[]'''


class ActiveCode3MigrationTest(unittest.TestCase):
    def test_explicit_signed_functor_and_coef(self):
        r = gate.check_owner(FIXTURE, TARGET, "signed_electron_source", 1)
        self.assertEqual(r["type"], "FVCoupledForce")
        self.assertEqual(r["coefficient"], 1)

    def test_wrong_sign_or_wrong_functor_rejected(self):
        for value in ("-1", "0", "nan", "inf", "0.5", "2"):
            with self.subTest(coef=value):
                bad = mp.upsert_parameter(FIXTURE, TARGET, "coef", value)
                with self.assertRaisesRegex(ValueError, "COEFFICIENT_DRIFT"):
                    gate.check_owner(bad, TARGET, "signed_electron_source", 1)
        bad = mp.upsert_parameter(FIXTURE, TARGET, "v", "wrong_source")
        with self.assertRaisesRegex(ValueError, "WRONG_SIGNED_FUNCTOR"):
            gate.check_owner(bad, TARGET, "signed_electron_source", 1)

    def test_unregistered_custom_type_and_deprecated_args_rejected(self):
        broken = mp.upsert_parameter(FIXTURE, TARGET, "type", gate.TARGET)
        with self.assertRaisesRegex(ValueError, "WRONG_OWNER"):
            gate.check_owner(broken, TARGET, "signed_electron_source", 1)
        for param, value in (("n_ref", "4"), ("state_form", "physical"),
                             ("number_source", "extra_electron_source")):
            with self.subTest(parameter=param):
                broken = mp.upsert_parameter(FIXTURE, TARGET, param, value)
                with self.assertRaisesRegex(ValueError, "DEPRECATED_PARAMETER"):
                    gate.check_owner(broken, TARGET, "signed_electron_source", 1)

    def test_normalized_inverse_reference_precision(self):
        ref = 1.298e18
        normalized = mp.upsert_parameter(FIXTURE, TARGET, "coef", f"{1/ref:.17g}")
        accepted = gate.check_owner(normalized, TARGET, "signed_electron_source", 1/ref)
        self.assertGreater(accepted["coefficient"], 0)
        with self.assertRaisesRegex(ValueError, "COEFFICIENT_DRIFT"):
            gate.check_owner(normalized, TARGET, "signed_electron_source", 1/ref*1.01)

    def test_live_generators_reject_old_factory_and_preserve_electron_ledger(self):
        result = gate.active_inputs()
        self.assertEqual({x["case"] for x in result},
                         {"EI01", "H05", "R2", "EI16", "EI16_STANDARD",
                          "EI20", "EDETACH", "S5R"})
        self.assertTrue(all(x["coefficient"] > 0 for x in result))
        self.assertEqual(gate.check_static_current_source_references()["active_cpp_source_reads"], 0)


if __name__ == "__main__":
    unittest.main()
