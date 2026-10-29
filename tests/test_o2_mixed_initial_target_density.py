"""P0: n_O3P(0) = 1e15 m^-3 from the exact EOS, no other species changes."""
import importlib.util
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "experiments/Issue395_powered_chemistry_ladder/set_zero_initial_atomic_o.py"
spec = importlib.util.spec_from_file_location("oxygen_initial", SRC)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def base():
    return """[Variables]
  [w_O]
    initial_condition = 0.10309278350515465
  []
  [w_Os]
    initial_condition = 0.12371134020618557
  []
  [w_O2s]
    initial_condition = 0.051546391752577324
  []
  [log_ne]
  []
  [log_ni]
  []
  [log_energy]
  []
[]
[FunctorMaterials]
  [constants]
    prop_names = 'p_fixed T_g_fixed ion_mobility ion_diffusion'
    prop_values = '1.333223684 300 10 0.2585'
  []
  [neutral_O2_constraint]
    property_name = w_O2_constraint
    functor_names = 'w_O2s w_O w_Os'
    expression = '1.0-s-o-a'
  []
  [mean_mass]
    expression = '1.0/(m0/0.032+m1/0.032+m2/0.016+m3/0.016)'
  []
  [neutral_density]
    functor_names = 'p Mn_neutral T_g_fixed'
    expression = 'prs*mol/(8.31446*tmp)'
  []
[]
"""

def test_eos_target_is_exact():
    initial = base()
    result = module.change_to_target_number_density(initial, 1e15)
    module.verify_target_number_density(result, 1e15)
    p,t,os = module._baseline_number_density_constants(result)
    w = module.target_o_mass_fraction(1e15,p=p,tg=t,os_fraction=os)
    assert math.isclose(w,1.7455280139995249e-6,rel_tol=1e-13)
    assert result == initial.replace("initial_condition = 0.10309278350515465", "initial_condition = "+format(w,'.17g'), 1)
    assert "initial_condition = 0.12371134020618557" in result

def test_target_differs_from_initial_zero_and_is_positive():
    import pytest
    for invalid in (0.0, -1.0, 1e25, math.inf, math.nan):
        with pytest.raises(ValueError):
            module.change_to_target_number_density(base(), invalid)
    with pytest.raises(ValueError):
        module.change_to_target_number_density(base().replace("prs*mol/(8.31446*tmp)","bad"),1e15)
