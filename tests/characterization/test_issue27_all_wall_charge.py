from __future__ import annotations

import json
import math
from pathlib import Path

from experiments.Issue27_surface_reactions.controlled_wall.charged import (
    AVOGADRO,
    BC_NAMES,
    FARADAY_C_PER_MOL,
    PLASMA_WALLS as CHARGED_WALLS,
    _build_charged_case_input,
    _validated_parameters as validate_charged,
)
from experiments.Issue27_surface_reactions.controlled_wall.multiwall import (
    PLASMA_WALLS as NEUTRAL_WALLS,
    _build_multiwall_case_input,
    _validated_parameters as validate_multiwall,
)
from qpx_harness.application.experiment_spec import load_experiment_spec
from qpx_harness.moose import blocks as mb
from qpx_harness.moose import parameters as mp

ROOT = Path(__file__).resolve().parents[2]
R4_SOURCE = ROOT / "experiments/Issue91_real_qvt_r3/r3_e0/heavy_base.i"
A1C_SPEC = ROOT / "experiments/Issue27_surface_reactions/A1c_o_sticking_all_walls/experiment.json"
A3E_SPEC = ROOT / "experiments/Issue27_surface_reactions/A3e_charged_wall_ledger/experiment.json"
EXPECTED_WALLS = (
    "plasma_electrode",
    "plasma_metal",
    "plasma_right",
    "plasma_cover",
    "plasma_wafer",
    "plasma_focus_ring",
)


def test_issue27_all_wall_sets_exclude_inlet_and_outlet() -> None:
    assert NEUTRAL_WALLS == EXPECTED_WALLS
    assert CHARGED_WALLS == EXPECTED_WALLS
    assert "inlet" not in EXPECTED_WALLS
    assert "outlet" not in EXPECTED_WALLS


def test_issue27_a1c_builds_sticking_on_all_six_plasma_walls() -> None:
    spec = load_experiment_spec(A1C_SPEC)
    frozen = validate_multiwall(spec.parameters)
    assert frozen["wall_scope"] == "all_plasma_walls"
    assert math.isclose(float(frozen["sticking_coefficient"]), 0.2)

    base = R4_SOURCE.read_text(encoding="utf-8")
    text, meta = _build_multiwall_case_input(
        base,
        parameters=spec.parameters,
        bc_factor=-1.0,
    )
    assert meta["predecessor"]["audit"]["status"] == "PASS"
    boundary = tuple(
        mp.words(
            mp.get_parameter(
                text,
                "FVBCs/issue27_a1b_O_sticking_wall_flux",
                "boundary",
            )
        )
    )
    assert boundary == EXPECTED_WALLS
    assert mp.get_parameter(
        text,
        "FVBCs/issue27_a1b_O_sticking_wall_flux",
        "type",
    ) == "FVFunctorNeumannBC"
    assert math.isclose(
        float(
            mp.get_parameter(
                text,
                "FVBCs/issue27_a1b_O_sticking_wall_flux",
                "factor",
            )
            or "nan"
        ),
        -1.0,
    )
    assert mb.has_block(text, "Variables/potential_plasma")
    assert mp.get_parameter(text, "FVKernels/n_e_drift", "potential") == "potential_plasma"


def test_issue27_a3e_charge_balance_algebra_is_exact() -> None:
    spec = load_experiment_spec(A3E_SPEC)
    frozen = validate_charged(spec.parameters)
    r_o2p = float(frozen["O2p_event_flux_mol_m2_s"])
    r_op = float(frozen["Op_event_flux_mol_m2_s"])
    r_om = float(frozen["Om_event_flux_mol_m2_s"])
    r_e = float(frozen["electron_absorption_molar_flux_mol_m2_s"])
    assert math.isclose(r_e, r_o2p + r_op - r_om, rel_tol=0.0, abs_tol=0.0)
    heavy_current = FARADAY_C_PER_MOL * (r_o2p + r_op - r_om)
    electron_current = -FARADAY_C_PER_MOL * r_e
    assert math.isclose(heavy_current + electron_current, 0.0, rel_tol=0.0, abs_tol=1.0e-18)


def test_issue27_a3e_heavy_only_and_balanced_bc_contracts() -> None:
    spec = load_experiment_spec(A3E_SPEC)
    base = R4_SOURCE.read_text(encoding="utf-8")
    heavy_text, heavy_meta = _build_charged_case_input(
        base,
        parameters=spec.parameters,
        mode="heavy_only",
    )
    balanced_text, balanced_meta = _build_charged_case_input(
        base,
        parameters=spec.parameters,
        mode="charge_balanced",
    )

    assert heavy_meta["predecessor"]["audit"]["status"] == "PASS"
    assert balanced_meta["predecessor"]["audit"]["status"] == "PASS"
    assert balanced_meta["excluded_boundaries"] == ["inlet", "outlet"]

    for species in ("O2p", "Op", "Om", "O", "electron"):
        path = f"FVBCs/{BC_NAMES[species]}"
        assert mp.get_parameter(balanced_text, path, "type") == "FVNeumannBC"
        assert tuple(mp.words(mp.get_parameter(balanced_text, path, "boundary"))) == EXPECTED_WALLS

    # A1 froze physical outward-positive flux -> MOOSE FVNeumannBC value = -J_out.
    assert float(mp.get_parameter(balanced_text, f"FVBCs/{BC_NAMES['O2p']}", "value") or "nan") < 0.0
    assert float(mp.get_parameter(balanced_text, f"FVBCs/{BC_NAMES['Op']}", "value") or "nan") < 0.0
    assert float(mp.get_parameter(balanced_text, f"FVBCs/{BC_NAMES['Om']}", "value") or "nan") < 0.0
    assert float(mp.get_parameter(balanced_text, f"FVBCs/{BC_NAMES['O']}", "value") or "nan") > 0.0

    # Electron solver unknown is n_hat.  The normalized wall flux must therefore
    # be Gamma_e/n_ref rather than the dimensional particle flux itself.
    n_ref = float(balanced_meta["electron_reference_density_m3"])
    r_e = float(
        balanced_meta["validated_parameters"]["electron_absorption_molar_flux_mol_m2_s"]
    )
    expected_e_value = -(AVOGADRO * r_e / n_ref)
    balanced_e = float(
        mp.get_parameter(balanced_text, f"FVBCs/{BC_NAMES['electron']}", "value")
        or "nan"
    )
    heavy_e = float(
        mp.get_parameter(heavy_text, f"FVBCs/{BC_NAMES['electron']}", "value")
        or "nan"
    )
    assert math.isclose(balanced_e, expected_e_value, rel_tol=1.0e-14)
    assert heavy_e == 0.0

    assert mb.has_block(balanced_text, "Variables/potential_plasma")
    assert mp.get_parameter(
        balanced_text,
        "FVKernels/n_e_drift",
        "potential",
    ) == "potential_plasma"


def test_issue27_new_specs_use_existing_issue27_protocol() -> None:
    a1c = json.loads(A1C_SPEC.read_text(encoding="utf-8"))
    a3e = json.loads(A3E_SPEC.read_text(encoding="utf-8"))
    assert a1c["protocol"] == "issue27-surface-reaction-controlled-wall"
    assert a3e["protocol"] == "issue27-surface-reaction-controlled-wall"
    assert a1c["parameters"]["wall_model"] == "sticking_all_walls"
    assert a3e["parameters"]["wall_model"] == "charged_prescribed_ledger"
