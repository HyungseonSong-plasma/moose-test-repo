from __future__ import annotations

import copy
import math

from physics_harness.adapters.moose import blocks as mb
from physics_harness.adapters.moose import parameters as mp
from experiments.Issue192_s5r_representative import run as s5r_runtime
from experiments.historical_recipe_support.issue192_s5r import (
    ADMITTED_CHANNELS,
    DEFERRED_TOKENS,
    audit_s5r_input,
)


def test_s5r_runtime_surface_preserves_canonical_science_and_only_changes_dt() -> None:
    baseline, _ = s5r_runtime._runtime_input(s5r_runtime.BASELINE_DT_S)
    half, _ = s5r_runtime._runtime_input(s5r_runtime.HALF_DT_S)

    assert audit_s5r_input(baseline)["status"] == "PASS"
    assert audit_s5r_input(half)["status"] == "PASS"
    assert math.isclose(
        float(mp.get_parameter(baseline, "Executioner", "dt")),
        s5r_runtime.BASELINE_DT_S,
    )
    assert math.isclose(
        float(mp.get_parameter(half, "Executioner", "dt")),
        s5r_runtime.HALF_DT_S,
    )
    assert mp.get_parameter(
        baseline, "Postprocessors/r31_charge_integral", "execute_on"
    ) == "'INITIAL TIMESTEP_END'"
    for name in (
        "s5r_n_epsilon_inventory",
        "s5r_mean_en_avg",
        "s5r_ei02_elastic_energy_avg",
        "s5r_ei17_elastic_energy_avg",
    ):
        assert mb.has_block(baseline, f"Postprocessors/{name}")
    for token in DEFERRED_TOKENS:
        assert token not in baseline
        assert token not in half


def test_s5r_runtime_full_diagnostic_stoichiometry_matches_frozen_ledger() -> None:
    assert set(s5r_runtime.FULL_HEAVY_STOICH) == set(ADMITTED_CHANNELS)
    assert s5r_runtime.FULL_HEAVY_STOICH["EI10"] == {"O2": -1, "O2s": 1}
    assert s5r_runtime.FULL_HEAVY_STOICH["EI16"] == {"O2": -1, "O2p": 1}
    assert s5r_runtime.FULL_HEAVY_STOICH["H05_OM_O_DETACHMENT"] == {
        "Om": -1,
        "O": -1,
        "O2": 1,
    }


def test_s5r_runtime_synthetic_balances_and_negative_controls() -> None:
    rows = s5r_runtime._synthetic_rows(s5r_runtime.BASELINE_DT_S)
    coefficients = {channel: -1.0 for channel in s5r_runtime.ENERGY_CHANNELS}

    assert s5r_runtime._state_evidence(rows[1:])["hard_pass"] is True
    assert (
        s5r_runtime._discrete_balances(
            rows, energy_coefficients=coefficients
        )["hard_pass"]
        is True
    )

    negative = copy.deepcopy(rows)
    negative[-1]["w_Om_min"] = "-0.1"
    assert s5r_runtime._state_evidence(negative[1:])["hard_pass"] is False

    broken_species = copy.deepcopy(rows)
    broken_species[-1]["mass_O"] = "0.2"
    assert (
        s5r_runtime._discrete_balances(
            broken_species, energy_coefficients=coefficients
        )["hard_pass"]
        is False
    )

    broken_electron = copy.deepcopy(rows)
    broken_electron[-1]["n_e_inventory"] = "1.1e16"
    assert (
        s5r_runtime._discrete_balances(
            broken_electron, energy_coefficients=coefficients
        )["hard_pass"]
        is False
    )

    broken_energy = copy.deepcopy(rows)
    broken_energy[-1]["s5r_n_epsilon_inventory"] = "1.1"
    assert (
        s5r_runtime._discrete_balances(
            broken_energy, energy_coefficients=coefficients
        )["hard_pass"]
        is False
    )


def test_s5r_runtime_timestep_sensitivity_is_measurement_not_auto_acceptance() -> None:
    result = s5r_runtime._timestep_sensitivity(
        {"mass_total": 1.0, "n_e_inventory": 2.0},
        {"mass_total": 0.99, "n_e_inventory": 2.02},
    )
    assert result["status"] == "MEASURED_UNTHRESHOLDED"
    assert "scientific convergence threshold" in result["reason"]
