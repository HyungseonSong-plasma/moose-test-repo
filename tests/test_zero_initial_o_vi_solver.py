"""P0 mutation controls for zero-O strict-kinetics VI numerical discriminator."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

CHEM = Path(__file__).resolve().parents[1] / "experiments/Issue395_powered_chemistry_ladder"
sys.path.insert(0, str(CHEM))
spec = importlib.util.spec_from_file_location("zero_o_vi", CHEM / "enable_zero_o_vi_solver.py")
assert spec and spec.loader
vi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vi)

EXAMPLE = """[Variables]
  [w_O2s]
    initial_condition = 0.051546391752577324
  []
  [w_O]
    initial_condition = 0.0
  []
  [w_Os]
    initial_condition = 0.12371134020618557
  []
  [log_ne][]
  [log_ni][]
  [log_energy][]
[]
[FunctorMaterials]
  [o2_constraint]
    property_name = w_O2_constraint
    functor_names = 'w_O2s w_O w_Os'
    expression = '1.0-s-o-a'
  []
[]
[AuxVariables]
  [d1_dummy]
    family = MONOMIAL
    order = CONSTANT
    block = wafer_surface
  []
[]
[Executioner]
  type = Transient
  scheme = implicit-euler
  solve_type = NEWTON
  line_search = bt
  petsc_options = '-snes_converged_reason -ksp_converged_reason'
  petsc_options_iname = '-ksp_type -pc_type -pc_factor_shift_type'
  petsc_options_value = 'preonly lu NONZERO'
[]
[Preconditioning]
  [smp]
    type = SMP
    full = true
  []
[]
"""


def test_one_state_only_positivity_and_retained_strict_interpolation() -> None:
    updated = vi.apply(EXAMPLE)
    vi.verify(updated)
    assert updated.count("bound_value = 0.0") == 1
    assert updated.count("bounded_variable = w_O") == 1
    assert updated.count("vinewtonrsls") == 1
    assert updated.splitlines().count("    initial_condition = 0.0") == 1
    assert "  line_search = bt\n" in updated
    assert "  scheme = implicit-euler\n" in updated
    assert "  solve_type = NEWTON\n" in updated
    assert "  petsc_options = '-snes_converged_reason -ksp_converged_reason'\n" in updated
    assert "  petsc_options_value = 'preonly lu NONZERO vinewtonrsls'\n" in updated
    assert "property_name = w_O2_constraint" in updated
    assert "expression = '1.0-s-o-a'" in updated
    assert vi.DUMMY in updated
    assert "max(0" not in updated
    with pytest.raises(ValueError, match="Existing bounds"):
        vi.apply(updated)


@pytest.mark.parametrize("bad", [
    EXAMPLE.replace("initial_condition = 0.0", "initial_condition = 1e-12"),
    EXAMPLE.replace("[AuxVariables]", "[ExtraVariables]"),
    EXAMPLE.replace("petsc_options_value = 'preonly lu NONZERO'", "petsc_options_value = 'preonly gamg NONZERO'"),
    EXAMPLE.replace("  solve_type = NEWTON", "  solve_type = PJFNK"),
    EXAMPLE.replace("property_name = w_O2_constraint", "property_name = invalid"),
    EXAMPLE + "[Bounds]\n[]\n",
])
def test_incompatible_initial_state_or_solver_fails_closed(bad: str) -> None:
    with pytest.raises(ValueError):
        vi.apply(bad)


def test_exact_block_and_preserve_original_strings() -> None:
    updated = vi.apply(EXAMPLE)
    assert updated.replace(vi.BOUND_SECTION + "\n", "").replace(vi.AUX_BODY, "").replace(
        vi.INAME_NEW, vi.INAME
    ).replace(vi.VALUE_NEW, vi.VALUE) == EXAMPLE
