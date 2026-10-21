"""Issue #395 EI17 O-elastic-only chemistry regression and mutation gates."""
from __future__ import annotations

import importlib.util
import math
from pathlib import Path
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "experiments/Issue395_powered_chemistry_ladder/build_o_elastic_overlay.py"
TABLE = REPO / "physics_app/data/electron_impact/o_elastic.txt"
BASE = """[Variables]
  [log_ne]
  []
  [log_energy]
  []
[]
[FVVariables]
  [w_O]
  []
[]
[FunctorMaterials]
  [density]
    property_name = rho_neutral
  []
  [ne]
    property_name = n_e_physical
  []
  [Tg]
    property_name = T_g_fixed
  []
  [en]
    type = PhysicsElectronMeanEnergyMaterial
    mean_energy = mean_en_solved
  []
[]
"""

spec = importlib.util.spec_from_file_location("issue395_build_o_elastic", SCRIPT)
assert spec and spec.loader
ei17 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ei17)


class EI17OElasticOverlay(unittest.TestCase):
    def test_production_table_frozen(self):
        ei17.verify_table(TABLE)

    def test_single_progress_energy_only(self):
        out = ei17.build(BASE, "o_elastic.txt")
        self.assertEqual(out.count("reaction_progress = R_elastic_O\n"), 1)
        self.assertIn("type = PhysicsElectronImpactRateMaterial", out)
        self.assertIn("rate_table_file = o_elastic.txt", out)
        self.assertIn("target_molar_concentration = c_O_EI17", out)
        self.assertIn("functor_names = 'rho_neutral w_O'", out)
        self.assertIn("expression = '-de*R'", out)
        self.assertIn("functor = S_electron_energy_EI17", out)
        self.assertIn("variable = log_energy", out)
        self.assertNotIn("variable = log_ne", out)
        self.assertNotIn("[FVKernels]", out)
        self.assertNotIn("variable = w_O", out)
        self.assertNotIn("S_neutral_mass_EI17", out)

    def test_elastic_O_factor_vs_O2(self):
        m_e=ei17.M_E
        N_A=ei17.N_A
        atomic=3*m_e/(ei17.M_O/N_A)
        molecular=3*m_e/(.032/N_A)
        self.assertTrue(math.isclose(ei17.ELASTIC_FACTOR,atomic,rel_tol=1e-14))
        self.assertTrue(math.isclose(atomic/molecular,2.0,rel_tol=1e-14))
        eps=5.73276
        tg=300.0
        dE=atomic*((2/3)*eps-ei17.K_B_OVER_E*tg)
        self.assertGreater(dE,0)  # positive electron energy loss under nominal conditions
        self.assertLess(dE,0.01) # elastic mass-ratio effect is small

    def test_missing_providers_blocked(self):
        with self.assertRaisesRegex(ValueError,"missing required"):
            ei17.build("[log_ne]\n[]\n", "o_elastic.txt")

    def test_duplicate_progress_blocked(self):
        with self.assertRaisesRegex(ValueError,"already present"):
            ei17.build(BASE+"reaction_progress = R_elastic_O\n", "o_elastic.txt")

    def test_table_mutation_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            changed=Path(tmp)/"o_elastic.txt"
            original=TABLE.read_bytes()
            altered=original.replace(b"5.89E+10",b"5.99E+10",1)
            self.assertNotEqual(original,altered)
            changed.write_bytes(altered)
            with self.assertRaisesRegex(ValueError,"Git blob mismatch"):
                ei17.verify_table(changed)


if __name__ == "__main__":
    unittest.main()
