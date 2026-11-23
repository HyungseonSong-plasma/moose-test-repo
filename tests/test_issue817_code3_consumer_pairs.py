"""P0 actual H05/R2 one-block and bad-consumer mutation controls."""
import unittest
from experiments.Code3_electron_source_retirement import consumer_pairs as cp
from experiments.Code3_electron_source_retirement import run as code3
from physics_app.ci import check_r2_o2_ionization_implementation as r2
from physics_app.ci import check_stage5_h05_runtime as h05

class ActiveConsumerPairTests(unittest.TestCase):
    def test_h05(self):
        old,new,meta=cp.h05_pair()
        self.assertNotEqual(old,new)
        self.assertEqual(code3._outside_target(old,cp.H05_TARGET),
                         code3._outside_target(new,cp.H05_TARGET))
        self.assertEqual((meta["source_functor"],meta["mode"],meta["coefficient"]),
                         ("S_e_h05","physical",1.0))
        self.assertIn("state_form = log_molar_eV",old)

    def test_r2(self):
        old,new,meta=cp.r2_pair()
        self.assertNotEqual(old,new)
        self.assertEqual(code3._outside_target(old,cp.R2_TARGET),
                         code3._outside_target(new,cp.R2_TARGET))
        self.assertEqual((meta["source_functor"],meta["mode"],meta["coefficient"]),
                         ("electron_ionization_number_source","physical",1.0))
        self.assertIn("state_form = log_molar_eV",old)

    def test_wrong_energy_bridge_fail_closed(self):
        source=r2.RUNTIME_INPUT
        bad=(source.replace("physical_eV","bad_mode"),
             source.replace("mean_energy_bridge","lost_bridge"),
             source.replace("physical_eV","physical_eV\n    state_form = physical_eV"))
        for mutant in bad:
            with self.subTest(mutant=mutant[:40]):
                with self.assertRaises(code3.Code3ParityError):
                    cp.r2_energy_bridge(mutant)

    def test_other_region_mutation_caught(self):
        for fn,path in ((cp.h05_pair,cp.H05_TARGET),(cp.r2_pair,cp.R2_TARGET)):
            old,new,_=fn()
            self.assertNotEqual(code3._outside_target(old,path),
                                code3._outside_target(
                                    new.replace("csv = true","csv = false"),path))

    def test_production_generators_have_standard_electron_source(self):
        self.assertIn("type = FVCoupledForce",h05.runtime_input())
        self.assertIn("v = S_e_h05",h05.runtime_input())
        self.assertIn("v = electron_ionization_number_source",r2.RUNTIME_INPUT)
        self.assertNotIn("type = PhysicsFVElectronReactionSource",h05.runtime_input())
        self.assertNotIn("type = PhysicsFVElectronReactionSource",r2.RUNTIME_INPUT)

if __name__ == "__main__":
    unittest.main()
