"""Issue #282: separate scientific meaning from historical 2-D E2a syntax.

Characterization-only; no SOL acceptance, no 2-D numerical oracle, and no
assumption that the initial Gaussian obeys homogeneous Neumann derivatives.
The historical E2a build has a coupled predecessor; this suite verifies its
*constructed input* rather than hiding the observed E1/E2a P3 segfault.
"""
from __future__ import annotations

import math
from pathlib import Path

import pytest

from experiments.historical_recipe_support.issue26_e1 import (
    ELEMENTARY_CHARGE_C,
    ENERGY_DENSITY_J_FUNCTOR,
    ENERGY_INVENTORY_PP,
    ENERGY_REFERENCE_EV,
    ENERGY_VARIABLE,
)
from experiments.historical_recipe_support.issue26_e2a import (
    E2A_DIFFUSION_KERNEL,
    E2A_DIFFUSIVITY_M2_S,
    E2A_INITIAL_EXPRESSION,
    build_issue26_e2a_input,
)
from physics_harness.adapters.moose import blocks as mb
from physics_harness.adapters.moose import parameters as mp

BASE = (
    Path(__file__).resolve().parents[2]
    / "experiments/Issue91_real_qvt_r3/r3_e0/heavy_base.i"
)


def _input(diffusivity: float):
    return build_issue26_e2a_input(
        BASE.read_text(encoding="utf-8"), diffusivity_m2_s=diffusivity
    )


def _unquote(value: str | None) -> str:
    assert value is not None
    return value.strip().strip("'\"")


@pytest.mark.parametrize("diffusivity", [0.0, E2A_DIFFUSIVITY_M2_S])
def test_two_arms_preserve_same_physical_operator_and_one_step(diffusivity: float) -> None:
    text, info = _input(diffusivity)
    assert info["audit"]["status"] == "PASS"
    assert mb.has_block(text, f"FVKernels/{E2A_DIFFUSION_KERNEL}")
    assert mp.get_parameter(text, f"FVKernels/{E2A_DIFFUSION_KERNEL}", "type") == "FVDiffusion"
    assert mp.get_parameter(text, f"FVKernels/{E2A_DIFFUSION_KERNEL}", "variable") == ENERGY_VARIABLE
    assert mp.get_parameter(text, f"FVKernels/{E2A_DIFFUSION_KERNEL}", "coeff") == "electron_energy_diffusivity_control"
    assert mp.get_parameter(text, "FVKernels/n_epsilon_time", "type") == "FVTimeKernel"
    assert mp.get_parameter(text, "FVKernels/n_epsilon_time", "variable") == ENERGY_VARIABLE
    assert float(mp.words(mp.get_parameter(text, "FunctorMaterials/e2a_energy_diffusivity", "prop_values"))[0]) == diffusivity
    assert mp.get_parameter(text, "FunctorMaterials/e2a_energy_diffusivity", "block") == "plasma"
    assert mp.get_parameter(text, f"FVKernels/{E2A_DIFFUSION_KERNEL}", "block") == "plasma"
    assert float(mp.get_parameter(text, "Executioner", "dt")) == 1e-8
    assert float(mp.get_parameter(text, "Executioner", "end_time")) == 1e-8
    assert not mb.has_block(text, "FVKernels/n_epsilon_drift")
    assert not mb.has_block(text, "FVKernels/n_epsilon_joule")
    assert info["joule_source_enabled"] is False
    assert info["wall_energy_flux_enabled"] is False
    assert info["volumetric_reaction_energy_sources_enabled"] is False
    assert info["transport_lookup_coupled_to_solved_energy"] is False


@pytest.mark.parametrize("diffusivity", [0.0, E2A_DIFFUSIVITY_M2_S])
def test_energy_density_unit_bridge_matches_derived_mean_energy_eV(diffusivity: float) -> None:
    text, info = _input(diffusivity)
    n_ref = float(info["predecessor"]["electron_reference_density_m3"])
    e_ref = float(info["energy_reference_eV"])
    assert n_ref > 0 and e_ref == ENERGY_REFERENCE_EV
    assert info["electron_energy_unknown"] == "n_epsilon == n_epsilon_hat"

    energy = f"FunctorMaterials/{ENERGY_DENSITY_J_FUNCTOR}"
    assert mp.words(mp.get_parameter(text, energy, "functor_names")) == [ENERGY_VARIABLE]
    assert mp.words(mp.get_parameter(text, energy, "functor_symbols")) == ["eps_hat"]
    observed = _unquote(mp.get_parameter(text, energy, "expression"))
    assert observed.endswith("*eps_hat")
    scale_j_m3 = float(observed.removesuffix("*eps_hat"))
    reference_j_m3 = n_ref * e_ref * ELEMENTARY_CHARGE_C
    assert math.isclose(scale_j_m3, reference_j_m3, rel_tol=2e-15)

    mean = "FunctorMaterials/mean_en_solved"
    assert mp.words(mp.get_parameter(text, mean, "functor_names")) == ["n_epsilon", "n_e"]
    assert mp.words(mp.get_parameter(text, mean, "functor_symbols")) == ["eps_hat", "ne_hat"]
    assert _unquote(mp.get_parameter(text, mean, "expression")) == f"{e_ref:.17g}*eps_hat/ne_hat"

    assert mp.get_parameter(text, f"Postprocessors/{ENERGY_INVENTORY_PP}", "functor") == ENERGY_DENSITY_J_FUNCTOR
    assert mp.get_parameter(text, f"Postprocessors/{ENERGY_INVENTORY_PP}", "block") == "plasma"
    for eps_hat, ne_hat in ((1.0, 1.0), (0.6, 1.2), (1.5, 0.8)):
        mean_ev = e_ref * eps_hat / ne_hat
        w_j_m3 = reference_j_m3 * eps_hat
        recovered_mean_ev = w_j_m3 / (n_ref * ne_hat * ELEMENTARY_CHARGE_C)
        assert math.isclose(mean_ev, recovered_mean_ev, rel_tol=1e-15)


def test_both_arms_share_identical_historical_structure_excluding_D() -> None:
    control, meta0 = _input(0.0)
    treatment, meta100 = _input(100.0)
    assert meta0["audit"]["status"] == meta100["audit"]["status"] == "PASS"
    prop = "FunctorMaterials/e2a_energy_diffusivity"
    assert mp.words(mp.get_parameter(control, prop, "prop_values")) == ["0"]
    assert mp.words(mp.get_parameter(treatment, prop, "prop_values")) == ["100"]
    # This is a builder-level negative control, not a runtime field parity claim.
    canonical = mp.upsert_parameter(control, prop, "prop_values", "'100'")
    assert canonical == treatment


def test_gaussian_initial_profile_is_not_a_closed_domain_analytic_final_oracle() -> None:
    assert E2A_INITIAL_EXPRESSION == "1.0 + 0.5*exp(-800.0*(x-0.12)^2 - 80.0*(y-0.22)^2)"
    def value(x: float, y: float) -> float:
        return 1 + 0.5 * math.exp(-800 * (x - 0.12)**2 - 80 * (y - 0.22)**2)
    def dx(x: float, y: float) -> float:
        return -1600 * (x - 0.12) * (value(x, y) - 1)
    def dy(x: float, y: float) -> float:
        return -160 * (y - 0.22) * (value(x, y) - 1)
    # The initial profile has a nonzero normal derivative at generic finite
    # boundaries. This prevents claiming the free-space diffused Gaussian as
    # the *exact* final solution for the closed irregular RZ mesh.
    assert abs(dx(0.1, 0.2)) > 0
    assert abs(dy(0.1, 0.2)) > 0


def test_physical_bridge_rejects_zero_electron_density_in_interpretation() -> None:
    n_ref = 1.0e15
    eps_hat = 1.0
    ne_hat = 0.0
    w_j_m3 = n_ref * ENERGY_REFERENCE_EV * ELEMENTARY_CHARGE_C * eps_hat
    assert w_j_m3 > 0
    with pytest.raises(ZeroDivisionError):
        _ = ENERGY_REFERENCE_EV * eps_hat / ne_hat
    # Historical expression contains no guard; a production canonical
    # contract needs an explicit positive-density domain or defined policy.
