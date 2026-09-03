#!/usr/bin/env python3
"""Run Issue #31 R4-QF1 closed electrostatic feedback with C2 measurement."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

from experiments.Issue31_r4_q0_all_ground import run as q0_run
from experiments.Issue31_r4_qn0_all_ground import run as qn0_run
from experiments.Issue91_real_qvt_r3 import run as issue91_run
from qpx_harness.evidence import create_collision_safe_directory, utc_timestamp, write_json_bundle
from qpx_harness.execution.cases import stage_case
from qpx_harness.execution.runtime import resolve_executable, validate_executable
from qpx_harness.moose import parameters as mp
from recipes.issue31_r4_qf1 import CHARGED_HEAVY_C2, build_r4_qf1_input
from recipes.issue31_r4_qn0 import AVOGADRO

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "experiments" / "Issue91_real_qvt_r3" / "r3_e0"
ELEMENTARY_CHARGE = 1.602176634e-19


def _stage(target: Path) -> dict[str, Any]:
    base = (SOURCE / "heavy_base.i").read_text()
    input_text, meta = build_r4_qf1_input(base)

    # C2 must use the actual discretized initial volume charge, not the nominal
    # algebraic QN ledger. The accepted initial O FunctionIC is spatially
    # varying, which changes Mn_mix/rho and therefore the integrated heavy
    # charge even when the top-level reference ledger is quasi-neutral.
    input_text = mp.upsert_parameter(
        input_text,
        "Postprocessors/r31_charge_integral",
        "execute_on",
        "'INITIAL TIMESTEP_END'",
    )
    meta["c2_initial_charge_observable"] = {
        "postprocessor": "r31_charge_integral",
        "execute_on": ["INITIAL", "TIMESTEP_END"],
        "reason": (
            "measure the actual discretized t=0 volume charge after spatial ICs "
            "and material evaluation; do not substitute the nominal QN ledger"
        ),
    }

    staging = stage_case(
        SOURCE,
        target,
        input_text=input_text,
        purge_directory_names=(".jitcache", "checkpoint", "checkpoints"),
        purge_patterns=(
            "input_out*",
            "*.log",
            "*.e",
            "*.exo",
            "prepare_evidence.json",
        ),
    )

    reference = float(
        meta["predecessor"]["quasi_neutral_reference"]["electron_reference_density_m3"]
    )
    expected_path = target / "expected.json"
    expected = json.loads(expected_path.read_text())
    expected["field_strength"] = 0.0
    expected["n0"] = reference
    expected_path.write_text(json.dumps(expected, indent=2, sort_keys=True) + "\n")

    (target / "prepare_evidence.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True) + "\n"
    )
    return {
        "source": str(SOURCE.resolve()),
        "staging": staging,
        "construction": meta,
        "expected": expected,
    }


def _c2_evidence(csv_path: Path, electron_reference_m3: float) -> dict[str, Any]:
    """Measure one-step implicit-Euler global charge conservation.

    QF1 explicitly executes `r31_charge_integral` on INITIAL and TIMESTEP_END so
    C2 uses the actual discretized initial and final volume charges. This is
    required because the spatial neutral-species FunctionIC changes local
    mixture molar mass and density; the nominal top-level QN ledger is not a
    substitute for the integrated initial charge of the actual discretized
    state.

    Electrostatic drift/correction operators avoid every physical plasma
    boundary and the electron equation has no external boundary-current
    operator in this scope. Therefore the explicit external charge current is
    reconstructed from the charged-heavy inlet/outlet advective mass-flux
    postprocessors. For implicit Euler the one-step boundary contribution is
    dt*I_boundary(t_{n+1}).
    """
    if not csv_path.is_file():
        return {"status": "MISSING", "error": f"missing {csv_path.name}"}
    with csv_path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) < 2:
        return {"status": "MISSING", "error": "need initial and final CSV rows"}

    first = rows[0]
    final = rows[-1]
    required = ["time", "r31_charge_integral", "domain_volume"]
    for species in CHARGED_HEAVY_C2:
        required.extend((f"inlet_mdot_{species}", f"outlet_mdot_{species}"))
    missing_final = [name for name in required if name not in final]
    missing_initial = [name for name in ("time", "r31_charge_integral") if name not in first]
    if missing_final or missing_initial:
        return {
            "status": "MISSING",
            "error": (
                f"missing C2 columns: final={missing_final}, initial={missing_initial}"
            ),
        }

    try:
        time_initial = float(first["time"])
        time_final = float(final["time"])
        q_initial = float(first["r31_charge_integral"])
        q_final = float(final["r31_charge_integral"])
        volume = float(final["domain_volume"])
    except (TypeError, ValueError) as exc:
        return {"status": "INVALID", "error": str(exc)}
    if not all(math.isfinite(value) for value in (time_initial, time_final, q_initial, q_final, volume)):
        return {"status": "INVALID", "error": "non-finite C2 scalar"}
    dt = time_final - time_initial
    if dt <= 0.0 or volume <= 0.0:
        return {
            "status": "INVALID",
            "error": f"invalid dt/domain volume: dt={dt}, volume={volume}",
        }

    species_current: dict[str, Any] = {}
    total_boundary_current = 0.0
    for species, contract in CHARGED_HEAVY_C2.items():
        try:
            inlet_mdot = float(final[f"inlet_mdot_{species}"])
            outlet_mdot = float(final[f"outlet_mdot_{species}"])
        except (TypeError, ValueError) as exc:
            return {"status": "INVALID", "error": f"{species}: {exc}"}
        z = int(contract["z"])
        molar_mass = float(contract["molar_mass_kg_per_mol"])
        outward_mass_rate = outlet_mdot - inlet_mdot
        outward_number_rate = outward_mass_rate * AVOGADRO / molar_mass
        outward_charge_current = ELEMENTARY_CHARGE * z * outward_number_rate
        total_boundary_current += outward_charge_current
        species_current[species] = {
            "z": z,
            "molar_mass_kg_per_mol": molar_mass,
            "inlet_mdot_kg_per_s_positive_into_domain": inlet_mdot,
            "outlet_mdot_kg_per_s_positive_outward": outlet_mdot,
            "outward_mass_rate_kg_per_s": outward_mass_rate,
            "outward_number_rate_per_s": outward_number_rate,
            "outward_charge_current_C_per_s": outward_charge_current,
        }

    delta_q = q_final - q_initial
    q_boundary = dt * total_boundary_current
    residual = delta_q + q_boundary
    component_scale = max(abs(delta_q), abs(q_boundary), 1.0e-300)
    carrier_charge_scale = max(
        ELEMENTARY_CHARGE * electron_reference_m3 * volume,
        1.0e-300,
    )
    return {
        "status": "MEASURED",
        "time_initial": time_initial,
        "time_final": time_final,
        "dt_s": dt,
        "initial_volume_charge_C": q_initial,
        "initial_charge_source": "r31_charge_integral evaluated on INITIAL",
        "final_volume_charge_C": q_final,
        "Delta_Q_C": delta_q,
        "species_boundary_current": species_current,
        "electron_boundary_current_C_per_s": 0.0,
        "electron_boundary_current_policy": (
            "no external electron flux operator in QF1; electron drift avoids all "
            "physical plasma boundaries and diffusion retains natural zero-flux BC"
        ),
        "total_outward_boundary_current_C_per_s": total_boundary_current,
        "Q_boundary_C": q_boundary,
        "R_Q_C": residual,
        "component_relative_defect": abs(residual) / component_scale,
        "carrier_charge_scale_C": carrier_charge_scale,
        "carrier_scaled_defect": abs(residual) / carrier_charge_scale,
        "time_discretization": "implicit Euler final-state boundary current",
        "sign_convention": "Delta_Q + Q_boundary(outward positive) = 0",
        "acceptance": "UNSET_FIRST_CLOSED_FEEDBACK_MEASUREMENT",
    }


def run(args: argparse.Namespace) -> int:
    exe = resolve_executable(args.qpx)
    validate_executable(exe)
    stamp = utc_timestamp().replace(":", "").replace("-", "")
    root = create_collision_safe_directory(
        args.results_root,
        f"issue31_r4_qf1_closed_feedback_{stamp}",
    )
    case_dir = root / "case"
    logs = root / "logs"
    logs.mkdir(parents=True, exist_ok=True)

    staged = _stage(case_dir)
    reference = float(
        staged["construction"]["predecessor"]["quasi_neutral_reference"][
            "electron_reference_density_m3"
        ]
    )
    summary: dict[str, Any] = {
        "issue": 31,
        "experiment": "r4-qf1-all-ground-closed-electrostatic-feedback",
        "repository_head": issue91_run._repo_head(),
        "qpx_realpath": str(exe.resolve()),
        "qpx_sha256": issue91_run._sha256(exe),
        "phase": {
            "volume_charge": True,
            "poisson": True,
            "quasi_neutral_initialization": True,
            "electrostatic_feedback": True,
            "surface_accumulated_charge": False,
            "volumetric_reactions": False,
            "secondary_emission": False,
            "all_ground_phi": True,
            "c2_global_charge": True,
        },
        "electron_reference_density_m3": reference,
        "staged": staged,
        "p2": {},
        "runtime": {},
        "r3_invariants": {},
        "gauss_law": {},
        "state": {},
        "c2_charge_conservation": {},
        "status": "NOT_RUN",
    }

    p2 = q0_run._p2(exe, case_dir, logs / "r4_qf1_p2.log", args.timeout)
    summary["p2"] = p2
    if p2["returncode"] != 0:
        summary["status"] = "P2_FAIL_R4_QF1"
        write_json_bundle(root, {"summary": ("summary.json", summary)})
        print(f"ISSUE31_R4_QF1_ROOT: {root}")
        print(f"ISSUE31_R4_QF1_STATUS: {summary['status']}")
        return 2

    runtime = q0_run._runtime(exe, case_dir, logs / "r4_qf1_runtime.log", args.timeout)
    summary["runtime"] = runtime
    if runtime["returncode"] != 0:
        summary["status"] = "R4_QF1_RUNTIME_FAIL"
        write_json_bundle(root, {"summary": ("summary.json", summary)})
        print(f"ISSUE31_R4_QF1_ROOT: {root}")
        print(f"ISSUE31_R4_QF1_STATUS: {summary['status']}")
        return 1

    invariants = issue91_run._checker(case_dir)
    summary["r3_invariants"] = invariants
    if invariants.get("pass") is not True:
        summary["status"] = "R4_QF1_R3_INVARIANT_FAIL"
        write_json_bundle(root, {"summary": ("summary.json", summary)})
        print(f"ISSUE31_R4_QF1_ROOT: {root}")
        print(f"ISSUE31_R4_QF1_STATUS: {summary['status']}")
        return 1

    physical = case_dir / "input_out.physical.csv"
    gauss = q0_run._gauss_evidence(physical)
    summary["gauss_law"] = gauss
    if gauss.get("status") != "MEASURED":
        summary["status"] = "R4_QF1_GAUSS_EVIDENCE_MISSING"
        write_json_bundle(root, {"summary": ("summary.json", summary)})
        print(f"ISSUE31_R4_QF1_ROOT: {root}")
        print(f"ISSUE31_R4_QF1_STATUS: {summary['status']}")
        return 1

    state = qn0_run._state_evidence(physical)
    summary["state"] = state
    if state.get("status") != "MEASURED":
        summary["status"] = "R4_QF1_STATE_EVIDENCE_MISSING"
        write_json_bundle(root, {"summary": ("summary.json", summary)})
        print(f"ISSUE31_R4_QF1_ROOT: {root}")
        print(f"ISSUE31_R4_QF1_STATUS: {summary['status']}")
        return 1

    c2 = _c2_evidence(case_dir / "input_out.csv", reference)
    summary["c2_charge_conservation"] = c2
    if c2.get("status") != "MEASURED":
        summary["status"] = "R4_QF1_C2_EVIDENCE_MISSING"
        write_json_bundle(root, {"summary": ("summary.json", summary)})
        print(f"ISSUE31_R4_QF1_ROOT: {root}")
        print(f"ISSUE31_R4_QF1_STATUS: {summary['status']}")
        return 1

    # First closed-feedback runtime is evidence collection, not automatic
    # scientific acceptance. Interpret nonlinear behavior, field magnitude,
    # C1 and C2 together before freezing any threshold or architecture choice.
    summary["status"] = "R4_QF1_EVIDENCE_READY"
    write_json_bundle(root, {"summary": ("summary.json", summary)})
    print(f"ISSUE31_R4_QF1_ROOT: {root}")
    print(f"ISSUE31_R4_QF1_STATUS: {summary['status']}")
    print(f"ISSUE31_R4_QF1_PHI_ABS_MAX_V: {state['phi_abs_max_V']:.17g}")
    print(f"ISSUE31_R4_QF1_VOLUME_CHARGE_C: {state['volume_charge_C']:.17g}")
    print(f"ISSUE31_R4_QF1_GAUSS_RELATIVE_DEFECT: {gauss['relative_defect']:.17g}")
    print(f"ISSUE31_R4_QF1_C2_RQ_C: {c2['R_Q_C']:.17g}")
    print(
        "ISSUE31_R4_QF1_C2_CARRIER_SCALED_DEFECT: "
        f"{c2['carrier_scaled_defect']:.17g}"
    )
    print(f"ISSUE31_R4_QF1_SUMMARY: {root / 'summary.json'}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qpx", required=True)
    parser.add_argument("--results-root", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
