#!/usr/bin/env python3
"""Run Issue #27 A4 excited-neutral wall-quenching controls on accepted R4-QF1."""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any, Mapping

from experiments.Issue31_r4_q0_all_ground import run as q0_run
from experiments.Issue91_real_qvt_r3 import run as issue91_run
from qpx_harness.evidence import create_collision_safe_directory, utc_timestamp, write_json_bundle
from qpx_harness.execution.cases import stage_case
from qpx_harness.execution.runtime import resolve_executable, validate_executable
from qpx_harness.adapters.moose import blocks as mb
from qpx_harness.adapters.moose import parameters as mp
from experiments.historical_recipe_support.issue31_r4_qf1 import build_r4_qf1_input

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "experiments" / "Issue91_real_qvt_r3" / "r3_e0"

GAS_CONSTANT_J_PER_MOL_K = 8.31446
M_O2_KG_PER_MOL = 0.032
M_O_KG_PER_MOL = 0.016
PLASMA_WALLS = (
    "plasma_electrode",
    "plasma_metal",
    "plasma_right",
    "plasma_cover",
    "plasma_wafer",
    "plasma_focus_ring",
)
CASE_MODES = ("control", "o2s_quench", "os_quench")

O2S_FLUX_MATERIAL = "issue27_a4_O2s_quench_flux"
O2S_FLUX_FUNCTOR = "issue27_a4_O2s_wall_flux_outward"
O2S_BC = "issue27_a4_O2s_wall_quench"
O2S_RATE_PP = "issue27_a4_O2s_wall_mass_rate_outward"

OS_FLUX_MATERIAL = "issue27_a4_Os_quench_flux"
OS_FLUX_FUNCTOR = "issue27_a4_Os_wall_flux_outward"
OS_BC = "issue27_a4_Os_wall_quench"
OS_RATE_PP = "issue27_a4_Os_wall_mass_rate_outward"

AREA_PP = "issue27_a4_wall_area"


class Issue27ExcitedNeutralWallError(RuntimeError):
    pass


def _float_parameter(parameters: Mapping[str, Any], name: str, default: float) -> float:
    raw = parameters.get(name, default)
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise Issue27ExcitedNeutralWallError(f"parameters.{name} must be numeric") from exc
    if not math.isfinite(value):
        raise Issue27ExcitedNeutralWallError(f"parameters.{name} must be finite")
    return value


def _validated_parameters(parameters: Mapping[str, Any]) -> dict[str, Any]:
    wall_model = str(parameters.get("wall_model", ""))
    if wall_model != "excited_neutral_sticking_control":
        raise Issue27ExcitedNeutralWallError(
            "A4 requires wall_model='excited_neutral_sticking_control'"
        )
    wall_scope = str(parameters.get("wall_scope", ""))
    if wall_scope != "all_plasma_walls":
        raise Issue27ExcitedNeutralWallError("A4 requires wall_scope='all_plasma_walls'")

    tg = str(parameters.get("gas_temperature_functor", "T_g"))
    if tg != "T_g":
        raise Issue27ExcitedNeutralWallError("A4 gas_temperature_functor is frozen to 'T_g'")
    motz = parameters.get("motz_wise_correction", False)
    if motz is not False:
        raise Issue27ExcitedNeutralWallError("A4 is frozen to Motz-Wise OFF")

    s_o2s = _float_parameter(parameters, "O2s_sticking_coefficient", 1.0)
    s_os = _float_parameter(parameters, "Os_sticking_coefficient", 0.2)
    for name, value in (("O2s_sticking_coefficient", s_o2s), ("Os_sticking_coefficient", s_os)):
        if not 0.0 < value <= 1.0:
            raise Issue27ExcitedNeutralWallError(f"{name} must lie in (0, 1]")

    return {
        "wall_model": wall_model,
        "wall_scope": wall_scope,
        "wall_boundaries": list(PLASMA_WALLS),
        "excluded_boundaries": ["inlet", "outlet"],
        "gas_temperature_functor": "T_g",
        "motz_wise_correction": False,
        "O2s_sticking_coefficient": s_o2s,
        "Os_sticking_coefficient": s_os,
        "surface_reactions": ["O2s -> constrained O2", "Os -> 0.5 constrained O2"],
        "secondary_emission": False,
        "electron_compensation": False,
    }


def _thermal_flux_expression(sticking: float, molar_mass: float, weight_symbol: str) -> str:
    thermal_speed = (
        f"sqrt(8.0*{GAS_CONSTANT_J_PER_MOL_K:.17g}*tg/"
        f"(3.14159265358979323846*{molar_mass:.17g}))"
    )
    return f"{sticking:.17g}*0.25*{thermal_speed}*rho*{weight_symbol}"


def _build_a4_case_input(
    base_text: str,
    *,
    parameters: Mapping[str, Any],
    mode: str,
) -> tuple[str, dict[str, Any]]:
    if mode not in CASE_MODES:
        raise Issue27ExcitedNeutralWallError(f"unsupported A4 mode {mode!r}")
    frozen = _validated_parameters(parameters)
    text, predecessor = build_r4_qf1_input(base_text)
    if predecessor["audit"]["status"] != "PASS":
        raise Issue27ExcitedNeutralWallError("R4-QF1 predecessor audit is not PASS")

    wall_list = "'" + " ".join(PLASMA_WALLS) + "'"
    for path in (
        f"FunctorMaterials/{O2S_FLUX_MATERIAL}",
        f"FunctorMaterials/{OS_FLUX_MATERIAL}",
        f"FVBCs/{O2S_BC}",
        f"FVBCs/{OS_BC}",
        f"Postprocessors/{AREA_PP}",
        f"Postprocessors/{O2S_RATE_PP}",
        f"Postprocessors/{OS_RATE_PP}",
    ):
        mb.require_absent(text, path)

    o2s_expression = _thermal_flux_expression(
        float(frozen["O2s_sticking_coefficient"]), M_O2_KG_PER_MOL, "wo2s"
    )
    os_expression = _thermal_flux_expression(
        float(frozen["Os_sticking_coefficient"]), M_O_KG_PER_MOL, "wos"
    )

    text = mb.insert_child_block(
        text,
        "FunctorMaterials",
        f"""  [{O2S_FLUX_MATERIAL}]
    type = ADParsedFunctorMaterial
    property_name = {O2S_FLUX_FUNCTOR}
    functor_names = 'rho_mat w_O2s T_g'
    functor_symbols = 'rho wo2s tg'
    expression = '{o2s_expression}'
    block = plasma
  []""",
    )
    text = mb.insert_child_block(
        text,
        "FunctorMaterials",
        f"""  [{OS_FLUX_MATERIAL}]
    type = ADParsedFunctorMaterial
    property_name = {OS_FLUX_FUNCTOR}
    functor_names = 'rho_mat w_Os T_g'
    functor_symbols = 'rho wos tg'
    expression = '{os_expression}'
    block = plasma
  []""",
    )

    o2s_factor = -1.0 if mode == "o2s_quench" else 0.0
    os_factor = -1.0 if mode == "os_quench" else 0.0
    text = mb.insert_child_block(
        text,
        "FVBCs",
        f"""  [{O2S_BC}]
    type = FVFunctorNeumannBC
    variable = w_O2s
    boundary = {wall_list}
    functor = {O2S_FLUX_FUNCTOR}
    factor = {o2s_factor:.17g}
  []""",
    )
    text = mb.insert_child_block(
        text,
        "FVBCs",
        f"""  [{OS_BC}]
    type = FVFunctorNeumannBC
    variable = w_Os
    boundary = {wall_list}
    functor = {OS_FLUX_FUNCTOR}
    factor = {os_factor:.17g}
  []""",
    )

    text = mb.insert_child_block(
        text,
        "Postprocessors",
        f"""  [{AREA_PP}]
    type = AreaPostprocessor
    boundary = {wall_list}
    execute_on = 'INITIAL TIMESTEP_END'
  []""",
    )
    for name, functor in ((O2S_RATE_PP, O2S_FLUX_FUNCTOR), (OS_RATE_PP, OS_FLUX_FUNCTOR)):
        text = mb.insert_child_block(
            text,
            "Postprocessors",
            f"""  [{name}]
    type = ADSideIntegralFunctorPostprocessor
    boundary = {wall_list}
    functor = {functor}
    restrict_to_functors_domain = true
    execute_on = 'INITIAL TIMESTEP_END'
  []""",
        )

    for pp in (
        "mass_total",
        "mass_O2",
        "mass_O2s",
        "mass_Os",
        "w_O2_min",
        "w_O2s_min",
        "w_Os_min",
        "r31_charge_integral",
        "r31_gauss_flux_charge",
    ):
        text = mp.upsert_parameter(
            text,
            f"Postprocessors/{pp}",
            "execute_on",
            "'INITIAL TIMESTEP_END'",
        )

    return text, {
        "issue": 27,
        "experiment": "A4_R4_QF1_EXCITED_NEUTRAL_QUENCHING",
        "mode": mode,
        "predecessor": predecessor,
        "validated_parameters": frozen,
        "wall_boundaries": list(PLASMA_WALLS),
        "excluded_boundaries": ["inlet", "outlet"],
        "surface_reactions": {
            "O2s": {
                "reaction": "O2s -> constrained O2",
                "molar_mass_kg_per_mol": M_O2_KG_PER_MOL,
                "sticking_coefficient": frozen["O2s_sticking_coefficient"],
                "outward_mass_flux_expression": o2s_expression,
                "fvbc_factor": o2s_factor,
            },
            "Os": {
                "reaction": "Os -> 0.5 constrained O2",
                "molar_mass_kg_per_mol": M_O_KG_PER_MOL,
                "sticking_coefficient": frozen["Os_sticking_coefficient"],
                "outward_mass_flux_expression": os_expression,
                "fvbc_factor": os_factor,
            },
        },
        "sign_contract": "physical outward-positive neutral loss -> FVFunctorNeumannBC factor = -1",
        "n_minus_1_contract": (
            "O2 is constrained; loss of solved O2s or Os is returned as equal mass of constrained O2"
        ),
        "frozen_phase": {
            "R4_QF1_preserved": True,
            "volumetric_reactions": False,
            "secondary_emission": False,
            "electron_wall_compensation": False,
            "surface_accumulated_charge": False,
        },
    }


def _stage_case(
    target: Path,
    *,
    parameters: Mapping[str, Any],
    mode: str,
) -> dict[str, Any]:
    base = (SOURCE / "heavy_base.i").read_text(encoding="utf-8")
    input_text, meta = _build_a4_case_input(base, parameters=parameters, mode=mode)
    staging = stage_case(
        SOURCE,
        target,
        input_text=input_text,
        purge_directory_names=(".jitcache", "checkpoint", "checkpoints"),
        purge_patterns=("input_out*", "*.log", "*.e", "*.exo", "prepare_evidence.json"),
    )
    reference = float(
        meta["predecessor"]["predecessor"]["quasi_neutral_reference"][
            "electron_reference_density_m3"
        ]
    )
    expected_path = target / "expected.json"
    if expected_path.is_file():
        expected = json.loads(expected_path.read_text(encoding="utf-8"))
        expected["field_strength"] = 0.0
        expected["n0"] = reference
        expected_path.write_text(json.dumps(expected, indent=2, sort_keys=True) + "\n")
    (target / "prepare_evidence.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {"source": str(SOURCE.resolve()), "staging": staging, "construction": meta}


def _read_final_state(csv_path: Path) -> dict[str, Any]:
    if not csv_path.is_file():
        return {"status": "MISSING", "error": f"missing {csv_path.name}"}
    with csv_path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) < 2:
        return {"status": "MISSING", "error": "need INITIAL and TIMESTEP_END rows"}
    required = (
        "time",
        AREA_PP,
        O2S_RATE_PP,
        OS_RATE_PP,
        "mass_total",
        "mass_O2",
        "mass_O2s",
        "mass_Os",
        "w_O2_min",
        "w_O2s_min",
        "w_Os_min",
        "r31_charge_integral",
        "r31_gauss_flux_charge",
    )
    row = rows[-1]
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


def _rel_defect(measured: float, expected: float) -> float:
    return abs(measured - expected) / max(abs(expected), 1.0e-300)


def _single_case_evidence(
    case: Mapping[str, Any],
    control: Mapping[str, Any],
    *,
    species: str,
    rate_pp: str,
) -> dict[str, Any]:
    dt = float(case["time"])
    rate = float(case[rate_pp])
    expected_transfer = rate * dt
    mass_key = f"mass_{species}"
    delta_species = float(case[mass_key]) - float(control[mass_key])
    delta_o2 = float(case["mass_O2"]) - float(control["mass_O2"])
    delta_total = float(case["mass_total"]) - float(control["mass_total"])
    delta_charge = float(case["r31_charge_integral"]) - float(control["r31_charge_integral"])
    gauss_defect = float(case["r31_gauss_flux_charge"]) - float(case["r31_charge_integral"])
    scale = max(abs(expected_transfer), 1.0e-300)
    return {
        "applied_wall_mass_rate_kg_s": rate,
        "implicit_euler_expected_transfer_kg": expected_transfer,
        "delta_species_mass_vs_control_kg": delta_species,
        "delta_constrained_O2_mass_vs_control_kg": delta_o2,
        "delta_total_mass_vs_control_kg": delta_total,
        "delta_volume_charge_vs_control_C": delta_charge,
        "gauss_defect_C": gauss_defect,
        "outward_species_loss_observed": delta_species < 0.0,
        "species_magnitude_relative_defect": _rel_defect(delta_species, -expected_transfer),
        "species_O2_stoich_relative_defect": abs(delta_species + delta_o2) / scale,
        "total_mass_relative_to_surface_transfer": abs(delta_total) / scale,
    }


def _differential_evidence(
    states: Mapping[str, Mapping[str, Any]],
    *,
    parameters: Mapping[str, Any],
) -> dict[str, Any]:
    if any(states[name].get("status") != "MEASURED" for name in CASE_MODES):
        return {"status": "MISSING", "error": "one or more A4 states are not measured"}
    frozen = _validated_parameters(parameters)
    times = [float(states[name]["time"]) for name in CASE_MODES]
    if times[0] <= 0.0 or any(
        not math.isclose(times[0], value, rel_tol=0.0, abs_tol=1.0e-18)
        for value in times[1:]
    ):
        return {"status": "INVALID", "error": f"inconsistent final times: {times}"}
    areas = [float(states[name][AREA_PP]) for name in CASE_MODES]
    if min(areas) <= 0.0 or any(
        not math.isclose(areas[0], value, rel_tol=1.0e-12, abs_tol=0.0)
        for value in areas[1:]
    ):
        return {"status": "INVALID", "error": f"inconsistent wall areas: {areas}"}

    control = states["control"]
    o2s = _single_case_evidence(
        states["o2s_quench"], control, species="O2s", rate_pp=O2S_RATE_PP
    )
    os = _single_case_evidence(
        states["os_quench"], control, species="Os", rate_pp=OS_RATE_PP
    )
    nonnegative = all(
        float(states[mode][key]) >= -1.0e-12
        for mode in ("o2s_quench", "os_quench")
        for key in ("w_O2_min", "w_O2s_min", "w_Os_min")
    )
    return {
        "status": "MEASURED",
        "wall_boundaries": list(PLASMA_WALLS),
        "excluded_boundaries": ["inlet", "outlet"],
        "final_time_s": times[0],
        "combined_wall_area_m2": areas[0],
        "parameters": frozen,
        "o2s_quench": o2s,
        "os_quench": os,
        "nonnegative_state": nonnegative,
        "scientific_acceptance": "UNSET_EVIDENCE_ONLY",
        "interpretation_contract": (
            "A4 validates neutral excited-species quenching and constrained-O2 mass/atom bookkeeping; "
            "no charged-wall or SEE claim is made"
        ),
    }


def run_excited_neutral_wall_control(
    *,
    qpx: str | Path | None,
    results_root: Path,
    timeout: float,
    parameters: Mapping[str, Any],
) -> int:
    if timeout <= 0.0:
        raise Issue27ExcitedNeutralWallError("timeout must be positive")
    exe = resolve_executable(qpx)
    validate_executable(exe)
    frozen = _validated_parameters(parameters)
    stamp = utc_timestamp().replace(":", "").replace("-", "")
    root = create_collision_safe_directory(
        results_root,
        f"issue27_a4_r4_qf1_excited_neutral_quenching_{stamp}",
    )
    cases_root = root / "cases"
    logs = root / "logs"
    cases_root.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)

    staged: dict[str, Any] = {}
    for mode in CASE_MODES:
        staged[mode] = _stage_case(cases_root / mode, parameters=parameters, mode=mode)

    summary: dict[str, Any] = {
        "issue": 27,
        "experiment": "A4_excited_neutral_quenching",
        "scientific_scope": (
            "state-dependent O2s -> constrained O2 and Os -> 0.5 constrained O2 wall quenching "
            "on all six plasma-facing walls"
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
        p2 = q0_run._p2(exe, cases_root / mode, logs / f"a4_{mode}_p2.log", timeout)
        summary["p2"][mode] = p2
        if p2["returncode"] != 0:
            summary["status"] = f"A4_P2_FAIL_{mode.upper()}"
            write_json_bundle(root, {"summary": ("summary.json", summary)})
            print(f"ISSUE27_A4_STATUS: {summary['status']}")
            print(f"EVIDENCE_DIR: {root}")
            return 2

    states: dict[str, Mapping[str, Any]] = {}
    for mode in CASE_MODES:
        case_dir = cases_root / mode
        runtime = q0_run._runtime(exe, case_dir, logs / f"a4_{mode}_runtime.log", timeout)
        state = _read_final_state(case_dir / "input_out.csv")
        summary["cases"][mode] = {"runtime": runtime, "state": state}
        if runtime["returncode"] != 0:
            summary["status"] = f"A4_RUNTIME_FAIL_{mode.upper()}"
            write_json_bundle(root, {"summary": ("summary.json", summary)})
            print(f"ISSUE27_A4_STATUS: {summary['status']}")
            print(f"EVIDENCE_DIR: {root}")
            return 1
        states[mode] = state

    evidence = _differential_evidence(states, parameters=parameters)
    summary["differential"] = evidence
    summary["status"] = (
        "A4_EXCITED_NEUTRAL_EVIDENCE_READY_NOT_ACCEPTED"
        if evidence.get("status") == "MEASURED"
        else "A4_EVIDENCE_MISSING"
    )
    write_json_bundle(root, {"summary": ("summary.json", summary)})
    print(f"ISSUE27_A4_STATUS: {summary['status']}")
    if evidence.get("status") == "MEASURED":
        print(f"WALL_COUNT: {len(PLASMA_WALLS)}")
        print(f"COMBINED_WALL_AREA_M2: {evidence['combined_wall_area_m2']}")
        for label in ("o2s_quench", "os_quench"):
            item = evidence[label]
            print(f"{label.upper()}_DELTA_SPECIES_KG: {item['delta_species_mass_vs_control_kg']}")
            print(f"{label.upper()}_STOICH_DEFECT: {item['species_O2_stoich_relative_defect']}")
            print(f"{label.upper()}_TOTAL_MASS_DEFECT: {item['total_mass_relative_to_surface_transfer']}")
            print(f"{label.upper()}_DELTA_Q_C: {item['delta_volume_charge_vs_control_C']}")
    print(f"EVIDENCE_DIR: {root}")
    return 0 if evidence.get("status") == "MEASURED" else 1


__all__ = [
    "AREA_PP",
    "CASE_MODES",
    "O2S_BC",
    "OS_BC",
    "PLASMA_WALLS",
    "Issue27ExcitedNeutralWallError",
    "_build_a4_case_input",
    "_differential_evidence",
    "_validated_parameters",
    "run_excited_neutral_wall_control",
]
