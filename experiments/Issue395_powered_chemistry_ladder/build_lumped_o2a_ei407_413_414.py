#!/usr/bin/env python3
"""EI-407/413/414 -> O2(a) user-selected lumped-rate research overlay.

This is NOT a validated state-resolved product model. The three original
Boltzmann 100-point rates and three independent eV losses are preserved.
"""
from __future__ import annotations

import argparse
import hashlib
import math
import shutil
from pathlib import Path

CHANNELS = ((407, "EI-407_O2_X.txt"), (413, "EI-413_O2_X.txt"), (414, "EI-414_O2_X.txt"))
BASE_REQUIRED = ("[w_O2s]", "[log_energy]", "property_name = w_O2_constraint",
                 "property_name = rho_neutral", "property_name = n_e_physical",
                 "mean_energy = mean_en_solved")
FORBIDDEN = ("R_EI407", "R_EI413", "R_EI414", "R_O2s",
             "S_O2s_mass_EI407_413_414", "S_energy_EI407_413_414")


def table(path: Path) -> list[tuple[float, float]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        fields = line.split()
        if len(fields) != 2:
            raise ValueError(f"{path}: expected two lookup columns")
        e, k = map(float, fields)
        if not math.isfinite(e) or not math.isfinite(k) or e <= 0 or k < 0:
            raise ValueError(f"{path}: invalid rate/mean energy")
        if rows and e <= rows[-1][0]:
            raise ValueError(f"{path}: mean-energy grid is not strictly increasing")
        rows.append((e, k))
    if len(rows) != 100:
        raise ValueError(f"{path}: expected 100 rows, got {len(rows)}")
    return rows


def build(base: str, paths: dict[int, str]) -> str:
    if set(paths) != {407, 413, 414}:
        raise ValueError("exactly 407, 413 and 414 required")
    missing = [key for key in BASE_REQUIRED if key not in base]
    duplicate = [key for key in FORBIDDEN if key in base]
    if missing or duplicate:
        raise ValueError(f"base missing={missing}, duplicate chemistry={duplicate}")
    owners = []
    for rid, _ in CHANNELS:
        filename = paths[rid]
        if "'" in filename or "\n" in filename:
            raise ValueError("unsupported rate filename")
        owners.append(f"""  [o2a_ei{rid}_rate]
    type = PhysicsElectronImpactRateMaterial
    rate_table_file = '{filename}'
    mean_energy = mean_en_solved
    electron_number_density = n_e_physical
    target_molar_concentration = c_O2_O2a_lumped
    reaction_progress = R_EI{rid}
    block = plasma
  []""")
    rate_owners = "\n".join(owners)
    return f"""# Research-only: EI-413/414 effective excitations lumped into O2(a)/O2s.
# This does not prove their microscopic product branching.
[FunctorMaterials]
  [o2a_lumped_o2_concentration]
    type = ADParsedFunctorMaterial
    property_name = c_O2_O2a_lumped
    functor_names = 'rho_neutral w_O2_constraint'
    functor_symbols = 'rho w'
    expression = 'rho*w/0.032'
    block = plasma
  []
{rate_owners}
  [o2a_lumped_progress]
    type = ADParsedFunctorMaterial
    property_name = R_O2s_EI407_413_414
    functor_names = 'R_EI407 R_EI413 R_EI414'
    functor_symbols = 'a b c'
    expression = 'a+b+c'
    block = plasma
  []
  [o2a_lumped_mass_source]
    type = ADParsedFunctorMaterial
    property_name = S_O2s_mass_EI407_413_414
    functor_names = 'R_O2s_EI407_413_414'
    functor_symbols = 'R'
    expression = '0.032*R'
    block = plasma
  []
  [o2a_lumped_implicit_o2_sink]
    type = ADParsedFunctorMaterial
    property_name = S_O2_implicit_EI407_413_414
    functor_names = 'R_O2s_EI407_413_414'
    functor_symbols = 'R'
    expression = '-0.032*R'
    block = plasma
  []
  [o2a_lumped_energy_sink]
    type = ADParsedFunctorMaterial
    property_name = S_energy_EI407_413_414
    functor_names = 'R_EI407 R_EI413 R_EI414'
    functor_symbols = 'a b c'
    expression = '-0.977*a-8.4*b-10.0*c'
    block = plasma
  []
  [o2a_lumped_mass_closure]
    type = ADParsedFunctorMaterial
    property_name = S_mass_closure_EI407_413_414
    functor_names = 'S_O2s_mass_EI407_413_414 S_O2_implicit_EI407_413_414'
    functor_symbols = 'p n'
    expression = 'p+n'
    block = plasma
  []
[]
[FVKernels]
  [o2a_lumped_species_source]
    type = PhysicsFVSpeciesReactionSource
    variable = w_O2s
    source = S_O2s_mass_EI407_413_414
    block = plasma
  []
[]
[Kernels]
  [o2a_lumped_energy_source]
    type = FunctorKernel
    variable = log_energy
    functor = S_energy_EI407_413_414
    functor_on_rhs = true
    block = plasma
  []
[]
[Postprocessors]
  [o2a_lumped_rate407_avg]
    type = ElementAverageFunctorPostprocessor
    functor = R_EI407
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [o2a_lumped_rate413_avg]
    type = ElementAverageFunctorPostprocessor
    functor = R_EI413
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [o2a_lumped_rate414_avg]
    type = ElementAverageFunctorPostprocessor
    functor = R_EI414
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [o2a_lumped_total_avg]
    type = ElementAverageFunctorPostprocessor
    functor = R_O2s_EI407_413_414
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [o2a_lumped_energy_avg]
    type = ElementAverageFunctorPostprocessor
    functor = S_energy_EI407_413_414
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [o2a_lumped_mass_closure_avg]
    type = ElementAverageFunctorPostprocessor
    functor = S_mass_closure_EI407_413_414
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]
"""


def prepare(base_input: Path, rate_dir: Path, output: Path) -> Path:
    base_input, rate_dir, output = (p.resolve() for p in (base_input, rate_dir, output))
    if output == base_input:
        raise ValueError("refusing to replace baseline input")
    grids = {rid: table(rate_dir / name) for rid, name in CHANNELS}
    if any(not math.isclose(a[0], b[0], rel_tol=1e-11, abs_tol=1e-10)
           for rid in (413, 414) for a, b in zip(grids[407], grids[rid])):
        raise ValueError("EI-407/413/414 rate grids differ")
    dest_dir = output.parent / "private_rates"
    dest_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for rid, name in CHANNELS:
        src = rate_dir / name
        dest = dest_dir / name
        if src.resolve() != dest.resolve():
            if dest.exists() and hashlib.sha256(src.read_bytes()).digest() != hashlib.sha256(dest.read_bytes()).digest():
                raise ValueError(f"rate table conflict at {dest}")
            shutil.copyfile(src, dest)
        try:
            paths[rid] = dest.relative_to(Path.cwd().resolve()).as_posix()
        except ValueError as error:
            raise ValueError("output must be under the MOOSE execution directory") from error
    output.write_text(build(base_input.read_text(encoding="utf-8"), paths), encoding="utf-8")
    return output


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--base-input", required=True, type=Path)
    p.add_argument("--rate-dir", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    print("EI407_EI413_EI414_O2A_LUMPED_OVERLAY_STAGED:", prepare(args.base_input, args.rate_dir, args.output))
    print("SCIENCE_STATUS: USER_SELECTED_LUMP; POWERED_ICP: NOT_RUN")


if __name__ == "__main__":
    main()
