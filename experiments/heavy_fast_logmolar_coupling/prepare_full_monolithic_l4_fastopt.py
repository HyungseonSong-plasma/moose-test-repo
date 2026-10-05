#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
LEVEL_MATRIX = HERE / "prepare_full_monolithic_log_simplex_level_matrix.py"


def load_level_matrix_module():
    spec = importlib.util.spec_from_file_location("level_matrix", LEVEL_MATRIX)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load Level-4 matrix generator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def fast_block(variant: str) -> str:
    asm_iname = "-ksp_type -ksp_rtol -ksp_max_it -pc_type -pc_asm_overlap -sub_pc_type"
    asm_value = "gmres 1e-4 100 asm 1 ilu"

    if variant == "baseline":
        splitting = "electron poisson"
        split_type = "multiplicative"
        schur = ""
    elif variant == "reverse":
        splitting = "poisson electron"
        split_type = "multiplicative"
        schur = ""
    elif variant == "schur":
        splitting = "electron poisson"
        split_type = "schur"
        schur = "      schur_type = full\n      schur_pre = Sp\n"
    elif variant == "reverse-schur":
        splitting = "poisson electron"
        split_type = "schur"
        schur = "      schur_type = full\n      schur_pre = Sp\n"
    else:
        raise ValueError(variant)

    return f"""    [fast]
      vars = 'log_ne log_energy potential'
      splitting = '{splitting}'
      splitting_type = {split_type}
{schur}      petsc_options = '-ksp_converged_reason -ksp_monitor'
      petsc_options_iname = '-ksp_type -ksp_rtol -ksp_max_it'
      petsc_options_value = 'gmres 1e-5 100'
    []

    [electron]
      vars = 'log_ne log_energy'
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


def build(variant: str) -> Path:
    module = load_level_matrix_module()
    base = module.build(4)
    text = base.read_text(encoding="utf-8")

    baseline_block = fast_block("baseline")
    desired_block = fast_block(variant)
    text = replace_once(text, baseline_block, desired_block, "fast-block replacement")

    old_base = "file_base = full_monolithic_log_simplex_level4"
    new_base = f"file_base = full_monolithic_log_simplex_l4_fastopt_{variant.replace('-', '_')}"
    text = replace_once(text, old_base, new_base, "file_base replacement")

    # Physics must be byte-for-byte inherited from the successful Level-4 case;
    # only the fast block factorization/order changes.
    for token in (
        "dt = 1.0e-10",
        "type = PhysicsFVLogMolarElectrostaticDrift",
        "type = PhysicsFVElectronEnergyJouleHeating",
        "type = PhysicsFVElectronGroundedSheathCollectionBC",
        "property_name = charge_number_density",
        "boomeramg",
        "vars = 'log_ne log_energy potential'",
    ):
        if token not in text:
            raise RuntimeError(f"full-physics contract missing: {token}")

    if variant.endswith("schur"):
        for token in ("splitting_type = schur", "schur_type = full", "schur_pre = Sp"):
            if token not in desired_block:
                raise RuntimeError(f"Schur contract missing: {token}")

    out = HERE / f"full_monolithic_l4_fastopt_{variant.replace('-', '_')}.i"
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out}")
    print(f"L4 fast optimization variant={variant}; physics unchanged; dt=0.1 ns")
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--variant",
        choices=("baseline", "reverse", "schur", "reverse-schur"),
        required=True,
    )
    args = parser.parse_args()
    build(args.variant)


if __name__ == "__main__":
    main()
