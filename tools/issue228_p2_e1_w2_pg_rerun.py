#!/usr/bin/env python3
"""Harness-corrected rerun wrapper for the Issue #228 P2/E1/W2/PG campaign.

This wrapper changes no intended scientific axis. It only corrects three
construction defects found in workflow run 34952758298:

1. FE Gauss postprocessor: use the FE `diffusivity` contract instead of the
   FV `functor_diffusivity` contract. The plasma relative permittivity is 1,
   so the diagnostic flux coefficient is exactly 1.
2. E1 one-cell A/V balance: add an FVDiffusion flux kernel and use a constant
   FVNeumannBC so the prescribed boundary flux actually participates in the
   FV face residual.
3. W2 frozen FV solve: restrict kernel coverage checking to the plasma block;
   the diagnostic nonlinear variable and kernels are intentionally
   plasma-restricted while the imported reactor mesh retains all subdomains.
"""
from __future__ import annotations

from experiments.Issue228_p2_e1_w2_pg import run as base
from physics_harness.adapters.moose import blocks as mb
from physics_harness.adapters.moose import parameters as mp


_original_build_fe_case = base.build_fe_case
_original_build_e1_input = base.build_e1_input
_original_build_w2_input = base.build_w2_input


def build_fe_case(mode: str):
    text, meta = _original_build_fe_case(mode)
    old = "    functor_diffusivity = relative_permittivity"
    new = "    diffusivity = 1"
    if text.count(old) != 1:
        raise RuntimeError(
            f"expected exactly one FV Gauss diffusivity contract, got {text.count(old)}"
        )
    text = text.replace(old, new, 1)
    return text, {
        **meta,
        "harness_correction": "FE SideDiffusiveFluxIntegral diffusivity contract",
        "gauss_flux_diffusivity": 1.0,
    }


def build_e1_input(h_m: float) -> str:
    text = _original_build_e1_input(h_m)
    old = """    type = FVFunctorNeumannBC
    variable = q
    boundary = right
    functor = 1
    factor = 1"""
    new = """    type = FVNeumannBC
    variable = q
    boundary = right
    value = 1"""
    if old not in text:
        raise RuntimeError("E1 expected FVFunctorNeumannBC block not found")
    text = text.replace(old, new, 1)
    text = mb.insert_child_block(
        text,
        "FVKernels",
        """  [diffusion_flux_carrier]
    type = FVDiffusion
    variable = q
    coeff = 1
  []""",
    )
    return text


def build_w2_input() -> str:
    text = _original_build_w2_input()
    return """[Problem]
  kernel_coverage_check = ONLY_LIST
  kernel_coverage_block_list = plasma
[]

""" + text


def fe_self_test():
    result = base.fe_self_test.__wrapped__() if hasattr(base.fe_self_test, "__wrapped__") else None
    # We replace base.fe_self_test below, so compute the original checks explicitly
    # before replacement by temporarily restoring the original build function.
    current = base.build_fe_case
    try:
        base.build_fe_case = build_fe_case
        checks = {}
        for mode in base.FE_MODES:
            text, meta = build_fe_case(mode)
            checks[f"{mode}:fe_family"] = mp.get_parameter(text, "Variables/potential_plasma", "family") == "LAGRANGE"
            checks[f"{mode}:fe_order"] = mp.get_parameter(text, "Variables/potential_plasma", "order") == "FIRST"
            checks[f"{mode}:no_fv_phi_diff"] = not mb.has_block(text, "FVKernels/r31_phi_diffusion")
            checks[f"{mode}:no_fv_phi_source"] = not mb.has_block(text, "FVKernels/r31_phi_charge_source")
            checks[f"{mode}:no_fv_phi_bc"] = not mb.has_block(text, "FVBCs/r31_phi_ground_all")
            checks[f"{mode}:fe_diff"] = mp.get_parameter(text, "Kernels/r228_fe_phi_diffusion", "type") == "Diffusion"
            checks[f"{mode}:fe_source"] = mp.get_parameter(text, "Kernels/r228_fe_phi_charge_source", "functor") == "poisson_charge_source"
            checks[f"{mode}:fe_ground"] = mp.get_parameter(text, "BCs/r228_fe_phi_ground", "boundary") == base.axis.GROUND_NONAXIS
            checks[f"{mode}:electron_drift_same"] = mp.get_parameter(text, "FVKernels/n_e_drift", "type") == "PhysicsFVElectrostaticDrift"
            checks[f"{mode}:steps"] = int(meta["expected_steps"]) == base.axis.EXPECTED_STEPS
            checks[f"{mode}:fe_gauss_diffusivity"] = mp.get_parameter(text, "Postprocessors/r31_gauss_flux_reduced", "diffusivity") == "1"
            checks[f"{mode}:no_fv_gauss_functor"] = mp.get_parameter(text, "Postprocessors/r31_gauss_flux_reduced", "functor_diffusivity") is None
        failed = sorted(k for k, v in checks.items() if not v)
        return {"status": "PASS" if not failed else "FAIL", "checks": checks, "failed_checks": failed}
    finally:
        base.build_fe_case = current


base.build_fe_case = build_fe_case
base.build_e1_input = build_e1_input
base.build_w2_input = build_w2_input
base.fe_self_test = fe_self_test


if __name__ == "__main__":
    raise SystemExit(base.main())
