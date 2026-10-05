#!/usr/bin/env python3
from __future__ import annotations

import argparse
import runpy
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE_GENERATOR = HERE / "prepare_full_monolithic_log_simplex.py"
BASE_INPUT = HERE / "full_monolithic_log_simplex.i"

HEAVY_VARS = "u v p eta_O2s eta_O2p eta_O eta_Om eta_Op eta_Os"
SPECIES_VARS = "eta_O2s eta_O2p eta_O eta_Om eta_Op eta_Os"
ELECTRON_VARS = "log_ne log_energy"


def replace_global_solver(text: str) -> str:
    old = """  petsc_options = '-snes_converged_reason -snes_monitor -snes_linesearch_monitor -ksp_converged_reason'
  petsc_options_iname = '-ksp_type -pc_type -pc_factor_shift_type -snes_linesearch_type'
  petsc_options_value = 'preonly lu NONZERO bt'
"""
    new = """  petsc_options = '-snes_converged_reason -snes_monitor -snes_linesearch_monitor'
  petsc_options_iname = '-snes_linesearch_type'
  petsc_options_value = 'bt'
  l_tol = 1e-6
  l_max_its = 200
"""
    if old not in text:
        raise RuntimeError("global-LU PETSc block not found")
    return text.replace(old, new, 1)


def insert_preconditioning(text: str, body: str) -> str:
    if "[Preconditioning]" in text:
        raise RuntimeError("unexpected pre-existing [Preconditioning] section")
    marker = "\n[Outputs]\n"
    if marker not in text:
        raise RuntimeError("[Outputs] insertion point not found")
    return text.replace(marker, "\n" + body.rstrip() + "\n" + marker, 1)


def common_top(inner: str) -> str:
    return f"""[Preconditioning]
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
{inner.rstrip()}
  []
[]
"""


def level2() -> str:
    # Heavy remains one exact block.  Fast is decomposed into the strongly
    # coupled electron/energy pair and the electrostatic potential.
    inner = f"""
    [heavy]
      vars = '{HEAVY_VARS}'
      petsc_options = '-ksp_converged_reason'
      petsc_options_iname = '-ksp_type -pc_type -pc_factor_shift_type'
      petsc_options_value = 'preonly lu NONZERO'
    []

    [fast]
      splitting = 'electron poisson'
      splitting_type = multiplicative
      petsc_options = '-ksp_converged_reason -ksp_monitor'
      petsc_options_iname = '-ksp_type -ksp_rtol -ksp_max_it'
      petsc_options_value = 'gmres 1e-6 100'
    []

    [electron]
      vars = '{ELECTRON_VARS}'
      petsc_options = '-ksp_converged_reason'
      petsc_options_iname = '-ksp_type -pc_type -pc_factor_shift_type'
      petsc_options_value = 'preonly lu NONZERO'
    []

    [poisson]
      vars = 'potential'
      petsc_options = '-ksp_converged_reason'
      petsc_options_iname = '-ksp_type -pc_type -pc_factor_shift_type'
      petsc_options_value = 'preonly lu NONZERO'
    []
"""
    return common_top(inner)


def level3() -> str:
    # Split the heavy block into flow and heavy-species transport while keeping
    # exact LU leaf solves.  Fast retains the Level-2 electron|Poisson split.
    inner = f"""
    [heavy]
      splitting = 'flow species'
      splitting_type = multiplicative
      petsc_options = '-ksp_converged_reason -ksp_monitor'
      petsc_options_iname = '-ksp_type -ksp_rtol -ksp_max_it'
      petsc_options_value = 'gmres 1e-6 100'
    []

    [flow]
      vars = 'u v p'
      petsc_options = '-ksp_converged_reason'
      petsc_options_iname = '-ksp_type -pc_type -pc_factor_shift_type'
      petsc_options_value = 'preonly lu NONZERO'
    []

    [species]
      vars = '{SPECIES_VARS}'
      petsc_options = '-ksp_converged_reason'
      petsc_options_iname = '-ksp_type -pc_type -pc_factor_shift_type'
      petsc_options_value = 'preonly lu NONZERO'
    []

    [fast]
      splitting = 'electron poisson'
      splitting_type = multiplicative
      petsc_options = '-ksp_converged_reason -ksp_monitor'
      petsc_options_iname = '-ksp_type -ksp_rtol -ksp_max_it'
      petsc_options_value = 'gmres 1e-6 100'
    []

    [electron]
      vars = '{ELECTRON_VARS}'
      petsc_options = '-ksp_converged_reason'
      petsc_options_iname = '-ksp_type -pc_type -pc_factor_shift_type'
      petsc_options_value = 'preonly lu NONZERO'
    []

    [poisson]
      vars = 'potential'
      petsc_options = '-ksp_converged_reason'
      petsc_options_iname = '-ksp_type -pc_type -pc_factor_shift_type'
      petsc_options_value = 'preonly lu NONZERO'
    []
"""
    return common_top(inner)


def level4() -> str:
    # Preserve the Level-3 physics hierarchy, but remove direct LU from the leaf
    # blocks.  Flow gets an inner velocity|pressure Schur split; transport-like
    # blocks use GMRES+ASM(ILU); Poisson uses BoomerAMG.
    asm_iname = "-ksp_type -ksp_rtol -ksp_max_it -pc_type -pc_asm_overlap -sub_pc_type"
    asm_value = "gmres 1e-4 100 asm 1 ilu"
    inner = f"""
    [heavy]
      splitting = 'flow species'
      splitting_type = multiplicative
      petsc_options = '-ksp_converged_reason -ksp_monitor'
      petsc_options_iname = '-ksp_type -ksp_rtol -ksp_max_it'
      petsc_options_value = 'gmres 1e-5 100'
    []

    [flow]
      splitting = 'velocity pressure'
      splitting_type = schur
      schur_type = full
      schur_pre = Sp
      petsc_options = '-ksp_converged_reason -ksp_monitor'
      petsc_options_iname = '-ksp_type -ksp_rtol -ksp_max_it'
      petsc_options_value = 'gmres 1e-4 100'
    []

    [velocity]
      vars = 'u v'
      petsc_options = '-ksp_converged_reason'
      petsc_options_iname = '{asm_iname}'
      petsc_options_value = '{asm_value}'
    []

    [pressure]
      vars = 'p'
      petsc_options = '-ksp_converged_reason'
      petsc_options_iname = '{asm_iname}'
      petsc_options_value = '{asm_value}'
    []

    [species]
      vars = '{SPECIES_VARS}'
      petsc_options = '-ksp_converged_reason'
      petsc_options_iname = '{asm_iname}'
      petsc_options_value = '{asm_value}'
    []

    [fast]
      splitting = 'electron poisson'
      splitting_type = multiplicative
      petsc_options = '-ksp_converged_reason -ksp_monitor'
      petsc_options_iname = '-ksp_type -ksp_rtol -ksp_max_it'
      petsc_options_value = 'gmres 1e-5 100'
    []

    [electron]
      vars = '{ELECTRON_VARS}'
      petsc_options = '-ksp_converged_reason'
      petsc_options_iname = '{asm_iname}'
      petsc_options_value = '{asm_value}'
    []

    [poisson]
      vars = 'potential'
      petsc_options = '-ksp_converged_reason'
      petsc_options_iname = '-ksp_type -pc_type -pc_hypre_type'
      petsc_options_value = 'preonly hypre boomeramg'
    []
"""
    return common_top(inner)


def build(level: int) -> Path:
    runpy.run_path(str(BASE_GENERATOR), run_name="__main__")
    text = BASE_INPUT.read_text(encoding="utf-8")
    text = replace_global_solver(text)
    if level == 2:
        pre = level2()
    elif level == 3:
        pre = level3()
    elif level == 4:
        pre = level4()
    else:
        raise ValueError(level)
    text = insert_preconditioning(text, pre)

    # Common physics contract: this is the exact full-monolithic discriminator,
    # including electron continuity, electron energy, Poisson, drift, Joule and
    # grounded sheath BCs.  Only preconditioning differs across matrix entries.
    for token in (
        "[log_ne]",
        "[log_energy]",
        "[potential]",
        "type = PhysicsFVLogMolarElectrostaticDrift",
        "type = PhysicsFVElectronEnergyJouleHeating",
        "type = PhysicsFVElectronGroundedSheathCollectionBC",
        "property_name = charge_number_density",
        "dt = 1.0e-10",
        "splitting = 'heavy fast'",
    ):
        if token not in text:
            raise RuntimeError(f"Level-{level} full-physics contract missing: {token}")
    if "preonly lu NONZERO bt" in text:
        raise RuntimeError(f"global LU survived Level-{level} generation")

    if level >= 2 and "splitting = 'electron poisson'" not in text:
        raise RuntimeError("fast electron|Poisson split missing")
    if level >= 3 and "splitting = 'flow species'" not in text:
        raise RuntimeError("heavy flow|species split missing")
    if level == 4:
        for token in ("splitting_type = schur", "pc_hypre_type", "boomeramg"):
            if token not in text:
                raise RuntimeError(f"Level-4 scalable solver token missing: {token}")

    out = HERE / f"full_monolithic_log_simplex_level{level}.i"
    # Give every matrix entry a unique output base so artifacts cannot collide.
    text = text.replace("file_base = full_monolithic_log_simplex", f"file_base = full_monolithic_log_simplex_level{level}")
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out}")
    print(f"full monolithic Level-{level} matrix case ready; physical dt unchanged at 0.1 ns")
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--level", type=int, choices=(2, 3, 4), required=True)
    args = parser.parse_args()
    build(args.level)


if __name__ == "__main__":
    main()
