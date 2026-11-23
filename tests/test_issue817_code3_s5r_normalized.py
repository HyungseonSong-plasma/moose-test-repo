"""Code3 #817: S5-R original normalized electron source + energy-only negatives."""
from __future__ import annotations
import unittest

from experiments.Code3_electron_source_retirement import consumer_pairs as cp
from experiments.Code3_electron_source_retirement import s5r_controls as sc
from physics_harness.adapters.moose import parameters as mp


class S5RNormalizedSourceGate(unittest.TestCase):
    def test_signed_normalized_pair_ledger(self):
        a,b,m=cp.s5r_pair()
        r=sc.assert_s5r_electron_ledger(a,b)
        self.assertTrue(r["coefficient_exact_inverse"])
        self.assertTrue(r["ei18_energy_only"])
        self.assertTrue(r["ei19_energy_only"])
        self.assertFalse(r["source_cut_allowed"])
        self.assertEqual(m["mode"],"normalized")

    def test_ei18_cannot_become_electron_source_functor(self):
        a,b,_=cp.s5r_pair()
        names=mp.unquote(mp.get_parameter(a,sc.MATERIAL,"functor_names"))
        changed="\u0027"+names+" R_excitation_O_1p968"+"\u0027"
        bad=mp.upsert_parameter(a,sc.MATERIAL,"functor_names",changed)
        bad_b=mp.upsert_parameter(b,sc.MATERIAL,"functor_names",changed)
        with self.assertRaisesRegex(ValueError,"ELECTRON_IONIZATION_SOURCE_LEDGER_DRIFT"):
            sc.assert_s5r_electron_ledger(bad,bad_b)

    def test_electron_sign_or_conversion_cannot_change(self):
        a,b,_=cp.s5r_pair()
        ex=mp.unquote(mp.get_parameter(a,sc.MATERIAL,"expression"))
        changed="\u0027"+ex.replace("-rattach","+rattach")+"\u0027"
        bad=mp.upsert_parameter(a,sc.MATERIAL,"expression",changed)
        bad_b=mp.upsert_parameter(b,sc.MATERIAL,"expression",changed)
        with self.assertRaisesRegex(ValueError,"ELECTRON_SOURCE_SIGN_OR_AVOGADRO_DRIFT"):
            sc.assert_s5r_electron_ledger(bad,bad_b)

    def test_inverse_density_coefficient_cannot_drift(self):
        a,b,_=cp.s5r_pair()
        drift=mp.upsert_parameter(b,sc.KERNEL,"coef","1")
        with self.assertRaisesRegex(ValueError,"NORMALIZED_REFERENCE_COEF_DRIFT"):
            sc.assert_s5r_electron_ledger(a,drift)

    def test_energy_only_projection_owner_cannot_drift(self):
        a,b,_=cp.s5r_pair()
        path="FVKernels/s5r_energy_ei18_o_to_os"
        bad=mp.upsert_parameter(a,path,"v","R_ion_O")
        bad_b=mp.upsert_parameter(b,path,"v","R_ion_O")
        with self.assertRaisesRegex(ValueError,"ENERGY_ONLY_CHEMISTRY_OWNER_DRIFT"):
            sc.assert_s5r_electron_ledger(bad,bad_b)


if __name__=="__main__":
    unittest.main()
