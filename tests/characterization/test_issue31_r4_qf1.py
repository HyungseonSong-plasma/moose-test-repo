from __future__ import annotations

import csv
import re
from pathlib import Path

from experiments.Issue31_r4_qf1_closed_feedback import run as qf1_run
from qpx_harness.moose import parameters as mp
from recipes.issue31_r4_qf1 import (
    ELECTROSTATIC_BOUNDARIES_TO_AVOID,
    EXPECTED_FEEDBACK_KERNELS,
    EXPECTED_DRIFT_KERNELS,
    EXPECTED_HEAVY_EM_CORRECTION_KERNELS,
    FEEDBACK_POTENTIAL,
    PURE_O2_FEED_SCCM,
    PURE_O2_MOLAR_MASS_KG_PER_MOL,
    SOLVED_NON_O2_INLET_SPECIES,
    UNIFORM_INITIAL_O_MASS_FRACTION,
    audit_r4_qf1_input,
    build_r4_qf1_input,
)

ROOT = Path(__file__).resolve().parents[2]
R3_E0 = ROOT / "experiments/Issue91_real_qvt_r3/r3_e0"


def _base() -> str:
    return (R3_E0 / "heavy_base.i").read_text()


def test_qf1_closes_exact_charged_particle_feedback_set() -> None:
    text, meta = build_r4_qf1_input(_base())
    audit = audit_r4_qf1_input(text)

    assert audit["status"] == "PASS"
    assert meta["electrostatic_feedback_enabled"] is True
    assert meta["surface_accumulated_charge_enabled"] is False
    assert meta["volumetric_reactions_enabled"] is False
    assert meta["secondary_emission_enabled"] is False
    assert meta["feedback_potential"] == FEEDBACK_POTENTIAL

    drift = []
    correction = []
    for path in mp.direct_children(text, "FVKernels"):
        typ = mp.get_parameter(text, path, "type")
        if typ == "QPXFVElectrostaticDrift":
            drift.append(path)
        elif typ == "QPXFVHeavyMassElectromigrationCorrection":
            correction.append(path)

    assert tuple(sorted(drift)) == tuple(sorted(EXPECTED_DRIFT_KERNELS))
    assert tuple(sorted(correction)) == tuple(
        sorted(EXPECTED_HEAVY_EM_CORRECTION_KERNELS)
    )
    assert len(EXPECTED_FEEDBACK_KERNELS) == 10

    for path in EXPECTED_FEEDBACK_KERNELS:
        assert mp.get_parameter(text, path, "potential") == FEEDBACK_POTENTIAL
        assert tuple(
            mp.words(mp.get_parameter(text, path, "boundaries_to_avoid"))
        ) == ELECTROSTATIC_BOUNDARIES_TO_AVOID


def test_qf1_removes_neutral_O_spatial_perturbation_for_qn_initial_state() -> None:
    text, meta = build_r4_qf1_input(_base())
    initial = meta["initial_plasma"]

    assert initial["neutral_O_spatial_perturbation"] is False
    assert (
        initial["w_O_initial_mass_fraction"]
        == UNIFORM_INITIAL_O_MASS_FRACTION
        == 0.10
    )
    assert initial["w_O_initial_condition"] == "uniform FunctionIC"
    assert "exp(" in initial["previous_w_O_expression"]
    assert mp.get_parameter(text, "Functions/ic_w_O_transient", "expression") == "'0.10'"


def test_qf1_uses_pure_o2_20_sccm_feed_without_replacing_initial_plasma() -> None:
    text, meta = build_r4_qf1_input(_base())
    inlet = meta["inlet"]

    assert inlet["feed"] == "pure O2"
    assert inlet["flow_sccm"] == PURE_O2_FEED_SCCM == 20.0
    assert inlet["molar_mass_kg_per_mol"] == PURE_O2_MOLAR_MASS_KG_PER_MOL == 0.032
    assert inlet["O2_feed_mass_fraction"] == 1.0
    assert inlet["non_O2_feed_mass_fractions"] == {
        species: 0.0 for species in SOLVED_NON_O2_INLET_SPECIES
    }
    assert inlet["initial_plasma_composition_is_feed_composition"] is False
    assert inlet["removed_unused_initial_aliases"] == ["Yin_O2", "Yin_O"]

    initial = inlet["initial_plasma_mass_fractions_preserved"]
    assert initial["O2"] == 0.7
    assert initial["O"] == 0.1
    assert initial["O2p"] == 0.01
    assert initial["Om"] == 0.01
    assert initial["Op"] == 0.01
    assert sum(initial.values()) == 1.0
    assert re.search(r"(?m)^\s*Yin_O2\s*=", text) is None
    assert re.search(r"(?m)^\s*Yin_O\s*=", text) is None


def test_qf1_preserves_qn_normalized_electron_reference() -> None:
    text, meta = build_r4_qf1_input(_base())
    predecessor = meta["predecessor"]
    reference = predecessor["quasi_neutral_reference"]["electron_reference_density_m3"]

    assert reference > 1.0e18
    assert mp.get_parameter(text, "Variables/n_e", "initial_condition") == "1.0"
    assert (
        mp.get_parameter(
            text,
            "FunctorMaterials/electron_density_physical",
            "expression",
        )
        == "'${n_e_value}*ne_hat'"
    )
    assert (
        mp.get_parameter(
            text,
            "FunctorMaterials/r31_charge_density",
            "electron_density",
        )
        == "n_e_physical"
    )
    assert audit_r4_qf1_input(
        text,
        expected_reference_m3=reference,
    )["status"] == "PASS"


def test_qf1_stage_executes_charge_integral_on_initial_and_timestep_end(tmp_path: Path) -> None:
    target = tmp_path / "QF1"
    staged = qf1_run._stage(target)
    text = (target / "input.i").read_text()

    assert mp.words(
        mp.get_parameter(text, "Postprocessors/r31_charge_integral", "execute_on")
    ) == ["INITIAL", "TIMESTEP_END"]
    observable = staged["construction"]["c2_initial_charge_observable"]
    assert observable["postprocessor"] == "r31_charge_integral"
    assert observable["execute_on"] == ["INITIAL", "TIMESTEP_END"]


def test_c2_implicit_euler_uses_actual_initial_charge_and_sign_convention(
    tmp_path: Path,
) -> None:
    path = tmp_path / "input_out.csv"
    # Start from a nonzero actual initial charge. One O2+ particle leaves during
    # the step, so Delta_Q=-e and Q_boundary=+e despite the nonzero offset.
    mdot_one_particle = 0.032 / 6.02214076e23
    elementary_charge = 1.602176634e-19
    q_initial = -2.5e-5
    fieldnames = (
        "time",
        "r31_charge_integral",
        "domain_volume",
        "inlet_mdot_O2p",
        "outlet_mdot_O2p",
        "inlet_mdot_Om",
        "outlet_mdot_Om",
        "inlet_mdot_Op",
        "outlet_mdot_Op",
    )
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(
            {
                "time": "0",
                "r31_charge_integral": f"{q_initial:.17g}",
                "domain_volume": "1",
                "inlet_mdot_O2p": "0",
                "outlet_mdot_O2p": "0",
                "inlet_mdot_Om": "0",
                "outlet_mdot_Om": "0",
                "inlet_mdot_Op": "0",
                "outlet_mdot_Op": "0",
            }
        )
        writer.writerow(
            {
                "time": "1",
                "r31_charge_integral": f"{q_initial-elementary_charge:.17g}",
                "domain_volume": "1",
                "inlet_mdot_O2p": "0",
                "outlet_mdot_O2p": f"{mdot_one_particle:.17g}",
                "inlet_mdot_Om": "0",
                "outlet_mdot_Om": "0",
                "inlet_mdot_Op": "0",
                "outlet_mdot_Op": "0",
            }
        )

    evidence = qf1_run._c2_evidence(path, electron_reference_m3=1.0e18)
    assert evidence["status"] == "MEASURED"
    assert evidence["initial_volume_charge_C"] == q_initial
    assert evidence["initial_charge_source"] == "r31_charge_integral evaluated on INITIAL"
    assert evidence["Delta_Q_C"] < 0.0
    assert evidence["Q_boundary_C"] > 0.0
    assert abs(evidence["R_Q_C"]) <= 1.0e-20
    assert evidence["component_relative_defect"] <= 1.0e-1
    assert evidence["acceptance"] == "UNSET_FIRST_CLOSED_FEEDBACK_MEASUREMENT"
