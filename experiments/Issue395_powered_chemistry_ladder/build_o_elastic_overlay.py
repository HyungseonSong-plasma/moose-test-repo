#!/usr/bin/env python3
"""Add only EI17 O-atom electron elastic collision to Issue #395 oxygen ICP.

Reaction: e + O -> e + O
One strict tabulated progress R_elastic_O, zero particle stoichiometry.
Electron-energy exchange per collision [eV]:
  delta_eps = 3*m_e/(M_O/N_A) * ((2/3)*mean_en_solved-(kB/e)*T_g).
The same progress drives the unique energy source -delta_eps * R_elastic_O.
Source rate table is the existing physics_app/data/electron_impact/o_elastic.txt.
"""
from __future__ import annotations

import argparse
import hashlib
import math
from pathlib import Path

M_O = 0.016
M_E = 9.1093837015e-31
N_A = 6.02214076e23
K_B_OVER_E = 8.617333262145e-5
ELASTIC_FACTOR = 3.0 * M_E / (M_O / N_A)
CANONICAL_TABLE_BLOB = "de9d718cf197d129db5d02fc3141c92969eca860"


def verify_table(path: Path) -> None:
    raw = path.read_bytes()
    sha = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()
    if sha != CANONICAL_TABLE_BLOB:
        raise ValueError(f"EI17 production table Git blob mismatch: {sha}")
    rows = [tuple(map(float, line.split())) for line in raw.decode().splitlines() if line.strip()]
    if len(rows) != 100 or any(len(row) != 2 for row in rows):
        raise ValueError("EI17 expected 100 paired rate rows")
    if any(not all(math.isfinite(v) for v in row) or row[1] < 0 for row in rows):
        raise ValueError("EI17 invalid table data")
    if any(b[0] <= a[0] for a, b in zip(rows, rows[1:])):
        raise ValueError("EI17 rate table energy grid not increasing")
    anchors = {1.40991: 2.08e10, 5.73276: 5.89e10, 22.1378: 2.19e11}
    values = dict(rows)
    if any(values.get(x) != y for x, y in anchors.items()):
        raise ValueError("EI17 rate anchors do not match frozen contract")


def build(base: str, table_name: str) -> str:
    required = (
        "[log_ne]", "[log_energy]", "[w_O]", "property_name = rho_neutral",
        "property_name = n_e_physical", "mean_energy = mean_en_solved",
        "T_g_fixed",
    )
    missing = [s for s in required if s not in base]
    if missing:
        raise ValueError(f"EI17 missing required canonical input providers: {missing}")
    if "reaction_progress = R_elastic_O" in base or "S_electron_energy_EI17" in base:
        raise ValueError("EI17 canonical progress/energy owner already present")

    overlay = f"""# Issue #395 EI17: e + O -> e + O elastic collision only.
# Atomic O concentration is taken from canonical heavy mixture.
# No electron-number source and no heavy-species mass sources.
# Single canonical molar progress R_elastic_O [mol/(m3 s)].
[FunctorMaterials]
  [ei17_o_concentration]
    type = ADParsedFunctorMaterial
    property_name = c_O_EI17
    functor_names = 'rho_neutral w_O'
    functor_symbols = 'rho w'
    expression = 'rho*w/{M_O:.17g}'
    block = plasma
  []
  [ei17_progress]
    type = PhysicsElectronImpactRateMaterial
    rate_table_file = {table_name}
    mean_energy = mean_en_solved
    electron_number_density = n_e_physical
    target_molar_concentration = c_O_EI17
    reaction_progress = R_elastic_O
    block = plasma
  []
  [ei17_delta_energy]
    type = ADParsedFunctorMaterial
    property_name = delta_epsilon_EI17_eV
    functor_names = 'mean_en_solved T_g_fixed'
    functor_symbols = 'eps Tg'
    expression = '{ELASTIC_FACTOR:.17g}*((2.0/3.0)*eps-{K_B_OVER_E:.17g}*Tg)'
    block = plasma
  []
  [ei17_electron_energy_exchange]
    type = ADParsedFunctorMaterial
    property_name = S_electron_energy_EI17
    functor_names = 'delta_epsilon_EI17_eV R_elastic_O'
    functor_symbols = 'de R'
    expression = '-de*R'
    block = plasma
  []
[]
[Kernels]
  [ei17_electron_energy_exchange]
    type = FunctorKernel
    variable = log_energy
    functor = S_electron_energy_EI17
    functor_on_rhs = true
    block = plasma
  []
[]
[Postprocessors]
  [ei17_rate_min]
    type = ADElementExtremeFunctorValue
    functor = R_elastic_O
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ei17_rate_max]
    type = ADElementExtremeFunctorValue
    functor = R_elastic_O
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ei17_rate_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = R_elastic_O
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ei17_delta_energy_min]
    type = ADElementExtremeFunctorValue
    functor = delta_epsilon_EI17_eV
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ei17_delta_energy_max]
    type = ADElementExtremeFunctorValue
    functor = delta_epsilon_EI17_eV
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [ei17_energy_source_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_electron_energy_EI17
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]
"""
    if overlay.count("reaction_progress = R_elastic_O\n") != 1:
        raise AssertionError("EI17 progress must have exactly one owner")
    if "variable = log_ne" in overlay or "[FVKernels]" in overlay:
        raise AssertionError("EI17 elastic should not change particle numbers")
    return overlay


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--elastic-table", default="o_elastic.txt")
    parser.add_argument("--source-table", required=True, type=Path)
    args = parser.parse_args()
    verify_table(args.source_table)
    out = build(args.base_input.read_text(encoding="utf-8"), args.elastic_table)
    args.output.write_text(out, encoding="utf-8")
    print("ISSUE395_EI17_O_ELASTIC_OVERLAY_BUILD_PASS")
    print("progress_owner=R_elastic_O")
    print("net_electron_stoich=0")
    print("net_oxygen_stoich=0")
    print(f"atomic_O_elastic_factor={ELASTIC_FACTOR:.17g}")
    print(f"output={args.output}")


if __name__ == "__main__":
    main()
