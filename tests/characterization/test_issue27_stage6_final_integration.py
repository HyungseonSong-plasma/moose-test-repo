from __future__ import annotations

from experiments.Issue193_a8_see_acceptance import run as issue193
from experiments.Issue27_surface_reactions import final_stage6
from experiments.historical_recipe_support import issue192_s5r as s5r
from experiments.Issue27_surface_reactions.controlled_wall.electron_wall import (
    THERMAL_BC,
    THERMAL_MATERIAL,
)
from experiments.Issue27_surface_reactions.controlled_wall.see import SEE_BC
from experiments.historical_recipe_support.issue26_energy_chain import (
    ENERGY_WALL_THERMAL_BC,
    SEE_ENERGY_BC,
)
from physics_harness.adapters.moose import parameters as mp


def _base_text() -> str:
    return (issue193.SOURCE / "heavy_base.i").read_text(encoding="utf-8")


def test_stage6_final_composition_preserves_accepted_contracts() -> None:
    text, meta = final_stage6.build_stage6_final_input(_base_text())
    audit = final_stage6.audit_stage6_final_input(text)

    assert audit["status"] == "PASS"
    assert audit["stage5_audit"]["status"] == "PASS"
    assert meta["stage"] == "STAGE_6_FINAL_WALL_SEE_ENERGY_CHEMISTRY"
    assert meta["claim"] == "construction_only_until_governed_runtime_passes"
    assert meta["stage5_admitted_ledger"] == list(s5r.ADMITTED_CHANNELS)
    assert meta["wall_boundaries"] == [
        "plasma_electrode",
        "plasma_metal",
        "plasma_right",
        "plasma_cover",
        "plasma_wafer",
        "plasma_focus_ring",
    ]
    assert meta["excluded_boundaries"] == ["inlet", "outlet"]
    assert meta["thermal_particle_mean_energy"] == "mean_en_solved"
    assert meta["see_coefficients"] == {"O2p": 0.05, "Op": 0.05, "Om": 0.0}
    assert meta["secondary_electron_mean_energy_eV"] == 4.0
    assert meta["timestep_s"] == 1.0e-10

    for check in (
        "stage5_ledger_and_solved_energy",
        "thermal_particle_uses_solved_energy",
        "thermal_particle_loss_enabled",
        "see_particle_source_enabled",
        "thermal_energy_loss_enabled",
        "see_energy_source_enabled",
        "finite_see_coefficients_frozen",
        "solved_energy_wall_mapping_present",
        "no_legacy_qpx_object_types",
    ):
        assert audit["checks"][check] is True

    for name in (THERMAL_BC, SEE_BC, ENERGY_WALL_THERMAL_BC, SEE_ENERGY_BC):
        assert audit["checks"][f"wall_bc_present:{name}"] is True
        assert audit["checks"][f"wall_scope_exact:{name}"] is True
        assert audit["checks"][f"inlet_outlet_excluded:{name}"] is True

    assert mp.words(
        mp.get_parameter(
            text,
            f"FunctorMaterials/{THERMAL_MATERIAL}",
            "functor_names",
        )
        or ""
    ) == ["n_e", "mean_en_solved"]


def test_stage6_final_audit_rejects_particle_energy_contract_breaks() -> None:
    text, _ = final_stage6.build_stage6_final_input(_base_text())

    broken_particle = mp.upsert_parameter(
        text,
        f"FVBCs/{SEE_BC}",
        "factor",
        "0",
    )
    particle_audit = final_stage6.audit_stage6_final_input(broken_particle)
    assert particle_audit["status"] == "FAIL"
    assert particle_audit["checks"]["see_particle_source_enabled"] is False

    broken_energy = mp.upsert_parameter(
        text,
        f"FVBCs/{SEE_ENERGY_BC}",
        "factor",
        "0",
    )
    energy_audit = final_stage6.audit_stage6_final_input(broken_energy)
    assert energy_audit["status"] == "FAIL"
    assert energy_audit["checks"]["see_energy_source_enabled"] is False

    broken_mean_energy = mp.upsert_parameter(
        text,
        f"FunctorMaterials/{THERMAL_MATERIAL}",
        "functor_names",
        "'n_e mean_en'",
    )
    mean_energy_audit = final_stage6.audit_stage6_final_input(broken_mean_energy)
    assert mean_energy_audit["status"] == "FAIL"
    assert mean_energy_audit["checks"]["thermal_particle_uses_solved_energy"] is False
