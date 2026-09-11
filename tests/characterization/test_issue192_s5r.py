from __future__ import annotations

from pathlib import Path

from physics_harness.adapters.moose import parameters as mp
from experiments.historical_recipe_support.issue192_s5r import (
    ADMITTED_CHANNELS,
    DEFERRED_TOKENS,
    H01_H04_ACTIVE,
    H05_ACTIVE,
    OWNER_BLOCKS,
    PROGRESS,
    RATE_TABLES,
    audit_s5r_input,
    build_s5r_input,
)

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "experiments/Issue91_real_qvt_r3/r3_e0/heavy_base.i"


def _build():
    return build_s5r_input(BASE.read_text())


def test_s5r_assembles_exact_frozen_ledger_on_r4_qf1() -> None:
    text, meta = _build()
    audit = audit_s5r_input(text)

    assert audit["status"] == "PASS"
    assert meta["audit"]["status"] == "PASS"
    assert tuple(meta["admitted_ledger"]) == ADMITTED_CHANNELS
    assert set(meta["owner_map"]) == set(ADMITTED_CHANNELS)
    assert set(meta["progress_map"]) == set(ADMITTED_CHANNELS)
    assert len(set(PROGRESS.values())) == len(ADMITTED_CHANNELS)
    assert meta["representative_runtime_claim"] is False


def test_s5r_preserves_solved_poisson_and_adds_solved_energy() -> None:
    text, _ = _build()

    assert mp.get_parameter(text, "FVKernels/n_e_drift", "potential") == "potential_plasma"
    assert (
        mp.get_parameter(text, "FVKernels/O2p_electrostatic_drift", "potential")
        == "potential_plasma"
    )
    assert mp.get_parameter(text, "Variables/n_epsilon", "type") == "MooseVariableFVReal"
    assert (
        mp.get_parameter(text, "FunctorMaterials/s5r_mean_energy", "type")
        == "PhysicsElectronMeanEnergyMaterial"
    )
    assert (
        mp.get_parameter(text, "FunctorMaterials/electron_transport", "type")
        == "PhysicsElectronTransportLookupMaterial"
    )
    assert (
        mp.get_parameter(text, "FunctorMaterials/electron_transport", "mean_energy")
        == "mean_en_solved"
    )
    assert (
        mp.get_parameter(text, "FunctorMaterials/electron_transport", "bounds_policy")
        == "error"
    )


def test_s5r_has_exact_canonical_progress_owner_surface() -> None:
    text, _ = _build()
    audit = audit_s5r_input(text)

    assert audit["checks"]["exact_kinetic_owner_block_set"] is True
    assert set(OWNER_BLOCKS) == set(ADMITTED_CHANNELS)
    for channel in ("EI01", "EI02", "EI17", "EI19", "EI18_O_TO_OS", "EI20_O_IONIZATION"):
        path = OWNER_BLOCKS[channel]
        assert mp.get_parameter(text, path, "type") == "PhysicsElectronImpactRateMaterial"
        assert mp.get_parameter(text, path, "rate_table_file") == RATE_TABLES[channel]
        assert mp.get_parameter(text, path, "reaction_progress") == PROGRESS[channel]

    assert (
        mp.get_parameter(text, OWNER_BLOCKS["EI10"], "type")
        == "PhysicsElectronImpactO2sExcitationMaterial"
    )
    assert (
        mp.get_parameter(text, OWNER_BLOCKS["EI16"], "type")
        == "PhysicsElectronImpactIonizationMaterial"
    )
    assert (
        mp.get_parameter(text, OWNER_BLOCKS["EDETACH_OM"], "property_name")
        == PROGRESS["EDETACH_OM"]
    )


def test_s5r_common_temperature_and_heavy_reaction_sets_are_exact() -> None:
    text, _ = _build()

    assert (
        mp.get_parameter(text, "FunctorMaterials/s5r_h01_h04_rates", "temperature")
        == "T_g"
    )
    assert (
        mp.words(
            mp.get_parameter(
                text, "FunctorMaterials/s5r_h01_h04_rates", "active_reactions"
            )
        )
        == list(H01_H04_ACTIVE)
    )
    assert mp.get_parameter(text, "FunctorMaterials/s5r_h05_rate", "temperature") == "T_g"
    assert (
        mp.words(
            mp.get_parameter(text, "FunctorMaterials/s5r_h05_rate", "active_reactions")
        )
        == [H05_ACTIVE]
    )
    for suffix in ("ei02", "ei17"):
        assert "T_g" in mp.words(
            mp.get_parameter(
                text,
                f"FunctorMaterials/s5r_{suffix}_elastic_energy",
                "functor_names",
            )
        )


def test_s5r_reuses_standard_projection_and_excludes_deferred_channels() -> None:
    text, _ = _build()

    assert "PhysicsFVElectronReactionEnergySource" not in text
    assert "bounds_policy = clamp" not in text
    assert "bounds_policy = floor" not in text
    assert "gas_temperature = T_gas" not in text
    assert "temperature = T_gas" not in text
    for token in DEFERRED_TOKENS:
        assert token not in text

    assert (
        mp.get_parameter(text, "FunctorMaterials/s5r_ei10_projection", "type")
        == "PhysicsO2sExcitationSourceMaterial"
    )
    assert (
        mp.get_parameter(text, "FunctorMaterials/s5r_ei16_projection", "type")
        == "PhysicsO2IonizationSourceMaterial"
    )
    assert (
        mp.get_parameter(text, "FVKernels/s5r_electron_source", "type")
        == "PhysicsFVElectronReactionSource"
    )
    for channel in (
        "EI10",
        "EI16",
        "EI19",
        "EI18_O_TO_OS",
        "EI20_O_IONIZATION",
        "EDETACH_OM",
    ):
        assert (
            mp.get_parameter(
                text, f"FVKernels/s5r_energy_{channel.lower()}", "type"
            )
            == "FVCoupledForce"
        )


def test_s5r_negative_mutations_fail_static_audit() -> None:
    text, _ = _build()
    mutations = (
        ("reaction_progress = R_attachment", "reaction_progress = R_attachment_BAD"),
        ("bounds_policy = error", "bounds_policy = clamp"),
        (
            "temperature = T_g\n    species = 'O2 O2p O Om Op'",
            "temperature = 600\n    species = 'O2 O2p O Om Op'",
        ),
    )
    for old, new in mutations:
        assert old in text
        assert audit_s5r_input(text.replace(old, new, 1))["status"] == "FAIL"
