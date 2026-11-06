"""QPX-free characterizations of the pending Issue282 real native run recipe.

These tests verify the *planned benchmark configuration*, not MOOSE runtime or
scientific acceptance. Real evidence must come from the one-shot Actions job.
"""
from __future__ import annotations

import math

from experiments.Issue282_diffusion_1d_oracle.run_native import (
    AMPLITUDE,
    DIFFUSIVITIES,
    END_S,
    LENGTH_M,
    MESHES,
    RELATIVE_TARGET,
    STEPS,
    cosine_cell_average,
    render_input,
)


def test_bounded_matrix_and_candidate_tolerance() -> None:
    assert len(DIFFUSIVITIES) * len(MESHES) * len(STEPS) == 18
    assert DIFFUSIVITIES == (0.0, 100.0)
    assert RELATIVE_TARGET == 1.0e-4


def test_both_d0_and_d100_keep_the_same_fv_operator_graph() -> None:
    control = render_input(nx=64, steps=10, diffusivity=0.0)
    treatment = render_input(nx=64, steps=10, diffusivity=100.0)
    for text in (control, treatment):
        assert "type = MooseVariableFVReal" in text
        assert "type = FVTimeKernel" in text
        assert "type = FVDiffusion" in text
        assert "coeff = controlled_energy_diffusivity" in text
        assert "type = FunctionIC" in text
        assert "exodus = true" in text
        assert "csv = true" in text
        assert "type = ADElementIntegralFunctorPostprocessor" in text
        assert "drift" not in text.lower()
    assert "prop_values = '0'" in control
    assert "prop_values = '100'" in treatment


def test_analytic_cell_average_has_zero_flux_and_conserves_integral() -> None:
    nx = 256
    for diffusivity in DIFFUSIVITIES:
        for t in (0.0, END_S):
            values = [
                cosine_cell_average(
                    LENGTH_M * j / nx, LENGTH_M * (j + 1) / nx,
                    diffusivity=diffusivity, t=t,
                )
                for j in range(nx)
            ]
            assert math.isclose(sum(values) / nx, 1.0, rel_tol=1e-13)
            assert all(1.0 - AMPLITUDE <= v <= 1.0 + AMPLITUDE for v in values)


def test_d0_cell_average_is_unchanged_while_positive_d_decays() -> None:
    lo = 0.0
    hi = LENGTH_M / 128
    initial = cosine_cell_average(lo, hi, diffusivity=0.0, t=0.0)
    assert cosine_cell_average(lo, hi, diffusivity=0.0, t=END_S) == initial
    assert cosine_cell_average(lo, hi, diffusivity=100.0, t=END_S) < initial
