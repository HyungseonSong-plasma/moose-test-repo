"""Physics #282: actual historical 2-D RZ E2a staging/normalization audit.

Tests below are an offline contract check, NOT a live 2-D backend V&V verdict.
"""
from __future__ import annotations

import math
from pathlib import Path

import pytest

from experiments.Issue282_e2a_rz_bridge.run_native import (
    CASE_DIFFUSIVITIES,
    ENERGY_REFERENCE_EV,
    ELEMENTARY_CHARGE_C,
    RELATIVE_TOLERANCE,
    analytic_initial,
    independent_scalar_checks,
    physical_energy_density_j_m3,
    r_z_cell_volume_m3,
)
from experiments.historical_recipe_support.issue26_e2a import (
    E2A_INITIAL_EXPRESSION,
    build_issue26_e2a_input,
)
from physics_harness.adapters.moose import blocks as mb
from physics_harness.adapters.moose import parameters as mp

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "experiments/Issue91_real_qvt_r3/r3_e0/heavy_base.i"


def test_real_historical_mesh_and_initial_condition_are_RZ_gaussian() -> None:
    source = BASE.read_text(encoding="utf-8")
    assert mp.get_parameter(source, "Mesh", "coord_type") == "RZ"
    assert mp.get_parameter(source, "Mesh", "rz_coord_axis") == "Y"
    assert "qvt.msh" in source
    assert CASE_DIFFUSIVITIES == {"zero_diffusion": 0.0, "diffusion": 100.0}
    assert "800.0*(x-0.12)^2" in E2A_INITIAL_EXPRESSION
    assert "80.0*(y-0.22)^2" in E2A_INITIAL_EXPRESSION
    assert analytic_initial(0.12, 0.22) == pytest.approx(1.5)
    assert analytic_initial(0, 0) > 1.0
    assert RELATIVE_TOLERANCE == 1.0e-4


def test_actual_two_arms_share_operator_and_energy_normalization() -> None:
    original = BASE.read_text(encoding="utf-8")
    for D in CASE_DIFFUSIVITIES.values():
        text, meta = build_issue26_e2a_input(original, diffusivity_m2_s=D)
        assert meta["audit"]["status"] == "PASS"
        assert meta["natural_zero_energy_flux_boundaries"] is True
        assert meta["transport_lookup_coupled_to_solved_energy"] is False
        assert meta["energy_drift_enabled"] is False
        assert meta["joule_source_enabled"] is False
        assert meta["wall_energy_flux_enabled"] is False
        assert mb.has_block(text, "FVKernels/n_epsilon_time")
        assert mb.has_block(text, "FVKernels/n_epsilon_diffusion")
        assert mp.get_parameter(
            text, "FVKernels/n_epsilon_diffusion", "variable"
        ) == "n_epsilon"
        assert mp.get_parameter(
            text, "FVKernels/n_epsilon_diffusion", "coeff"
        ) == "electron_energy_diffusivity_control"
        assert mp.words(mp.get_parameter(
            text, "FunctorMaterials/e2a_energy_diffusivity", "prop_values"
        )) == [str(int(D))]
        assert "eps_hat/ne_hat" in mp.get_parameter(
            text, "FunctorMaterials/mean_en_solved", "expression"
        )
        expression = mp.get_parameter(
            text, "FunctorMaterials/electron_energy_density_J_m3", "expression"
        )
        scale = float(mp.words(expression)[0].split("*")[0])
        expected = (
            meta["predecessor"]["electron_reference_density_m3"]
            * ENERGY_REFERENCE_EV * ELEMENTARY_CHARGE_C
        )
        assert math.isclose(scale, expected, rel_tol=1e-14)
        assert math.isclose(
            physical_energy_density_j_m3(1.0, meta["predecessor"]["electron_reference_density_m3"]),
            expected, rel_tol=1e-14
        )


def test_RZ_radial_y_revolution_volume_uses_2pi_r_weight() -> None:
    rectangle = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    volume, cx, radius = r_z_cell_volume_m3(rectangle)
    assert volume == pytest.approx(math.pi)
    assert (cx, radius) == pytest.approx((0.5, 0.5))
    triangle = [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]
    volume_tri, _, radius_tri = r_z_cell_volume_m3(triangle)
    assert volume_tri == pytest.approx(math.pi / 3.0)
    assert radius_tri == pytest.approx(1.0 / 3.0)
    with pytest.raises(ValueError, match="degenerate"):
        r_z_cell_volume_m3([(0, 0), (1, 0), (2, 0)])


def _measured_case(initial_j: float, final_j: float, old_range: float, new_range: float) -> dict:
    return {
        "state_status": "MEASURED",
        "state": {
            "initial": {
                "electron_energy_inventory_J": initial_j,
                "n_epsilon_min": 1.0,
                "n_epsilon_max": 1.0 + old_range,
            },
            "final": {
                "electron_energy_inventory_J": final_j,
                "n_epsilon_min": 1.0,
                "n_epsilon_max": 1.0 + new_range,
            },
        },
    }


def test_independent_scalar_check_rejects_no_smoothing_and_nonconservation() -> None:
    good = {
        "zero_diffusion": _measured_case(1, 1, 0.5, 0.5),
        "diffusion": _measured_case(1, 1, 0.5, 0.4),
    }
    assert independent_scalar_checks(good)["candidate_scalar_gates_met"] is True
    bad_diffusion = dict(good)
    bad_diffusion["diffusion"] = _measured_case(1, 1, 0.5, 0.5)
    assert independent_scalar_checks(bad_diffusion)["candidate_scalar_gates_met"] is False
    bad_energy = dict(good)
    bad_energy["diffusion"] = _measured_case(1, 1.001, 0.5, 0.4)
    assert independent_scalar_checks(bad_energy)["candidate_scalar_gates_met"] is False
    assert independent_scalar_checks({})["status"] == "INCONCLUSIVE_DATA_MISSING"

def test_research_type_projection_is_exact_reversible_and_source_registered() -> None:
    """Registration-name bridge is an *audit*, never a science-equivalence verdict."""
    import re

    from experiments.Issue282_e2a_rz_bridge.research_type_bridge import (
        HISTORICAL_TO_CURRENT_TYPE,
        TYPE_LINE,
        project_historical_registration_only,
    )

    original, _ = build_issue26_e2a_input(
        BASE.read_text(encoding="utf-8"), diffusivity_m2_s=100.0,
    )
    projected, report = project_historical_registration_only(original)
    assert projected != original
    assert report["status"] == "TYPE_TOKENS_ONLY_RESEARCH_PROJECTION"
    assert report["not_physics_semantics_parity"] is True
    assert len(HISTORICAL_TO_CURRENT_TYPE) == 7
    assert all(row["instances"] > 0 for row in report["mappings"].values())

    for historical, current in HISTORICAL_TO_CURRENT_TYPE.items():
        assert historical in original
        assert current in projected
        dirname = "materials" if "Material" in current and "FV" not in current else "fvkernels"
        # Historical type-only projection is byte-pinned and cannot be
        # rewritten to the new factory API without breaking source evidence.
        # The old electron lookup token remains IN THE ARCHIVED PROJECTION,
        # but is deliberately not registered by the current PhysicsApp.
        retired_lookup = current == "PhysicsElectronTransportLookupMaterial"
        canonical = "DDTransportMaterial" if retired_lookup else current
        candidate = ROOT / "physics_app" / "src" / dirname / f"{canonical}.C"
        assert candidate.is_file(), f"missing current PhysicsApp source: {candidate}"
        source = candidate.read_text(encoding="utf-8")
        assert re.search(
            rf'register(?:AD)?MooseObject\(\s*"PhysicsApp"\s*,\s*{re.escape(canonical)}\s*\)\s*;',
            source,
        )
        if retired_lookup:
            assert (
                'registerMooseObjectAliased("PhysicsApp", DDTransportMaterial, '
                '"PhysicsElectronTransportLookupMaterial");'
            ) not in source
            # The frozen research-only projection is *not* runnable under
            # the retired input API; migrate parameters in a new study.

    assert all(
        not m.group("name").startswith("QPX")
        for m in TYPE_LINE.finditer(projected)
    )
    with pytest.raises(ValueError, match="unknown"):
        project_historical_registration_only(
            original + "\n[Materials]\n  [unsupported]\n    type = QPXUnknown\n  []\n[]\n"
        )
