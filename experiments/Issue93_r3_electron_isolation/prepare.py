#!/usr/bin/env python3
"""Build the Issue #93 J1 frozen-heavy real-QVT electron discriminator."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from recipes.issue91_r3 import BOUNDARIES_TO_AVOID, MEAN_ELECTRON_ENERGY_EV

ROOT = Path(__file__).resolve().parents[2]
SOURCE_CASE = ROOT / "experiments" / "Issue91_real_qvt_r3" / "r3_e0"
DEFAULT_DT = 1.0e-8
P_FROZEN = 1.33322
TG_FROZEN = 600.0
NE_INITIAL = 1.0e16


class PrepareError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_top_level_block(text: str, name: str) -> str:
    lines = text.splitlines()
    collecting = False
    depth = 0
    out: list[str] = []
    for raw in lines:
        stripped = raw.strip()
        if not collecting:
            if stripped == f"[{name}]":
                collecting = True
                depth = 1
                out.append(raw)
            continue
        out.append(raw)
        if stripped.startswith("[") and stripped.endswith("]"):
            if stripped == "[]":
                depth -= 1
                if depth == 0:
                    return "\n".join(out) + "\n"
            else:
                depth += 1
    raise PrepareError(f"top-level block [{name}] not found or unterminated")


def build_input(source_case: Path = SOURCE_CASE, dt: float = DEFAULT_DT) -> str:
    if not dt > 0:
        raise PrepareError("dt must be positive")
    heavy = (source_case / "heavy_base.i").read_text()
    mesh = extract_top_level_block(heavy, "Mesh")

    return f"""# Issue #93 J1 diagnostic-only frozen-heavy electron discriminator
# Same real-QVT mesh and accepted Issue91/Issue2 electron transport semantics.
# Heavy nonlinear equations are intentionally absent. Poisson is OFF.

p_frozen_value = {P_FROZEN:.17g}
T_g_frozen_value = {TG_FROZEN:.17g}
n_e_value = {NE_INITIAL:.17g}

{mesh}
[Problem]
  kernel_coverage_check = false
[]

[Variables]
  [n_e]
    type = MooseVariableFVReal
    initial_condition = ${{n_e_value}}
    block = plasma
  []
[]

[FunctorMaterials]
  [frozen_state]
    type = ADGenericFunctorMaterial
    prop_names = 'p_frozen T_g_frozen'
    prop_values = '${{p_frozen_value}} ${{T_g_frozen_value}}'
    block = plasma
  []

  [electron_constants]
    type = ADGenericFunctorMaterial
    prop_names = 'mean_en carrier_one'
    prop_values = '{MEAN_ELECTRON_ENERGY_EV:.17g} 1.0'
    block = plasma
  []

  [electron_transport]
    type = QPXElectronTransportLookupMaterial
    property_table_file = electron_moments.txt
    mean_energy = mean_en
    pressure = p_frozen
    gas_temperature = T_g_frozen
    bounds_policy = error
    block = plasma
  []
[]

[Functions]
  [phi_prescribed]
    type = ParsedFunction
    expression = '0'
  []
[]

[FVKernels]
  [n_e_time]
    type = FVTimeKernel
    variable = n_e
    block = plasma
  []
  [n_e_diffusion]
    type = FVDiffusion
    variable = n_e
    coeff = electron_diffusion
    block = plasma
  []
  [n_e_drift]
    type = QPXFVElectrostaticDrift
    variable = n_e
    potential = phi_prescribed
    mobility = electron_mobility
    carrier = carrier_one
    charge_number = -1
    advected_interp_method = upwind
    boundaries_to_avoid = '{BOUNDARIES_TO_AVOID}'
    block = plasma
  []
[]

[Postprocessors]
  [carrier_one_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = carrier_one
    block = plasma
  []
  [n_e_inventory]
    type = ADElementIntegralFunctorPostprocessor
    functor = n_e
    block = plasma
  []
  [n_e_avg]
    type = ElementAverageFunctorPostprocessor
    functor = n_e
    block = plasma
  []
  [n_e_min]
    type = ADElementExtremeFunctorValue
    functor = n_e
    value_type = min
    block = plasma
  []
  [n_e_max]
    type = ADElementExtremeFunctorValue
    functor = n_e
    value_type = max
    block = plasma
  []
  [electron_mobility_avg]
    type = ElementAverageFunctorPostprocessor
    functor = electron_mobility
    block = plasma
  []
  [electron_diffusion_avg]
    type = ElementAverageFunctorPostprocessor
    functor = electron_diffusion
    block = plasma
  []
[]

[Debug]
  show_var_residual_norms = true
[]

[Executioner]
  type = Transient
  scheme = implicit-euler
  solve_type = NEWTON
  dt = {dt:.17g}
  end_time = {dt:.17g}
  num_steps = 1
  petsc_options_iname = '-pc_type -pc_factor_shift_type'
  petsc_options_value = 'lu NONZERO'
  line_search = none
  nl_rel_tol = 1e-8
  nl_abs_tol = 1e-11
  nl_max_its = 8
  automatic_scaling = true
  off_diagonals_in_auto_scaling = true
  compute_scaling_once = false
  abort_on_solve_fail = true
[]

[Outputs]
  csv = true
  execute_on = 'INITIAL TIMESTEP_END'
[]
"""


def prepare_case(dest: Path, source_case: Path = SOURCE_CASE, dt: float = DEFAULT_DT) -> dict[str, Any]:
    source_case = source_case.resolve()
    dest = dest.resolve()
    required = ("heavy_base.i", "qvt.msh", "electron_moments.txt")
    for name in required:
        if not (source_case / name).is_file():
            raise PrepareError(f"missing source asset: {source_case / name}")
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_case / "qvt.msh", dest / "qvt.msh")
    shutil.copy2(source_case / "electron_moments.txt", dest / "electron_moments.txt")
    input_text = build_input(source_case, dt)
    (dest / "input.i").write_text(input_text)
    evidence = {
        "issue": 93,
        "stage": "J1_PREPARE",
        "scientific_acceptance_eligible": False,
        "source_case": str(source_case),
        "dt_s": dt,
        "p_frozen_Pa": P_FROZEN,
        "T_g_frozen_K": TG_FROZEN,
        "n_e_initial_m3": NE_INITIAL,
        "field_V_m": 0.0,
        "heavy_nonlinear_equations": "REMOVED_FOR_DIAGNOSTIC",
        "poisson": "OFF",
        "electron_contract": "Issue91 exact lookup/drift parameterization with p,T_g frozen",
        "mesh_sha256": _sha256(dest / "qvt.msh"),
        "electron_table_sha256": _sha256(dest / "electron_moments.txt"),
        "input_sha256": hashlib.sha256(input_text.encode()).hexdigest(),
    }
    (dest / "prepare_evidence.json").write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", type=Path, required=True)
    parser.add_argument("--source-case", type=Path, default=SOURCE_CASE)
    parser.add_argument("--dt", type=float, default=DEFAULT_DT)
    args = parser.parse_args()
    try:
        evidence = prepare_case(args.dest, args.source_case, args.dt)
    except (PrepareError, OSError, ValueError) as exc:
        print(f"ISSUE93_J1_PREPARE_ERROR: {exc}")
        return 2
    print(json.dumps(evidence, indent=2, sort_keys=True))
    print("ISSUE93_J1_PREPARE: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
