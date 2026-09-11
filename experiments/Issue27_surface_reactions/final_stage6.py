"""Final Stage-6 wall + SEE + energy + chemistry integration composition for #27.

This module composes only previously accepted component contracts.  It does not
claim Stage-6 acceptance by construction: acceptance still requires an exact-head
ordinary CI pass plus governed real-physics runtime evidence on the assembled
production path.
"""
from __future__ import annotations

from typing import Any

from experiments.Issue27_surface_reactions.controlled_wall.electron_wall import (
    THERMAL_BC,
    THERMAL_MATERIAL,
)
from experiments.Issue27_surface_reactions.controlled_wall.see import (
    SEE_BC,
    _build_a8_case_input,
)
from experiments.historical_recipe_support import issue192_s5r as s5r
from experiments.historical_recipe_support.issue26_energy_chain import (
    A8_WALL_PARAMETERS,
    ENERGY_WALL_THERMAL_BC,
    SEE_ENERGY_BC,
    _insert_energy_wall_terms,
)
from experiments.Issue27_surface_reactions.controlled_wall.electron_wall_stable import (
    A7_DISCRIMINATOR_DT_S,
)
from physics_harness.adapters.moose import blocks as mb
from physics_harness.adapters.moose import parameters as mp


class Issue27Stage6FinalError(RuntimeError):
    pass


def _retarget_thermal_particle_flux_to_solved_energy(text: str) -> str:
    """Use the solved electron mean energy for the accepted thermal particle loss."""
    if not mb.has_block(text, f"FunctorMaterials/{THERMAL_MATERIAL}"):
        raise Issue27Stage6FinalError("missing accepted A7 thermal-electron material")
    return mp.upsert_parameter(
        text,
        f"FunctorMaterials/{THERMAL_MATERIAL}",
        "functor_names",
        "'n_e mean_en_solved'",
    )


def audit_stage6_final_input(text: str) -> dict[str, Any]:
    checks: dict[str, bool] = {}

    # The complete admitted Stage-5 ledger and solved-energy transport remain intact.
    s5_audit = s5r.audit_s5r_input(text)
    checks["stage5_ledger_and_solved_energy"] = s5_audit["status"] == "PASS"

    wall_list = [
        "plasma_electrode",
        "plasma_metal",
        "plasma_right",
        "plasma_cover",
        "plasma_wafer",
        "plasma_focus_ring",
    ]
    expected_walls = set(wall_list)
    for name in (THERMAL_BC, SEE_BC, ENERGY_WALL_THERMAL_BC, SEE_ENERGY_BC):
        path = f"FVBCs/{name}"
        checks[f"wall_bc_present:{name}"] = mb.has_block(text, path)
        boundaries = set(mp.words(mp.get_parameter(text, path, "boundary") or ""))
        checks[f"wall_scope_exact:{name}"] = boundaries == expected_walls
        checks[f"inlet_outlet_excluded:{name}"] = not ({"inlet", "outlet"} & boundaries)

    checks["thermal_particle_uses_solved_energy"] = (
        mp.words(
            mp.get_parameter(
                text, f"FunctorMaterials/{THERMAL_MATERIAL}", "functor_names"
            )
            or ""
        )
        == ["n_e", "mean_en_solved"]
    )
    checks["thermal_particle_loss_enabled"] = (
        float(mp.get_parameter(text, f"FVBCs/{THERMAL_BC}", "factor") or "nan") == -1.0
    )
    checks["see_particle_source_enabled"] = (
        float(mp.get_parameter(text, f"FVBCs/{SEE_BC}", "factor") or "nan") == 1.0
    )
    checks["thermal_energy_loss_enabled"] = (
        float(
            mp.get_parameter(text, f"FVBCs/{ENERGY_WALL_THERMAL_BC}", "factor")
            or "nan"
        )
        == -1.0
    )
    checks["see_energy_source_enabled"] = (
        float(mp.get_parameter(text, f"FVBCs/{SEE_ENERGY_BC}", "factor") or "nan") == 1.0
    )

    checks["finite_see_coefficients_frozen"] = all(
        token in text
        for token in (
            "issue27_a8_see_normalized_flux_inward",
            "0.05",
        )
    )
    checks["solved_energy_wall_mapping_present"] = all(
        token in text
        for token in (
            "issue26_energy_wall_thermal_flux_outward",
            "issue26_see_energy_normalized_flux_inward",
        )
    )
    checks["no_legacy_qpx_object_types"] = "type = QPX" not in text

    failed = sorted(name for name, passed in checks.items() if not passed)
    return {
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "failed_checks": failed,
        "stage5_audit": s5_audit,
    }


def build_stage6_final_input(base_text: str) -> tuple[str, dict[str, Any]]:
    """Compose the narrow representative final Stage-6 production surface."""
    # Start from the accepted A8 conducting-wall particle path so wall chemistry,
    # charged-heavy surface+migration transport, thermal electron loss and finite
    # O2+/O+ SEE retain their accepted ownership and signs.
    text, a8_meta = _build_a8_case_input(
        base_text,
        parameters=A8_WALL_PARAMETERS,
        mode="see_on",
    )

    # Promote inherited live runtime objects to the current Physics registrations.
    text = s5r._promote_current_physics_object_types(text)

    # Promote the same electron equation to the accepted solved-energy + Stage-5
    # chemistry surface.  These helpers are exactly the accepted S5-R owners.
    n_ref = s5r._top_level_float(text, "n_e_value")
    text = s5r._insert_energy_state(text)
    text = _retarget_thermal_particle_flux_to_solved_energy(text)
    text = s5r._insert_concentrations(text)
    text = s5r._insert_kinetic_owners(text)
    text = s5r._insert_species_sources(text)
    text = s5r._insert_electron_source(text, n_ref=n_ref)
    text = s5r._insert_energy_sources(text, n_ref=n_ref)
    text = s5r._insert_observables(text)

    # Consume the accepted #26 E4/E5 wall-energy mapping without redefining gamma
    # or the 4 eV emitted-electron energy.
    text = _insert_energy_wall_terms(
        text,
        n_ref=n_ref,
        thermal_energy_on=True,
        see_energy_on=True,
        secondary_energy_ev=4.0,
    )

    # Keep the first final-integration discriminator deliberately bounded.  A
    # longer horizon may only be introduced after this exact composition passes
    # construction and governed one-step runtime gates.
    text = mp.upsert_parameter(text, "Executioner", "dt", f"{A7_DISCRIMINATOR_DT_S:.17g}")
    text = mp.upsert_parameter(
        text, "Executioner", "end_time", f"{A7_DISCRIMINATOR_DT_S:.17g}"
    )

    audit = audit_stage6_final_input(text)
    if audit["status"] != "PASS":
        raise Issue27Stage6FinalError(
            f"Stage-6 final composition audit failed: {audit['failed_checks']}"
        )

    return text, {
        "issue": 27,
        "stage": "STAGE_6_FINAL_WALL_SEE_ENERGY_CHEMISTRY",
        "claim": "construction_only_until_governed_runtime_passes",
        "a8_construction": a8_meta,
        "electron_reference_density_m3": n_ref,
        "stage5_admitted_ledger": list(s5r.ADMITTED_CHANNELS),
        "wall_boundaries": [
            "plasma_electrode",
            "plasma_metal",
            "plasma_right",
            "plasma_cover",
            "plasma_wafer",
            "plasma_focus_ring",
        ],
        "excluded_boundaries": ["inlet", "outlet"],
        "thermal_particle_mean_energy": "mean_en_solved",
        "see_coefficients": {"O2p": 0.05, "Op": 0.05, "Om": 0.0},
        "secondary_electron_mean_energy_eV": 4.0,
        "timestep_s": A7_DISCRIMINATOR_DT_S,
        "audit": audit,
    }


__all__ = [
    "Issue27Stage6FinalError",
    "audit_stage6_final_input",
    "build_stage6_final_input",
]
