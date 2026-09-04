#!/usr/bin/env python3
"""Issue #27 A7 COMSOL-style electron thermal wall-loss discriminator.

This stage preserves accepted A6 heavy-wall chemistry and ion surface+migration
transport, removes the matched electron charge-ledger BC, and replaces it with
COMSOL-style random thermal electron wall loss.

The current R4-QF1 electron model solves density only. Therefore this stage
validates the electron *particle* wall-flux contract. The corresponding electron
energy wall flux remains deferred until an electron-energy solver variable is
activated.
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any, Mapping

from experiments.Issue31_r4_q0_all_ground import run as q0_run
from experiments.Issue91_real_qvt_r3 import run as issue91_run
from experiments.Issue27_surface_reactions.controlled_wall.combined import (
    AREA_PP,
    CHARGED,
    ELECTRON_BC as A6_ELECTRON_BC,
    ELECTRON_FUNCTOR as A6_ELECTRON_FUNCTOR,
    ELECTRON_PP as A6_ELECTRON_PP,
    M_O2_KG_PER_MOL,
    M_O_KG_PER_MOL,
    PLASMA_WALLS,
    _a5_preflight,
    _build_a6_case_input,
    _charged_names,
)
from qpx_harness.evidence import create_collision_safe_directory, utc_timestamp, write_json_bundle
from qpx_harness.execution.cases import stage_case
from qpx_harness.execution.runtime import resolve_executable, validate_executable
from qpx_harness.moose import blocks as mb
from qpx_harness.moose import parameters as mp
from recipes.issue91_r3 import MEAN_ELECTRON_ENERGY_EV

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "experiments" / "Issue91_real_qvt_r3" / "r3_e0"

ELEMENTARY_CHARGE_C = 1.602176634e-19
ELECTRON_MASS_KG = 9.1093837139e-31
AVOGADRO = 6.02214076e23
FARADAY_C_PER_MOL = AVOGADRO * ELEMENTARY_CHARGE_C

CASE_MODES = ("control", "electron_thermal_only", "combined_thermal")
THERMAL_FUNCTOR = "issue27_a7_electron_thermal_normalized_flux_outward"
THERMAL_MATERIAL = "issue27_a7_electron_thermal_wall_material"
THERMAL_BC = "issue27_a7_electron_thermal_wall_loss"
THERMAL_PP = "issue27_a7_electron_thermal_wall_rate"


class Issue27ElectronWallError(RuntimeError):
    pass


def _float_parameter(parameters: Mapping[str, Any], name: str, default: float) -> float:
    raw = parameters.get(name, default)
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise Issue27ElectronWallError(f"parameters.{name} must be numeric") from exc
    if not math.isfinite(value):
        raise Issue27ElectronWallError(f"parameters.{name} must be finite")
    return value


def _validated_parameters(parameters: Mapping[str, Any]) -> dict[str, Any]:
    if str(parameters.get("wall_model", "")) != "comsol_electron_thermal_wall_control":
        raise Issue27ElectronWallError(
            "A7 requires wall_model='comsol_electron_thermal_wall_control'"
        )
    if str(parameters.get("wall_scope", "")) != "all_plasma_walls":
        raise Issue27ElectronWallError("A7 requires wall_scope='all_plasma_walls'")

    reflection = _float_parameter(parameters, "electron_reflection_coefficient", 0.0)
    if reflection != 0.0:
        raise Issue27ElectronWallError("A7 COMSOL ICP reference freezes electron reflection to 0")

    see = _float_parameter(parameters, "secondary_emission_coefficient", 0.0)
    if see != 0.0:
        raise Issue27ElectronWallError("A7 is frozen to SEE=0")

    if parameters.get("electron_wall_migration", False) is not False:
        raise Issue27ElectronWallError(
            "A7 COMSOL ICP reference freezes electron wall migration OFF"
        )
    if parameters.get("electron_energy_wall_coupling", False) is not False:
        raise Issue27ElectronWallError(
            "A7 density-only R4-QF1 cannot enable electron-energy wall coupling"
        )

    expected_sticking = {
        "O_sticking_coefficient": 0.2,
        "O2s_sticking_coefficient": 1.0,
        "Os_sticking_coefficient": 0.2,
        "O2p_sticking_coefficient": 1.0,
        "Om_sticking_coefficient": 1.0,
        "Op_sticking_coefficient": 1.0,
    }
    frozen: dict[str, Any] = {
        "wall_model": "comsol_electron_thermal_wall_control",
        "wall_scope": "all_plasma_walls",
        "wall_boundaries": list(PLASMA_WALLS),
        "excluded_boundaries": ["inlet", "outlet"],
        "electron_reflection_coefficient": reflection,
        "electron_wall_migration": False,
        "secondary_emission_coefficient": 0.0,
        "electron_energy_wall_coupling": False,
        "electron_mean_energy_eV": MEAN_ELECTRON_ENERGY_EV,
        "electron_mean_energy_source": "FunctorMaterials/electron_constants:mean_en",
    }
    for name, expected in expected_sticking.items():
        value = _float_parameter(parameters, name, expected)
        if not math.isclose(value, expected, rel_tol=0.0, abs_tol=0.0):
            raise Issue27ElectronWallError(f"A7 freezes {name}={expected}, got {value}")
        frozen[name] = value
    return frozen


def _a6_parameters(parameters: Mapping[str, Any]) -> dict[str, Any]:
    frozen = _validated_parameters(parameters)
    return {
        "wall_model": "combined_comsol_wall_control",
        "wall_scope": "all_plasma_walls",
        "gas_temperature_functor": "T_g",
        "motz_wise_correction": False,
        "O_sticking_coefficient": frozen["O_sticking_coefficient"],
        "O2s_sticking_coefficient": frozen["O2s_sticking_coefficient"],
        "Os_sticking_coefficient": frozen["Os_sticking_coefficient"],
        "O2p_sticking_coefficient": frozen["O2p_sticking_coefficient"],
        "Om_sticking_coefficient": frozen["Om_sticking_coefficient"],
        "Op_sticking_coefficient": frozen["Op_sticking_coefficient"],
        "secondary_emission_coefficient": 0.0,
        "electron_wall_mode": "matched_signed_charge_ledger",
    }


def _thermal_speed_from_mean_energy(mean_energy_eV: float) -> float:
    """COMSOL Maxwellian thermal speed using mean energy = 3/2 k_B T_e."""
    if mean_energy_eV <= 0.0:
        raise Issue27ElectronWallError("mean electron energy must be positive")
    return math.sqrt(
        16.0 * ELEMENTARY_CHARGE_C * mean_energy_eV
        / (3.0 * math.pi * ELECTRON_MASS_KG)
    )


def _mode_contract(mode: str) -> tuple[str, bool]:
    if mode == "control":
        return "control", False
    if mode == "electron_thermal_only":
        return "control", True
    if mode == "combined_thermal":
        return "comsol_wall", True
    raise Issue27ElectronWallError(f"unsupported A7 mode {mode!r}")


def _build_a7_case_input(
    base_text: str,
    *,
    parameters: Mapping[str, Any],
    mode: str,
) -> tuple[str, dict[str, Any]]:
    frozen = _validated_parameters(parameters)
    a6_mode, thermal_on = _mode_contract(mode)
    text, a6_meta = _build_a6_case_input(
        base_text,
        parameters=_a6_parameters(parameters),
        mode=a6_mode,
    )

    # A7 replaces, rather than composes with, the accepted A6 matched ledger.
    for path in (
        f"FunctorMaterials/issue27_a6_electron_ledger_material",
        f"FVBCs/{A6_ELECTRON_BC}",
        f"Postprocessors/{A6_ELECTRON_PP}",
    ):
        if not mb.has_block(text, path):
            raise Issue27ElectronWallError(f"expected A6 electron-ledger block missing: {path}")
        text = mb.remove_block(text, path)

    for path in (
        f"FunctorMaterials/{THERMAL_MATERIAL}",
        f"FVBCs/{THERMAL_BC}",
        f"Postprocessors/{THERMAL_PP}",
    ):
        mb.require_absent(text, path)

    reflection_factor = (
        (1.0 - float(frozen["electron_reflection_coefficient"]))
        / (1.0 + float(frozen["electron_reflection_coefficient"]))
    )
    expression = (
        f"{0.5 * reflection_factor:.17g}*ne_hat*"
        f"sqrt(16.0*{ELEMENTARY_CHARGE_C:.17g}*mean_ev/"
        f"(3.0*3.14159265358979323846*{ELECTRON_MASS_KG:.17g}))"
    )
    wall_list = "'" + " ".join(PLASMA_WALLS) + "'"

    text = mb.insert_child_block(
        text,
        "FunctorMaterials",
        f"""  [{THERMAL_MATERIAL}]
    type = ADParsedFunctorMaterial
    property_name = {THERMAL_FUNCTOR}
    functor_names = 'n_e mean_en'
    functor_symbols = 'ne_hat mean_ev'
    expression = '{expression}'
    block = plasma
  []""",
    )
    text = mb.insert_child_block(
        text,
        "FVBCs",
        f"""  [{THERMAL_BC}]
    type = FVFunctorNeumannBC
    variable = n_e
    boundary = {wall_list}
    functor = {THERMAL_FUNCTOR}
    factor = {-1.0 if thermal_on else 0.0:.17g}
  []""",
    )
    text = mb.insert_child_block(
        text,
        "Postprocessors",
        f"""  [{THERMAL_PP}]
    type = SideFVFluxBCIntegral
    boundary = {wall_list}
    fvbcs = '{THERMAL_BC}'
    execute_on = 'INITIAL TIMESTEP_END'
  []""",
    )

    for pp in (
        "n_e_inventory",
        "n_e_min",
        "r31_charge_integral",
        "r31_gauss_flux_charge",
        "sum_w_min",
        "sum_w_max",
    ):
        text = mp.upsert_parameter(
            text,
            f"Postprocessors/{pp}",
            "execute_on",
            "'INITIAL TIMESTEP_END'",
        )

    a5 = _a5_preflight(text, a6_meta)
    if a5["status"] != "PASS":
        raise Issue27ElectronWallError(f"A5 preflight failed for A7 {mode}: {a5['failures']}")

    return text, {
        "issue": 27,
        "experiment": "A7_COMSOL_ELECTRON_THERMAL_WALL",
        "mode": mode,
        "a6_base_mode": a6_mode,
        "a6_construction": a6_meta,
        "a5_preflight": a5,
        "validated_parameters": frozen,
        "thermal_wall_enabled": thermal_on,
        "electron_reference_density_m3": float(a6_meta["electron_reference_density_m3"]),
        "thermal_speed_m_s": _thermal_speed_from_mean_energy(MEAN_ELECTRON_ENERGY_EV),
        "particle_flux_contract": (
            "Gamma_e,out/n_ref = ((1-r_e)/(1+r_e))*0.5*n_hat*"
            "sqrt(16*e*mean_energy_eV/(3*pi*m_e)); r_e=0"
        ),
        "sign_contract": "physical outward positive -> FVFunctorNeumannBC factor = -1",
        "matched_a6_electron_ledger_removed": True,
        "electron_wall_migration": False,
        "secondary_emission": False,
        "electron_energy_wall_coupling": False,
        "electron_energy_deferral": (
            "R4-QF1 has no electron-energy solver variable; COMSOL energy wall flux "
            "must be coupled when #26 activates the electron-energy equation"
        ),
        "current_balance_policy": (
            "not forced: volume charge is allowed to respond self-consistently to "
            "independent heavy-wall and electron thermal wall currents"
        ),
    }


def _stage_case(
    target: Path,
    *,
    parameters: Mapping[str, Any],
    mode: str,
) -> dict[str, Any]:
    base = (SOURCE / "heavy_base.i").read_text(encoding="utf-8")
    input_text, meta = _build_a7_case_input(base, parameters=parameters, mode=mode)
    staging = stage_case(
        SOURCE,
        target,
        input_text=input_text,
        purge_directory_names=(".jitcache", "checkpoint", "checkpoints"),
        purge_patterns=("input_out*", "*.log", "*.e", "*.exo", "prepare_evidence.json"),
    )
    expected_path = target / "expected.json"
    if expected_path.is_file():
        expected = json.loads(expected_path.read_text(encoding="utf-8"))
        expected["field_strength"] = 0.0
        expected["n0"] = float(meta["electron_reference_density_m3"])
        expected_path.write_text(json.dumps(expected, indent=2, sort_keys=True) + "\n")
    (target / "prepare_evidence.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "source": str(SOURCE.resolve()),
        "staging": staging,
        "construction": meta,
    }


def _required_columns() -> tuple[str, ...]:
    names = [
        "time",
        AREA_PP,
        THERMAL_PP,
        "n_e_inventory",
        "n_e_min",
        "sum_w_min",
        "sum_w_max",
        "r31_charge_integral",
        "r31_gauss_flux_charge",
    ]
    for species in CHARGED:
        for wall in PLASMA_WALLS:
            _, _, surface_pp, migration_pp = _charged_names(species, wall)
            names.extend((surface_pp, migration_pp))
    return tuple(names)


def _read_final_state(csv_path: Path) -> dict[str, Any]:
    if not csv_path.is_file():
        return {"status": "MISSING", "error": f"missing {csv_path.name}"}
    with csv_path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) < 2:
        return {"status": "MISSING", "error": "need INITIAL and TIMESTEP_END rows"}
    row = rows[-1]
    required = _required_columns()
    missing = [name for name in required if name not in row]
    if missing:
        return {"status": "MISSING", "error": f"missing CSV columns: {missing}"}
    try:
        values = {name: float(row[name]) for name in required}
    except (TypeError, ValueError) as exc:
        return {"status": "INVALID", "error": str(exc)}
    if not all(math.isfinite(value) for value in values.values()):
        return {"status": "INVALID", "error": "non-finite final-state value"}
    return {"status": "MEASURED", **values}


def _physical_rate(value: float) -> float:
    return abs(float(value))


def _heavy_charge_molar_rate(state: Mapping[str, Any]) -> float:
    rates: dict[str, float] = {}
    for species in CHARGED:
        total = 0.0
        for wall in PLASMA_WALLS:
            _, _, surface_pp, migration_pp = _charged_names(species, wall)
            total += _physical_rate(float(state[surface_pp]))
            total += _physical_rate(float(state[migration_pp]))
        rates[species] = total
    return (
        rates["O2p"] / M_O2_KG_PER_MOL
        + rates["Op"] / M_O_KG_PER_MOL
        - rates["Om"] / M_O_KG_PER_MOL
    )


def _rel_defect(measured: float, expected: float) -> float:
    return abs(measured - expected) / max(abs(expected), 1.0e-300)


def _differential_evidence(
    states: Mapping[str, Mapping[str, Any]],
    *,
    n_ref_m3: float,
) -> dict[str, Any]:
    if any(states[name].get("status") != "MEASURED" for name in CASE_MODES):
        return {"status": "MISSING", "error": "one or more A7 states are not measured"}

    control = states["control"]
    times = [float(states[name]["time"]) for name in CASE_MODES]
    if times[0] <= 0.0 or any(
        not math.isclose(times[0], value, rel_tol=0.0, abs_tol=1.0e-18)
        for value in times[1:]
    ):
        return {"status": "INVALID", "error": f"inconsistent final times: {times}"}
    dt = times[0]

    cases: dict[str, Any] = {}
    for mode in ("electron_thermal_only", "combined_thermal"):
        state = states[mode]
        normalized_wall_rate = _physical_rate(float(state[THERMAL_PP]))
        expected_electron_loss = normalized_wall_rate * n_ref_m3 * dt
        measured_electron_loss = (
            float(control["n_e_inventory"]) - float(state["n_e_inventory"])
        )
        electron_charge_delta = ELEMENTARY_CHARGE_C * expected_electron_loss

        heavy_molar_rate = _heavy_charge_molar_rate(state)
        heavy_charge_delta = -FARADAY_C_PER_MOL * heavy_molar_rate * dt
        expected_net_charge_delta = heavy_charge_delta + electron_charge_delta
        measured_net_charge_delta = (
            float(state["r31_charge_integral"])
            - float(control["r31_charge_integral"])
        )
        charge_scale = max(
            abs(heavy_charge_delta) + abs(electron_charge_delta),
            1.0e-300,
        )
        gauss_residual_delta = (
            (
                float(state["r31_gauss_flux_charge"])
                - float(state["r31_charge_integral"])
            )
            - (
                float(control["r31_gauss_flux_charge"])
                - float(control["r31_charge_integral"])
            )
        )
        composition_error = max(
            abs(float(state["sum_w_min"]) - 1.0),
            abs(float(state["sum_w_max"]) - 1.0),
        )

        cases[mode] = {
            "electron_normalized_wall_rate_integral_m3_s": normalized_wall_rate,
            "expected_electron_inventory_loss": expected_electron_loss,
            "measured_electron_inventory_loss": measured_electron_loss,
            "electron_inventory_relative_defect": _rel_defect(
                measured_electron_loss,
                expected_electron_loss,
            ),
            "expected_electron_charge_delta_C": electron_charge_delta,
            "heavy_wall_charge_molar_rate_mol_s": heavy_molar_rate,
            "expected_heavy_charge_delta_C": heavy_charge_delta,
            "expected_net_charge_delta_C": expected_net_charge_delta,
            "measured_net_charge_delta_C": measured_net_charge_delta,
            "net_charge_abs_defect_over_current_scale": (
                abs(measured_net_charge_delta - expected_net_charge_delta)
                / charge_scale
            ),
            "gauss_residual_delta_C": gauss_residual_delta,
            "composition_max_abs_error": composition_error,
            "nonnegative_electron_density": float(state["n_e_min"]) >= -1.0e-12,
            "current_balance_forced": False,
        }

    return {
        "status": "MEASURED",
        "final_time_s": dt,
        "electron_reference_density_m3": n_ref_m3,
        "thermal_speed_m_s": _thermal_speed_from_mean_energy(MEAN_ELECTRON_ENERGY_EV),
        "mean_electron_energy_eV": MEAN_ELECTRON_ENERGY_EV,
        "cases": cases,
        "scientific_acceptance": "UNSET_EVIDENCE_ONLY",
        "acceptance_contract": (
            "A7 electron particle wall loss must close electron inventory against the "
            "state-dependent COMSOL thermal wall integral, preserve n_e>=0, and produce "
            "the independently predicted net volume-charge change with Gauss consistency. "
            "No zero-current constraint is imposed. Electron-energy wall coupling and SEE "
            "remain outside this stage."
        ),
    }


def run_comsol_electron_thermal_wall_control(
    *,
    qpx: str | Path | None,
    results_root: Path,
    timeout: float,
    parameters: Mapping[str, Any],
) -> int:
    if timeout <= 0.0:
        raise Issue27ElectronWallError("timeout must be positive")
    exe = resolve_executable(qpx)
    validate_executable(exe)
    frozen = _validated_parameters(parameters)

    stamp = utc_timestamp().replace(":", "").replace("-", "")
    root = create_collision_safe_directory(
        results_root,
        f"issue27_a7_r4_qf1_comsol_electron_wall_{stamp}",
    )
    cases_root = root / "cases"
    logs = root / "logs"
    cases_root.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)

    staged: dict[str, Any] = {}
    for mode in CASE_MODES:
        staged[mode] = _stage_case(
            cases_root / mode,
            parameters=parameters,
            mode=mode,
        )
    n_ref = float(staged["control"]["construction"]["electron_reference_density_m3"])

    summary: dict[str, Any] = {
        "issue": 27,
        "experiment": "A7_comsol_electron_thermal_wall",
        "scientific_scope": (
            "COMSOL-style random thermal electron particle wall loss with r_e=0, "
            "electron wall migration OFF, SEE=0; accepted A6 ion wall physics is "
            "used unchanged in the combined case"
        ),
        "repository_head": issue91_run._repo_head(),
        "qpx_realpath": str(exe.resolve()),
        "qpx_sha256": issue91_run._sha256(exe),
        "parameters": frozen,
        "staged": staged,
        "p2": {},
        "cases": {},
        "differential": {},
        "status": "NOT_RUN",
    }

    for mode in CASE_MODES:
        p2 = q0_run._p2(
            exe,
            cases_root / mode,
            logs / f"a7_{mode}_p2.log",
            timeout,
        )
        summary["p2"][mode] = p2
        if p2["returncode"] != 0:
            summary["status"] = f"A7_P2_FAIL_{mode.upper()}"
            write_json_bundle(root, {"summary": ("summary.json", summary)})
            print(f"ISSUE27_A7_STATUS: {summary['status']}")
            print(f"EVIDENCE_DIR: {root}")
            return 2

    states: dict[str, Mapping[str, Any]] = {}
    for mode in CASE_MODES:
        case_dir = cases_root / mode
        runtime = q0_run._runtime(
            exe,
            case_dir,
            logs / f"a7_{mode}_runtime.log",
            timeout,
        )
        state = _read_final_state(case_dir / "input_out.csv")
        summary["cases"][mode] = {"runtime": runtime, "state": state}
        if runtime["returncode"] != 0:
            summary["status"] = f"A7_RUNTIME_FAIL_{mode.upper()}"
            write_json_bundle(root, {"summary": ("summary.json", summary)})
            print(f"ISSUE27_A7_STATUS: {summary['status']}")
            print(f"EVIDENCE_DIR: {root}")
            return 1
        states[mode] = state

    evidence = _differential_evidence(states, n_ref_m3=n_ref)
    summary["differential"] = evidence
    summary["status"] = (
        "A7_COMSOL_ELECTRON_THERMAL_WALL_EVIDENCE_READY_NOT_ACCEPTED"
        if evidence.get("status") == "MEASURED"
        else "A7_EVIDENCE_MISSING"
    )
    write_json_bundle(root, {"summary": ("summary.json", summary)})

    print(f"ISSUE27_A7_STATUS: {summary['status']}")
    print(f"A7_THERMAL_SPEED_M_S: {_thermal_speed_from_mean_energy(MEAN_ELECTRON_ENERGY_EV)}")
    if evidence.get("status") == "MEASURED":
        for mode in ("electron_thermal_only", "combined_thermal"):
            item = evidence["cases"][mode]
            print(
                f"{mode.upper()}_ELECTRON_INVENTORY_DEFECT: "
                f"{item['electron_inventory_relative_defect']}"
            )
            print(
                f"{mode.upper()}_NET_CHARGE_DEFECT_OVER_CURRENT_SCALE: "
                f"{item['net_charge_abs_defect_over_current_scale']}"
            )
            print(
                f"{mode.upper()}_DELTA_Q_C: {item['measured_net_charge_delta_C']}"
            )
            print(
                f"{mode.upper()}_GAUSS_RESIDUAL_DELTA_C: "
                f"{item['gauss_residual_delta_C']}"
            )
    print(f"EVIDENCE_DIR: {root}")
    return 0 if evidence.get("status") == "MEASURED" else 1


__all__ = [
    "CASE_MODES",
    "THERMAL_BC",
    "THERMAL_FUNCTOR",
    "THERMAL_PP",
    "Issue27ElectronWallError",
    "_build_a7_case_input",
    "_thermal_speed_from_mean_energy",
    "_validated_parameters",
    "run_comsol_electron_thermal_wall_control",
]
