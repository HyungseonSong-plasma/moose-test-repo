#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import runpy

HERE = Path(__file__).resolve().parent
BASE_GENERATOR = HERE / "prepare_heavy_electron_continuity_full.py"
BASE_INPUT = HERE / "heavy_electron_continuity_full.i"
OUT = HERE / "heavy_electron_continuity_level1.i"

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
    raise RuntimeError("global-LU PETSc block not found")
text = text.replace(old_petsc, new_petsc, 1)

level1 = """
[Preconditioning]
  active = 'FSP'

  [FSP]
    type = FSP
    full = true
    topsplit = 'he'

    [he]
      splitting = 'heavy electron'
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

    [electron]
      vars = 'log_ne'
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

for required in (
    "splitting = 'heavy electron'",
    "splitting_type = multiplicative",
    "vars = 'u v p eta_O2s eta_O2p eta_O eta_Om eta_Op eta_Os'",
    "vars = 'log_ne'",
    "type = PhysicsFVLogMolarElectronTimeDerivative",
    "type = PhysicsFVLogMolarElectronDiffusion",
    "dt = 1.0e-9",
):
    if required not in text:
        raise RuntimeError(f"Level-1 heavy+electron contract missing: {required}")
if "preonly lu NONZERO bt" in text:
    raise RuntimeError("global LU survived Level-1 generation")
for forbidden in (
    "PhysicsFVLogMolarElectrostaticDrift",
    "PhysicsFVElectronEnergyJouleHeating",
    "[log_energy]",
    "[potential]\n",
):
    if forbidden in text:
        raise RuntimeError(f"forbidden fast-physics token survived Level-1: {forbidden}")

OUT.write_text(text, encoding="utf-8")
print(f"wrote {OUT}")
print("Level-1 FieldSplit: heavy | electron-continuity")
print("outer split = multiplicative GMRES; block subsolves = preonly LU")
print("physics and dt = 1 ns are identical to the global-LU A/B baseline")
