#!/usr/bin/env python3
"""Harness-corrected coupled-FE Poisson rerun for Issue #228."""
from __future__ import annotations

import argparse
from pathlib import Path

from experiments.Issue228_p2_e1_w2_pg import run as base
from physics_harness.adapters.moose import blocks as mb

_ORIGINAL = base.build_fe_case


def corrected_build_fe_case(mode: str):
    text, meta = _ORIGINAL(mode)
    # SideDiffusiveFluxIntegral has separate FE/FV coefficient interfaces.
    # The plasma relative permittivity is unity in this controlled case, so
    # expose that same coefficient as an FE material property for the governed
    # Gauss-law diagnostic.  This changes no Poisson physics.
    text = mb.insert_child_block(
        text,
        "Materials",
        """  [r228_fe_eps_for_gauss]
    type = GenericConstantMaterial
    prop_names = r228_fe_relative_permittivity
    prop_values = 1
    block = plasma
  []""",
    )
    text = mb.replace_block(
        text,
        "Postprocessors/r31_gauss_flux_reduced",
        """  [r31_gauss_flux_reduced]
    type = SideDiffusiveFluxIntegral
    variable = potential_plasma
    boundary = r31_plasma_all_boundary
    diffusivity = r228_fe_relative_permittivity
    execute_on = 'INITIAL TIMESTEP_END'
  []""",
    )
    meta = {**meta, "fe_gauss_diagnostic_interface_corrected": True,
            "fe_gauss_diffusivity_material": "r228_fe_relative_permittivity"}
    return text, meta


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=base.FE_MODES, required=True)
    p.add_argument("--physics-opt", type=Path, required=True)
    p.add_argument("--results-root", type=Path, required=True)
    p.add_argument("--timeout", type=float, default=1800)
    p.add_argument("--self-test", action="store_true")
    a = p.parse_args()
    base.build_fe_case = corrected_build_fe_case
    if a.self_test:
        result = base.fe_self_test()
        import json
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["status"] == "PASS" else 1
    return base.run_fe(a)


if __name__ == "__main__":
    raise SystemExit(main())
