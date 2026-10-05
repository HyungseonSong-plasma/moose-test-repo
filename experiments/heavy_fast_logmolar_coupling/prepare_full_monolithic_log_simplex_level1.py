#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import runpy

HERE = Path(__file__).resolve().parent
BASE_GENERATOR = HERE / "prepare_full_monolithic_log_simplex.py"
BASE_INPUT = HERE / "full_monolithic_log_simplex.i"
OUT = HERE / "full_monolithic_log_simplex_level1.i"

# Generate the exact same full-monolithic physics problem as the global-LU
# baseline, then change only the linear-solver/preconditioner structure.
runpy.run_path(str(BASE_GENERATOR), run_name="__main__")
text = BASE_INPUT.read_text(encoding="utf-8")

old_petsc = """  petsc_options = '-snes_converged_reason -snes_monitor -snes_linesearch_monitor -ksp_converged_reason'
  petsc_options_iname = '-ksp_type -pc_type -pc_factor_shift_type -snes_linesearch_type'
  petsc_options_value = 'preonly lu NONZERO bt'
"""
new_petsc = """  petsc_options = '-snes_converged_reason -snes_monitor -snes_linesearch_monitor'
  petsc_options_iname = '-snes_linesearch_type'
  petsc_options_value = 'bt'
  l_tol = 1e-6
  l_max_its = 200
"""
if old_petsc not in text:
    raise RuntimeError("global-LU PETSc block not found in monolithic baseline")
text = text.replace(old_petsc, new_petsc, 1)

if "[Preconditioning]" in text:
    raise RuntimeError("unexpected pre-existing [Preconditioning] section")

level1 = """
[Preconditioning]
  active = 'FSP'

  [FSP]
    type = FSP
    full = true
    topsplit = 'hf'

    [hf]
      splitting = 'heavy fast'
      splitting_type = multiplicative
      petsc_options = '-ksp_converged_reason -ksp_monitor'
      petsc_options_iname = '-ksp_type -ksp_rtol -ksp_max_it'
      petsc_options_value = 'gmres 1e-6 200'
    []

    [heavy]
      vars = 'u v p eta_O2s eta_O2p eta_O eta_Om eta_Op eta_Os'
      petsc_options = '-ksp_converged_reason'
      petsc_options_iname = '-ksp_type -pc_type -pc_factor_shift_type'
      petsc_options_value = 'preonly lu NONZERO'
    []

    [fast]
      vars = 'log_ne log_energy potential'
      petsc_options = '-ksp_converged_reason'
      petsc_options_iname = '-ksp_type -pc_type -pc_factor_shift_type'
      petsc_options_value = 'preonly lu NONZERO'
    []
  []
[]
"""

marker = "\n[Outputs]\n"
if marker not in text:
    raise RuntimeError("[Outputs] insertion point not found")
text = text.replace(marker, "\n" + level1 + marker, 1)

# A/B contract: identical nonlinear variables/physics, only the linear solve differs.
for required in (
    "splitting = 'heavy fast'",
    "splitting_type = multiplicative",
    "vars = 'u v p eta_O2s eta_O2p eta_O eta_Om eta_Op eta_Os'",
    "vars = 'log_ne log_energy potential'",
    "type = PhysicsFVElectronEnergyJouleHeating",
    "property_name = charge_number_density",
    "dt = 1.0e-10",
):
    if required not in text:
        raise RuntimeError(f"Level-1 contract missing: {required}")
if "preonly lu NONZERO bt" in text:
    raise RuntimeError("global LU survived Level-1 generation")

OUT.write_text(text, encoding="utf-8")
print(f"wrote {OUT}")
print("Level-1 FieldSplit: heavy | (log_ne, log_energy, potential)")
print("outer split = multiplicative GMRES; block subsolves = preonly LU")
print("nonlinear physics and physical dt are unchanged from the global-LU baseline")
