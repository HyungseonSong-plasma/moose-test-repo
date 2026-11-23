"""Code3 #817 EI18/EI19 no-electron-source semantic mutation gates."""
import unittest
from physics_app.ci.check_issue817_electron_source_absence import (
    assert_no_electron_particle_source,
)

BASE="""[Variables]
  [n_e]
    type = MooseVariableFVReal
  []
  [mean_en]
    type = MooseVariableFVReal
  []
[]
[FVKernels]
  [electron_time]
    type = FVTimeKernel
    variable = n_e
  []
  [energy_loss]
    type = FVCoupledForce
    variable = mean_en
    v = R_excitation_O_1p968
    coef = -1
  []
[]
"""

class NoElectronParticleSource(unittest.TestCase):
    def test_energy_only_fv_force_is_permitted(self):
        for name in ("EI18","EI19"):
            r=assert_no_electron_particle_source(BASE,channel=name)
            self.assertTrue(r["electron_particle_source_absent"])
            self.assertEqual(r["checked_fvkernels"],2)

    def test_new_standard_force_on_electron_variable_fails(self):
        bad=BASE.replace("  [energy_loss]", """  [n_e_source]
    type = FVCoupledForce
    variable = n_e
    v = R_excitation_O_1p968
    coef = 1
  []
  [energy_loss]""")
        for name in ("EI18","EI19"):
            with self.assertRaisesRegex(AssertionError,"must not create an electron-particle source"):
                assert_no_electron_particle_source(bad,channel=name)

    def test_old_source_type_cannot_reappear(self):
        bad=BASE.replace("  [energy_loss]", """  [particle_source]
    type = PhysicsFVElectronReactionSource
    variable = n_e
    number_source = R_excitation_O_1p968
  []
  [energy_loss]""")
        with self.assertRaises(AssertionError):
            assert_no_electron_particle_source(bad,channel="EI18")

    def test_source_named_kernel_is_forbidden_even_if_type_renamed(self):
        bad=BASE.replace("  [energy_loss]", """  [fake_electron_source]
    type = FVMysteryProjector
    variable = n_e
  []
  [energy_loss]""")
        with self.assertRaises(AssertionError):
            assert_no_electron_particle_source(bad,channel="EI19")

if __name__=="__main__":
    unittest.main()
