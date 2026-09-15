#!/usr/bin/env python3
"""Harness-corrected rerun wrappers for Issue #228 E1 and W2.

This file exists outside experiments/Issue228_p2_e1_w2_pg/ so correcting the
small harnesses does not retrigger the expensive coupled-FE matrix.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from experiments.Issue228_p2_e1_w2_pg import run as base


def corrected_e1_input(h_m: float) -> str:
    # FVFunctorNeumannBC is a boundary-flux provider.  Include the diffusion
    # flux kernel that owns FV boundary fluxes.  factor=-1 gives an outward
    # loss because FVFunctorNeumannBC returns -factor*functor in the residual.
    return f"""[Mesh]
  [gen]
    type = GeneratedMeshGenerator
    dim = 1
    xmin = 0
    xmax = {h_m:.17g}
    nx = 1
  []
[]

[Variables]
  [q]
    type = MooseVariableFVReal
    initial_condition = {base.E1_INITIAL:.17g}
  []
[]

[FVKernels]
  [time]
    type = FVTimeKernel
    variable = q
  []
  [diffusion_flux_owner]
    type = FVDiffusion
    variable = q
    coeff = 1
  []
[]

[FVBCs]
  [right_loss]
    type = FVFunctorNeumannBC
    variable = q
    boundary = right
    functor = {base.E1_FLUX:.17g}
    factor = -1
  []
[]

[Postprocessors]
  [q_avg]
    type = ElementAverageFunctorPostprocessor
    functor = q
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]

[Executioner]
  type = Transient
  scheme = implicit-euler
  solve_type = NEWTON
  dt = {base.E1_DT:.17g}
  end_time = {base.E1_DT:.17g}
  nl_abs_tol = 1e-13
  nl_rel_tol = 1e-12
[]

[Outputs]
  csv = true
[]
"""


def corrected_w2_input() -> str:
    # The governed source Exodus contains the complete reactor.  The nonlinear
    # variable and both kernels remain restricted to `plasma`; non-plasma
    # blocks are passive mesh context.  Disable only the global kernel-coverage
    # integrity check that otherwise demands a kernel on those passive blocks.
    text = base.build_w2_input()
    return """[Problem]
  kernel_coverage_check = false
[]

""" + text


def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("e1")
    e.add_argument("--h-m", type=float, required=True)
    e.add_argument("--physics-opt", type=Path, required=True)
    e.add_argument("--results-root", type=Path, required=True)
    w = sub.add_parser("w2")
    w.add_argument("--suppression-fraction", type=float, required=True)
    w.add_argument("--snapshot-root", type=Path, required=True)
    w.add_argument("--physics-opt", type=Path, required=True)
    w.add_argument("--results-root", type=Path, required=True)
    a = p.parse_args()
    if a.cmd == "e1":
        base.build_e1_input = corrected_e1_input
        return base.run_e1(a)
    base.build_w2_input = corrected_w2_input
    return base.run_w2(a)


if __name__ == "__main__":
    raise SystemExit(main())
