"""P0 test: the new study changes only the original atomic O initial state."""
from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import pytest

SRC = (Path(__file__).resolve().parents[1] /
       "experiments/Issue395_powered_chemistry_ladder/set_zero_initial_atomic_o.py")
spec = importlib.util.spec_from_file_location("zero_initial_atomic_o", SRC)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

BASE = """[Variables]
  [w_O2s]
    type = INSFVScalarFieldVariable
    initial_condition = 0.051546391752577324
    block = plasma
  []
  [w_O]
    type = INSFVScalarFieldVariable
    initial_condition = 0.10309278350515465
    block = plasma
  []
  [w_Os]
    type = INSFVScalarFieldVariable
    initial_condition = 0.12371134020618557
    block = plasma
  []
  [log_ne]
  []
  [log_ni]
  []
  [log_energy]
  []
[]
[FunctorMaterials]
  [neutral_O2_constraint]
    type = ADParsedFunctorMaterial
    property_name = w_O2_constraint
    functor_names = 'w_O2s w_O w_Os'
    functor_symbols = 's o a'
    expression = '1.0-s-o-a'
    block = plasma
  []
[]
"""


def test_exactly_one_w_o_initial_line() -> None:
    modified = module.change_generated_input(BASE)
    module.verify_generated_input(modified)
    old = "    initial_condition = 0.10309278350515465\n"
    new = "    initial_condition = 0.0\n"
    assert BASE.replace(old, new) == modified
    assert modified.splitlines().count("    initial_condition = 0.0") == 1
    assert "initial_condition = 0.12371134020618557" in modified
    assert "initial_condition = 0.051546391752577324" in modified


def test_preexisting_zero_initial_conditions_do_not_confuse_one_line_patch() -> None:
    # Actual generated ICP input contains many unrelated zero-valued ICs.
    original = BASE.replace(
        "  [w_O2s]\n",
        "  [u]\n    initial_condition = 0.0\n  []\n"
        "  [v]\n    initial_condition = 0.0\n  []\n"
        "  [w_O2s]\n",
    )
    updated = module.change_generated_input(original)
    module.verify_generated_input(updated)
    assert updated == original.replace(
        "    initial_condition = 0.10309278350515465\n",
        "    initial_condition = 0.0\n",
    )
    assert updated.count("initial_condition = 0.0") == 3


def test_o2_closure_reallocates_initial_mass_without_other_species_change() -> None:
    o2s = 0.051546391752577324
    os = 0.12371134020618557
    o = module.ORIGINAL_W_O
    before = 1.0 - o2s - os - o
    after = 1.0 - o2s - os
    assert math.isclose(after-before, o, rel_tol=0, abs_tol=1e-15)
    assert math.isclose(after+o2s+os, 1.0, rel_tol=0, abs_tol=1e-15)
    assert o > 0 and module.O_MASS_FRACTION == 0.0


@pytest.mark.parametrize("mutated", [
    BASE.replace("0.10309278350515465", "0.10"),
    BASE.replace("  [w_O]\n", ""),
    BASE.replace("  [w_O]\n", "  [w_O]\n  [w_O]\n    initial_condition = 0.10309278350515465\n  []\n"),
    BASE.replace("expression = '1.0-s-o-a'", "expression = '1.0-s-a'"),
    BASE.replace("  [log_ne]\n", "  [other]\n"),
])
def test_mismatched_source_fails_closed(mutated: str) -> None:
    with pytest.raises(ValueError):
        module.change_generated_input(mutated)


def test_repatch_denied_and_corrupted_zero_detected() -> None:
    updated = module.change_generated_input(BASE)
    with pytest.raises(ValueError):
        module.change_generated_input(updated)
    with pytest.raises(ValueError):
        module.verify_generated_input(updated.replace("initial_condition = 0.0", "initial_condition = 1e-12"))
