#!/usr/bin/env python3
"""Issue #27 A8 finite ion-induced SEE control on the accepted A7 wall model.

A8 keeps the accepted A7 COMSOL-style electron thermal wall loss and A6
heavy-wall chemistry/ion migration, then adds ion-induced secondary electron
emission from O2+ and O+ with the COMSOL oxygen-ICP coefficients

    gamma_O2+ = gamma_O+ = 0.05
    mean secondary-electron energy = 4 eV (4 V per emitted electron).

The current R4-QF1 model still has no solved electron-energy variable. Therefore
A8 couples the SEE *particle* source to the solved electron-density equation and
validates the corresponding 4 eV secondary-electron energy flux as a runtime
ledger. The later #26 electron-energy equation will consume this same validated
energy-flux contract; A8 does not fabricate an energy state.
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
    CHARGED,
    M_O2_KG_PER_MOL,
    M_O_KG_PER_MOL,
    PLASMA_WALLS,
    _charged_names,
)
from experiments.Issue27_surface_reactions.controlled_wall.electron_wall import (
    THERMAL_BC,
    THERMAL_PP,
)
from experiments.Issue27_surface_reactions.controlled_wall.electron_wall_stable import (
    A7_DISCRIMINATOR_DT_S,
    _build_a7_case_input,
)
from qpx_harness.evidence import create_collision_safe_directory, utc_timestamp, write_json_bundle
from qpx_harness.execution.cases import stage_case
from qpx_harness.execution.runtime import resolve_executable, validate_executable
from qpx_harness.adapters.moose import blocks as mb
from qpx_harness.adapters.moose import parameters as mp

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "experiments" / "Issue91_real_qvt_r3" / "r3_e0"

AVOGADRO = 6.02214076e23
ELEMENTARY_CHARGE_C = 1.602176634e-19
FARADAY_C_PER_MOL = AVOGADRO * ELEMENTARY_CHARGE_C
CASE_MODES = ("see_off", "see_on")
SEE_MATERIAL = "issue27_a8_see_material"
SEE_FUNCTOR = "issue27_a8_see_normalized_flux_inward"
SEE_BC = "issue27_a8_see_electron_source"
SEE_PP = "issue27_a8_see_particle_rate_normalized"
SEE_ENERGY_PP = "issue27_a8_see_energy_power"


class Issue27SEEError(RuntimeError):
    pass


def _float_parameter(parameters: Mapping[str, Any], name: str, default: float) -> float:
    raw = parameters.get(name, default)
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise Issue27SEEError(f"parameters.{name} must be numeric") from exc
    if not math.isfinite(value):
        raise Issue27SEEError(f"parameters.{name} must be finite")
    return value


def _validated_parameters(parameters: Mapping[str, Any]) -> dict[str, Any]:
    if str(parameters.get("wall_model", "")) != "finite_see_control":
        raise Issue27SEEError("A8 requires wall_model='finite_see_control'")
    if str(parameters.get("wall_scope", "")) != "all_plasma_walls":
        raise Issue27SEEError("A8 requires wall_scope='all_plasma_walls'")

    gamma_o2p = _float_parameter(parameters, "O2p_secondary_emission_coefficient", 0.05)
    gamma_op = _float_parameter(parameters, "Op_secondary_emission_coefficient", 0.05)
    energy_ev = _float_parameter(parameters, "secondary_electron_mean_energy_eV", 4.0)
    if gamma_o2p != 0.05 or gamma_op != 0.05:
        raise Issue27SEEError("A8 freezes O2+/O+ SEE coefficients to 0.05")
    if energy_ev != 4.0:
        raise Issue27SEEError("A8 freezes secondary-electron mean energy to 4 eV")
    if parameters.get("electron_wall_migration", False) is not False:
        raise Issue27SEEError("A8 retains COMSOL ICP electron wall migration OFF")
    if parameters.get("electron_energy_equation_coupled", False) is not False:
        raise Issue27SEEError(
            "A8 validates the SEE energy ledger only; solved energy coupling belongs to #26"
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
        "wall_model": "finite_see_control",
        "wall_scope": "all_plasma_walls",
        "wall_boundaries": list(PLASMA_WALLS),
        "excluded_boundaries": ["inlet", "outlet"],
        "O2p_secondary_emission_coefficient": gamma_o2p,
        "Op_secondary_emission_coefficient": gamma_op,
        "secondary_electron_mean_energy_eV": energy_ev,
        "electron_wall_migration": False,
        "electron_energy_equation_coupled": False,
    }
    for name, expected in expected_sticking.items():
        value = _float_parameter(parameters, name, expected)
        if not math.isclose(value, expected, rel_tol=0.0, abs_tol=0.0):
            raise Issue27SEEError(f"A8 freezes {name}={expected}, got {value}")
        frozen[name] = value
    return frozen


def _a7_parameters(parameters: Mapping[str, Any]) -> dict[str, Any]:
    frozen = _validated_parameters(parameters)
    return {
        "wall_model": "comsol_electron_thermal_wall_control",
        "wall_scope": "all_plasma_walls",
        "electron_reflection_coefficient": 0.0,
        "electron_wall_migration": False,
        "secondary_emission_coefficient": 0.0,
        "electron_energy_wall_coupling": False,
        "O_sticking_coefficient": frozen["O_sticking_coefficient"],
        "O2s_sticking_coefficient": frozen["O2s_sticking_coefficient"],
        "Os_sticking_coefficient": frozen["Os_sticking_coefficient"],
        "O2p_sticking_coefficient": frozen["O2p_sticking_coefficient"],
        "Om_sticking_coefficient": frozen["Om_sticking_coefficient"],
        "Op_sticking_coefficient": frozen["Op_sticking_coefficient"],
    }


def _build_a8_case_input(
    base_text: str,
    *,
    parameters: Mapping[str, Any],
    mode: str,
) -> tuple[str, dict[str, Any]]:
    if mode not in CASE_MODES:
        raise Issue27SEEError(f"unsupported A8 mode {mode!r}")
    frozen = _validated_parameters(parameters)

    # Always start from the accepted A7 combined case: heavy wall chemistry,
    # positive/negative ion wall migration, and electron thermal wall loss ON.
    text, a7_meta = _build_a7_case_input(
        base_text,
        parameters=_a7_parameters(parameters),
        mode="combined_thermal",
    )
    n_ref = float(a7_meta["electron_reference_density_m3"])
    gamma = float(frozen["O2p_secondary_emission_coefficient"])
    see_on = mode == "see_on"

    for path in (
        f"FunctorMaterials/{SEE_MATERIAL}",
        f"FVBCs/{SEE_BC}",
        f"Postprocessors/{SEE_PP}",
        f"Postprocessors/{SEE_ENERGY_PP}",
    ):
        mb.require_absent(text, path)

    # COMSOL wall theory: Gamma_e,SEE = sum_i gamma_i (Gamma_i . n).
    # The accepted QPX ion wall object exposes outward-positive surface and
    # one-sided migration mass fluxes. Convert O2+/O+ mass flux to particle flux,
    # apply gamma=0.05, and normalize by n_ref for the n_hat equation.
    expression = (
        f"{gamma:.17g}*{AVOGADRO:.17g}/{n_ref:.17g}*("
        f"(o2ps+o2pm)/{M_O2_KG_PER_MOL:.17g}+"
        f"(ops+opm)/{M_O_KG_PER_MOL:.17g})"
    )
    wall_list = "'" + " ".join(PLASMA_WALLS) + "'"
    text = mb.insert_child_block(
        text,
        "FunctorMaterials",
        f"""  [{SEE_MATERIAL}]
    type = ADParsedFunctorMaterial
    property_name = {SEE_FUNCTOR}
    functor_names = 'ion_surface_mass_flux_O2p ion_migration_mass_flux_O2p ion_surface_mass_flux_Op ion_migration_mass_flux_Op'
    functor_symbols = 'o2ps o2pm ops opm'
    expression = '{expression}'
    block = plasma
  []""",
    )
    text = mb.insert_child_block(
        text,
        "FVBCs",
        f"""  [{SEE_BC}]
    type = FVFunctorNeumannBC
    variable = n_e
    boundary = {wall_list}
    functor = {SEE_FUNCTOR}
    factor = {1.0 if see_on else 0.0:.17g}
  []""",
    )
    text = mb.insert_child_block(
        text,
        "Postprocessors",
        f"""  [{SEE_PP}]
    type = SideFVFluxBCIntegral
    boundary = {wall_list}
    fvbcs = '{SEE_BC}'
    execute_on = 'INITIAL TIMESTEP_END'
  []""",
    )
    energy_scale = n_ref * ELEMENTARY_CHARGE_C * float(
        frozen["secondary_electron_mean_energy_eV"]
    )
    text = mb.insert_child_block(
        text,
        "Postprocessors",
        f"""  [{SEE_ENERGY_PP}]
    type = ScalePostprocessor
    value = {SEE_PP}
    scaling_factor = {energy_scale:.17g}
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

    return text, {
        "issue": 27,
        "experiment": "A8_FINITE_SEE_PARTICLE_AND_ENERGY_LEDGER",
        "mode": mode,
        "a7_construction": a7_meta,
        "validated_parameters": frozen,
        "electron_reference_density_m3": n_ref,
        "see_enabled": see_on,
        "see_particle_contract": (
            "Gamma_e,SEE = 0.05*(Gamma_O2p,out + Gamma_Op,out), using each "
            "positive ion's accepted surface + one-sided migration wall flux"
        ),
        "see_sign_contract": (
            "emitted electron flux is physically inward; positive SEE functor uses "
            "FVFunctorNeumannBC factor=+1 in the normalized n_hat equation"
        ),
        "see_energy_contract": (
            "P_SEE = Gamma_e,SEE * e * 4 eV-equivalent-volts; runtime ledger only"
        ),
        "secondary_electron_mean_energy_eV": float(
            frozen["secondary_electron_mean_energy_eV"]
        ),
        "electron_energy_equation_coupled": False,
        "electron_energy_handoff": (
            "#26 must connect this validated 4 eV SEE energy flux to the solved "
            "electron-energy boundary equation without redefining gamma or mean energy"
        ),
        "a8_discriminator_timestep_s": A7_DISCRIMINATOR_DT_S,
    }


def _stage_case(
    target: Path,
    *,
    parameters: Mapping[str, Any],
    mode: str,
) -> dict[str, Any]:
    base = (SOURCE / "heavy_base.i").read_text(encoding="utf-8")
    input_text, meta = _build_a8_case_input(base, parameters=parameters, mode=mode)
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
    return {"source": str(SOURCE.resolve()), "staging": staging, "construction": meta}


def _required_columns() -> tuple[str, ...]:
    names = [
        "time",
        THERMAL_PP,
        SEE_PP,
        SEE_ENERGY_PP,
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


def _read_state(csv_path: Path) -> dict[str, Any]:
    if not csv_path.is_file():
        return {"status": "MISSING", "error": f"missing {csv_path.name}"}
    with csv_path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) < 2:
        return {"status": "MISSING", "error": "need INITIAL and TIMESTEP_END rows"}
    required = _required_columns()
    for label, row in (("initial", rows[0]), ("final", rows[-1])):
        missing = [name for name in required if name not in row]
        if missing:
            return {"status": "MISSING", "error": f"{label} missing CSV columns: {missing}"}
    try:
        initial = {name: float(rows[0][name]) for name in required}
        final = {name: float(rows[-1][name]) for name in required}
    except (TypeError, ValueError) as exc:
        return {"status": "INVALID", "error": str(exc)}
    if not all(math.isfinite(value) for value in (*initial.values(), *final.values())):
        return {"status": "INVALID", "error": "non-finite state value"}
    return {"status": "MEASURED", "initial": initial, "final": final}


def _physical_rate(value: float) -> float:
    return abs(float(value))


def _species_wall_mass_rate(state: Mapping[str, Any], species: str) -> float:
    total = 0.0
    for wall in PLASMA_WALLS:
        _, _, surface_pp, migration_pp = _charged_names(species, wall)
        total += _physical_rate(float(state[surface_pp]))
        total += _physical_rate(float(state[migration_pp]))
    return total


def _positive_ion_particle_rate(state: Mapping[str, Any]) -> float:
    return AVOGADRO * (
        _species_wall_mass_rate(state, "O2p") / M_O2_KG_PER_MOL
        + _species_wall_mass_rate(state, "Op") / M_O_KG_PER_MOL
    )


def _heavy_charge_molar_rate(state: Mapping[str, Any]) -> float:
    return (
        _species_wall_mass_rate(state, "O2p") / M_O2_KG_PER_MOL
        + _species_wall_mass_rate(state, "Op") / M_O_KG_PER_MOL
        - _species_wall_mass_rate(state, "Om") / M_O_KG_PER_MOL
    )


def _rel_defect(measured: float, expected: float) -> float:
    return abs(measured - expected) / max(abs(expected), 1.0e-300)


def _case_evidence(
    state: Mapping[str, Any],
    *,
    n_ref_m3: float,
    gamma: float,
    energy_eV: float,
) -> dict[str, Any]:
    if state.get("status") != "MEASURED":
        return {"status": "MISSING", "error": "case state not measured"}
    initial = state["initial"]
    final = state["final"]
    dt = float(final["time"]) - float(initial["time"])
    if dt <= 0.0:
        return {"status": "INVALID", "error": f"non-positive dt={dt}"}

    thermal_rate_norm = _physical_rate(float(final[THERMAL_PP]))
    see_rate_norm = _physical_rate(float(final[SEE_PP]))
    thermal_loss = thermal_rate_norm * n_ref_m3 * dt
    see_gain = see_rate_norm * n_ref_m3 * dt
    expected_electron_delta = see_gain - thermal_loss
    measured_electron_delta = (
        float(final["n_e_inventory"]) - float(initial["n_e_inventory"])
    )

    positive_ion_rate = _positive_ion_particle_rate(final)
    expected_see_particle_rate = gamma * positive_ion_rate
    measured_see_particle_rate = see_rate_norm * n_ref_m3
    expected_see_energy_power = expected_see_particle_rate * ELEMENTARY_CHARGE_C * energy_eV
    measured_see_energy_power = _physical_rate(float(final[SEE_ENERGY_PP]))

    heavy_charge_delta = -FARADAY_C_PER_MOL * _heavy_charge_molar_rate(final) * dt
    electron_thermal_charge_delta = ELEMENTARY_CHARGE_C * thermal_loss
    electron_see_charge_delta = -ELEMENTARY_CHARGE_C * see_gain
    expected_charge_delta = (
        heavy_charge_delta + electron_thermal_charge_delta + electron_see_charge_delta
    )
    measured_charge_delta = (
        float(final["r31_charge_integral"]) - float(initial["r31_charge_integral"])
    )
    charge_scale = max(
        abs(heavy_charge_delta)
        + abs(electron_thermal_charge_delta)
        + abs(electron_see_charge_delta),
        1.0e-300,
    )
    gauss_residual_delta = (
        (float(final["r31_gauss_flux_charge"]) - float(final["r31_charge_integral"]))
        - (float(initial["r31_gauss_flux_charge"]) - float(initial["r31_charge_integral"]))
    )
    composition_error = max(
        abs(float(final["sum_w_min"]) - 1.0),
        abs(float(final["sum_w_max"]) - 1.0),
    )

    return {
        "status": "MEASURED",
        "dt_s": dt,
        "positive_ion_incident_particle_rate_s-1": positive_ion_rate,
        "expected_see_particle_rate_s-1": expected_see_particle_rate,
        "measured_see_particle_rate_s-1": measured_see_particle_rate,
        "see_particle_rate_relative_defect": _rel_defect(
            measured_see_particle_rate,
            expected_see_particle_rate,
        ) if expected_see_particle_rate != 0.0 else abs(measured_see_particle_rate),
        "secondary_electron_mean_energy_eV": energy_eV,
        "expected_see_energy_power_W": expected_see_energy_power,
        "measured_see_energy_power_W": measured_see_energy_power,
        "see_energy_power_relative_defect": _rel_defect(
            measured_see_energy_power,
            expected_see_energy_power,
        ) if expected_see_energy_power != 0.0 else abs(measured_see_energy_power),
        "thermal_electron_loss": thermal_loss,
        "see_electron_gain": see_gain,
        "expected_electron_inventory_delta": expected_electron_delta,
        "measured_electron_inventory_delta": measured_electron_delta,
        "electron_inventory_relative_defect": _rel_defect(
            measured_electron_delta,
            expected_electron_delta,
        ),
        "expected_heavy_charge_delta_C": heavy_charge_delta,
        "expected_electron_thermal_charge_delta_C": electron_thermal_charge_delta,
        "expected_electron_see_charge_delta_C": electron_see_charge_delta,
        "expected_net_charge_delta_C": expected_charge_delta,
        "measured_net_charge_delta_C": measured_charge_delta,
        "net_charge_abs_defect_over_current_scale": (
            abs(measured_charge_delta - expected_charge_delta) / charge_scale
        ),
        "gauss_residual_delta_C": gauss_residual_delta,
        "composition_max_abs_error": composition_error,
        "nonnegative_electron_density": float(final["n_e_min"]) >= -1.0e-12,
    }


def run_finite_see_control(
    *,
    qpx: str | Path | None,
    results_root: Path,
    timeout: float,
    parameters: Mapping[str, Any],
) -> int:
    if timeout <= 0.0:
        raise Issue27SEEError("timeout must be positive")
    exe = resolve_executable(qpx)
    validate_executable(exe)
    frozen = _validated_parameters(parameters)

    stamp = utc_timestamp().replace(":", "").replace("-", "")
    root = create_collision_safe_directory(
        results_root,
        f"issue27_a8_r4_qf1_finite_see_{stamp}",
    )
    cases_root = root / "cases"
    logs = root / "logs"
    cases_root.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)

    staged: dict[str, Any] = {}
    for mode in CASE_MODES:
        staged[mode] = _stage_case(cases_root / mode, parameters=parameters, mode=mode)
    n_ref = float(staged["see_off"]["construction"]["electron_reference_density_m3"])

    summary: dict[str, Any] = {
        "issue": 27,
        "experiment": "A8_finite_see_particle_and_energy_ledger",
        "scientific_scope": (
            "COMSOL oxygen-ICP finite SEE from O2+/O+ with gamma=0.05, actual "
            "electron particle source coupling, and 4 eV secondary-electron energy "
            "flux ledger; solved electron-energy equation remains deferred to #26"
        ),
        "repository_head": issue91_run._repo_head(),
        "qpx_realpath": str(exe.resolve()),
        "qpx_sha256": issue91_run._sha256(exe),
        "parameters": frozen,
        "staged": staged,
        "p2": {},
        "cases": {},
        "evidence": {},
        "status": "NOT_RUN",
    }

    for mode in CASE_MODES:
        p2 = q0_run._p2(exe, cases_root / mode, logs / f"a8_{mode}_p2.log", timeout)
        summary["p2"][mode] = p2
        if p2["returncode"] != 0:
            summary["status"] = f"A8_P2_FAIL_{mode.upper()}"
            write_json_bundle(root, {"summary": ("summary.json", summary)})
            print(f"ISSUE27_A8_STATUS: {summary['status']}")
            print(f"EVIDENCE_DIR: {root}")
            return 2

    for mode in CASE_MODES:
        case_dir = cases_root / mode
        runtime = q0_run._runtime(
            exe,
            case_dir,
            logs / f"a8_{mode}_runtime.log",
            timeout,
        )
        state = _read_state(case_dir / "input_out.csv")
        active_gamma = (
            float(frozen["O2p_secondary_emission_coefficient"]) if mode == "see_on" else 0.0
        )
        evidence = _case_evidence(
            state,
            n_ref_m3=n_ref,
            gamma=active_gamma,
            energy_eV=float(frozen["secondary_electron_mean_energy_eV"]),
        )
        summary["cases"][mode] = {"runtime": runtime, "state": state}
        summary["evidence"][mode] = evidence
        if runtime["returncode"] != 0:
            summary["status"] = f"A8_RUNTIME_FAIL_{mode.upper()}"
            write_json_bundle(root, {"summary": ("summary.json", summary)})
            print(f"ISSUE27_A8_STATUS: {summary['status']}")
            print(f"EVIDENCE_DIR: {root}")
            return 1

    measured = all(
        summary["evidence"][mode].get("status") == "MEASURED" for mode in CASE_MODES
    )
    summary["status"] = (
        "A8_FINITE_SEE_EVIDENCE_READY_NOT_ACCEPTED" if measured else "A8_EVIDENCE_MISSING"
    )
    summary["scientific_acceptance"] = "UNSET_EVIDENCE_ONLY"
    summary["acceptance_contract"] = (
        "SEE_ON must emit 0.05 electrons per incident O2+/O+ ion using the accepted "
        "surface+migration ion wall flux, close the electron inventory and charge/Gauss "
        "ledger, and carry a 4 eV-per-emitted-electron energy flux. SEE_OFF must report "
        "zero SEE particle/energy flux. This stage validates the energy flux contract, "
        "not a solved electron-energy state."
    )
    write_json_bundle(root, {"summary": ("summary.json", summary)})

    print(f"ISSUE27_A8_STATUS: {summary['status']}")
    if measured:
        for mode in CASE_MODES:
            item = summary["evidence"][mode]
            print(f"{mode.upper()}_SEE_PARTICLE_DEFECT: {item['see_particle_rate_relative_defect']}")
            print(f"{mode.upper()}_SEE_ENERGY_DEFECT: {item['see_energy_power_relative_defect']}")
            print(f"{mode.upper()}_ELECTRON_INVENTORY_DEFECT: {item['electron_inventory_relative_defect']}")
            print(
                f"{mode.upper()}_NET_CHARGE_DEFECT_OVER_CURRENT_SCALE: "
                f"{item['net_charge_abs_defect_over_current_scale']}"
            )
    print(f"EVIDENCE_DIR: {root}")
    return 0 if measured else 1


__all__ = [
    "CASE_MODES",
    "SEE_BC",
    "SEE_ENERGY_PP",
    "SEE_FUNCTOR",
    "SEE_MATERIAL",
    "SEE_PP",
    "Issue27SEEError",
    "_build_a8_case_input",
    "_validated_parameters",
    "run_finite_see_control",
]
