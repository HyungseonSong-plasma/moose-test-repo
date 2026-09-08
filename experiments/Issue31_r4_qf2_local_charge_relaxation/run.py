#!/usr/bin/env python3
"""Run Issue #31 R4-QF2 local-charge relaxation discriminator."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

from experiments.Issue31_r4_q0_all_ground import run as q0_run
from experiments.Issue31_r4_qf1_closed_feedback import run as qf1_run
from experiments.Issue31_r4_qn0_all_ground import run as qn0_run
from experiments.Issue91_real_qvt_r3 import run as issue91_run
from qpx_harness.evidence import create_collision_safe_directory, sha256_file, utc_timestamp, write_json_bundle
from qpx_harness.execution.cases import stage_case
from qpx_harness.execution.runtime import resolve_executable, validate_executable
from qpx_harness.provenance import ArtifactRef, FileIdentity, RunEnvelope, write_run_envelope
from experiments.historical_recipe_support.issue31_r4_qf2 import (
    QF2_CHARGE_MAX_PP,
    QF2_CHARGE_MIN_PP,
    build_r4_qf2_input,
)

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "experiments" / "Issue91_real_qvt_r3" / "r3_e0"
ELEMENTARY_CHARGE = 1.602176634e-19
PROTOCOL_ID = "r4-qf2-local-charge-relaxation"

# Predeclared bounded scientific gates for the final R4 discriminator.
MAX_INITIAL_GLOBAL_CARRIER_SCALED_CHARGE = 1.0e-6
MIN_INITIAL_LOCAL_CHARGE_DENSITY_C_PER_M3 = 1.0e-8
MAX_LOCAL_CHARGE_RELAXATION_RATIO = 0.5
MAX_GAUSS_RELATIVE_DEFECT = 1.0e-3
MAX_C2_CARRIER_SCALED_DEFECT = 1.0e-10


def _stage(target: Path) -> dict[str, Any]:
    base = (SOURCE / "heavy_base.i").read_text()
    input_text, meta = build_r4_qf2_input(base)
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

    reference = float(meta["electron_reference_density_m3"])
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


def _local_relaxation_evidence(
    csv_path: Path,
    *,
    electron_reference_m3: float,
    phi_abs_max_V: float,
) -> dict[str, Any]:
    if not csv_path.is_file():
        return {"status": "MISSING", "error": f"missing {csv_path.name}"}
    with csv_path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) < 2:
        return {"status": "MISSING", "error": "need initial and final CSV rows"}

    first = rows[0]
    final = rows[-1]
    required = (
        "time",
        "domain_volume",
        "r31_charge_integral",
        QF2_CHARGE_MIN_PP,
        QF2_CHARGE_MAX_PP,
        "n_e_min",
        "n_e_max",
        "n_e_avg",
    )
    missing = [name for name in required if name not in final or name not in first]
    if missing:
        return {"status": "MISSING", "error": f"missing QF2 columns: {missing}"}

    try:
        volume = float(final["domain_volume"])
        q_initial = float(first["r31_charge_integral"])
        charge_min_initial = float(first[QF2_CHARGE_MIN_PP])
        charge_max_initial = float(first[QF2_CHARGE_MAX_PP])
        charge_min_final = float(final[QF2_CHARGE_MIN_PP])
        charge_max_final = float(final[QF2_CHARGE_MAX_PP])
        ne_min_initial = float(first["n_e_min"])
        ne_max_initial = float(first["n_e_max"])
        ne_avg_initial = float(first["n_e_avg"])
        ne_min_final = float(final["n_e_min"])
        ne_max_final = float(final["n_e_max"])
        ne_avg_final = float(final["n_e_avg"])
    except (TypeError, ValueError) as exc:
        return {"status": "INVALID", "error": str(exc)}

    values = (
        volume,
        q_initial,
        charge_min_initial,
        charge_max_initial,
        charge_min_final,
        charge_max_final,
        ne_min_initial,
        ne_max_initial,
        ne_avg_initial,
        ne_min_final,
        ne_max_final,
        ne_avg_final,
        phi_abs_max_V,
    )
    if not all(math.isfinite(value) for value in values):
        return {"status": "INVALID", "error": "non-finite QF2 relaxation scalar"}
    if volume <= 0.0 or electron_reference_m3 <= 0.0:
        return {"status": "INVALID", "error": "non-positive volume/reference density"}

    local_initial = max(abs(charge_min_initial), abs(charge_max_initial))
    local_final = max(abs(charge_min_final), abs(charge_max_final))
    relaxation_ratio = local_final / max(local_initial, 1.0e-300)
    carrier_charge_scale = ELEMENTARY_CHARGE * electron_reference_m3 * volume
    global_initial_scaled = abs(q_initial) / max(carrier_charge_scale, 1.0e-300)
    initial_ne_mean_rel = abs(ne_avg_initial - electron_reference_m3) / electron_reference_m3
    initial_ne_peak_rel = max(
        abs(ne_min_initial / electron_reference_m3 - 1.0),
        abs(ne_max_initial / electron_reference_m3 - 1.0),
    )
    final_ne_peak_rel = max(
        abs(ne_min_final / electron_reference_m3 - 1.0),
        abs(ne_max_final / electron_reference_m3 - 1.0),
    )

    gates = {
        "initial_local_charge_present": (
            local_initial >= MIN_INITIAL_LOCAL_CHARGE_DENSITY_C_PER_M3
        ),
        "initial_global_charge_near_neutral": (
            global_initial_scaled <= MAX_INITIAL_GLOBAL_CARRIER_SCALED_CHARGE
        ),
        "local_charge_relaxes": relaxation_ratio <= MAX_LOCAL_CHARGE_RELAXATION_RATIO,
    }

    return {
        "status": "MEASURED",
        "initial_volume_charge_C": q_initial,
        "carrier_charge_scale_C": carrier_charge_scale,
        "initial_global_carrier_scaled_charge": global_initial_scaled,
        "initial_charge_density_min_C_per_m3": charge_min_initial,
        "initial_charge_density_max_C_per_m3": charge_max_initial,
        "initial_local_charge_density_amplitude_C_per_m3": local_initial,
        "final_charge_density_min_C_per_m3": charge_min_final,
        "final_charge_density_max_C_per_m3": charge_max_final,
        "final_local_charge_density_amplitude_C_per_m3": local_final,
        "local_charge_relaxation_ratio": relaxation_ratio,
        "initial_n_e_min_m3": ne_min_initial,
        "initial_n_e_max_m3": ne_max_initial,
        "initial_n_e_avg_m3": ne_avg_initial,
        "initial_n_e_mean_relative_offset": initial_ne_mean_rel,
        "initial_n_e_peak_relative_perturbation": initial_ne_peak_rel,
        "final_n_e_min_m3": ne_min_final,
        "final_n_e_max_m3": ne_max_final,
        "final_n_e_avg_m3": ne_avg_final,
        "final_n_e_peak_relative_departure": final_ne_peak_rel,
        "final_phi_abs_max_V": phi_abs_max_V,
        "gates": gates,
        "pass": all(gates.values()),
    }


def _persist_run_artifacts(root: Path, summary: dict[str, Any], exe: Path, case_dir: Path) -> None:
    write_json_bundle(root, {"summary": ("summary.json", summary)})

    artifacts: list[ArtifactRef] = [ArtifactRef(kind="protocol", path="summary.json")]
    logs_dir = root / "logs"
    for log in sorted(logs_dir.glob("*.log")):
        artifacts.append(ArtifactRef(kind="execution", path=str(log.relative_to(root))))
    for evidence_path in (case_dir / "input_out.csv", case_dir / "input_out.physical.csv"):
        if evidence_path.is_file():
            artifacts.append(ArtifactRef(kind="evidence", path=str(evidence_path.relative_to(root))))

    input_path = case_dir / "input.i"
    input_identity = (
        FileIdentity(path=str(input_path.relative_to(root)), sha256=sha256_file(input_path))
        if input_path.is_file()
        else None
    )
    envelope = RunEnvelope(
        run_id=root.name,
        experiment_id=PROTOCOL_ID,
        protocol=PROTOCOL_ID,
        source_revision=str(summary.get("repository_head")) if summary.get("repository_head") else None,
        executable=FileIdentity(path=str(exe.resolve()), sha256=str(summary.get("qpx_sha256"))),
        input=input_identity,
        artifacts=tuple(artifacts),
    )
    write_run_envelope(root / "run_envelope.json", envelope)


def _print_terminal(root: Path, summary: dict[str, Any]) -> None:
    print(f"ISSUE31_R4_QF2_ROOT: {root}")
    print(f"ISSUE31_R4_QF2_STATUS: {summary['status']}")
    state = summary.get("state", {})
    relax = summary.get("local_charge_relaxation", {})
    gauss = summary.get("gauss_law", {})
    c2 = summary.get("c2_charge_conservation", {})
    if state.get("status") == "MEASURED":
        print(f"ISSUE31_R4_QF2_PHI_ABS_MAX_V: {state['phi_abs_max_V']:.17g}")
    if relax.get("status") == "MEASURED":
        print(
            "ISSUE31_R4_QF2_INITIAL_GLOBAL_CARRIER_SCALED_CHARGE: "
            f"{relax['initial_global_carrier_scaled_charge']:.17g}"
        )
        print(
            "ISSUE31_R4_QF2_LOCAL_CHARGE_RELAXATION_RATIO: "
            f"{relax['local_charge_relaxation_ratio']:.17g}"
        )
    if gauss.get("status") == "MEASURED":
        print(
            "ISSUE31_R4_QF2_GAUSS_RELATIVE_DEFECT: "
            f"{gauss['relative_defect']:.17g}"
        )
    if c2.get("status") == "MEASURED":
        print(
            "ISSUE31_R4_QF2_C2_CARRIER_SCALED_DEFECT: "
            f"{c2['carrier_scaled_defect']:.17g}"
        )
    print(f"ISSUE31_R4_QF2_SUMMARY: {root / 'summary.json'}")
    print(f"ISSUE31_R4_QF2_RUN_ENVELOPE: {root / 'run_envelope.json'}")


def run(args: argparse.Namespace) -> int:
    exe = resolve_executable(args.qpx)
    validate_executable(exe)
    stamp = utc_timestamp().replace(":", "").replace("-", "")
    root = create_collision_safe_directory(
        args.results_root,
        f"issue31_r4_qf2_local_charge_relaxation_{stamp}",
    )
    case_dir = root / "case"
    logs = root / "logs"
    logs.mkdir(parents=True, exist_ok=True)

    staged = _stage(case_dir)
    reference = float(staged["construction"]["electron_reference_density_m3"])
    summary: dict[str, Any] = {
        "issue": 31,
        "experiment": PROTOCOL_ID,
        "repository_head": issue91_run._repo_head(),
        "qpx_realpath": str(exe.resolve()),
        "qpx_sha256": issue91_run._sha256(exe),
        "phase": {
            "volume_charge": True,
            "poisson": True,
            "quasi_neutral_global_initialization": True,
            "local_charge_perturbation": True,
            "electrostatic_feedback": True,
            "surface_accumulated_charge": False,
            "volumetric_reactions": False,
            "secondary_emission": False,
            "all_ground_phi": True,
            "c1_gauss": True,
            "c2_global_charge": True,
        },
        "electron_reference_density_m3": reference,
        "scientific_gates": {
            "max_initial_global_carrier_scaled_charge": MAX_INITIAL_GLOBAL_CARRIER_SCALED_CHARGE,
            "min_initial_local_charge_density_C_per_m3": MIN_INITIAL_LOCAL_CHARGE_DENSITY_C_PER_M3,
            "max_local_charge_relaxation_ratio": MAX_LOCAL_CHARGE_RELAXATION_RATIO,
            "max_gauss_relative_defect": MAX_GAUSS_RELATIVE_DEFECT,
            "max_c2_carrier_scaled_defect": MAX_C2_CARRIER_SCALED_DEFECT,
        },
        "staged": staged,
        "p2": {},
        "runtime": {},
        "r3_invariants": {},
        "gauss_law": {},
        "state": {},
        "c2_charge_conservation": {},
        "local_charge_relaxation": {},
        "acceptance": {},
        "status": "NOT_RUN",
    }

    p2 = q0_run._p2(exe, case_dir, logs / "r4_qf2_p2.log", args.timeout)
    summary["p2"] = p2
    if p2["returncode"] != 0:
        summary["status"] = "P2_FAIL_R4_QF2"
        _persist_run_artifacts(root, summary, exe, case_dir)
        _print_terminal(root, summary)
        return 2

    runtime = q0_run._runtime(exe, case_dir, logs / "r4_qf2_runtime.log", args.timeout)
    summary["runtime"] = runtime
    if runtime["returncode"] != 0:
        summary["status"] = "R4_QF2_RUNTIME_FAIL"
        _persist_run_artifacts(root, summary, exe, case_dir)
        _print_terminal(root, summary)
        return 1

    invariants = issue91_run._checker(case_dir)
    summary["r3_invariants"] = invariants
    if invariants.get("pass") is not True:
        summary["status"] = "R4_QF2_R3_INVARIANT_FAIL"
        _persist_run_artifacts(root, summary, exe, case_dir)
        _print_terminal(root, summary)
        return 1

    physical = case_dir / "input_out.physical.csv"
    gauss = q0_run._gauss_evidence(physical)
    state = qn0_run._state_evidence(physical)
    c2 = qf1_run._c2_evidence(case_dir / "input_out.csv", reference)
    summary["gauss_law"] = gauss
    summary["state"] = state
    summary["c2_charge_conservation"] = c2

    if any(item.get("status") != "MEASURED" for item in (gauss, state, c2)):
        summary["status"] = "R4_QF2_CORE_EVIDENCE_MISSING"
        _persist_run_artifacts(root, summary, exe, case_dir)
        _print_terminal(root, summary)
        return 1

    relaxation = _local_relaxation_evidence(
        case_dir / "input_out.csv",
        electron_reference_m3=reference,
        phi_abs_max_V=float(state["phi_abs_max_V"]),
    )
    summary["local_charge_relaxation"] = relaxation
    if relaxation.get("status") != "MEASURED":
        summary["status"] = "R4_QF2_RELAXATION_EVIDENCE_MISSING"
        _persist_run_artifacts(root, summary, exe, case_dir)
        _print_terminal(root, summary)
        return 1

    acceptance = {
        "r3_invariants": invariants.get("pass") is True,
        "local_charge_discriminator": relaxation.get("pass") is True,
        "gauss_c1": gauss["relative_defect"] <= MAX_GAUSS_RELATIVE_DEFECT,
        "global_charge_c2": (
            c2["carrier_scaled_defect"] <= MAX_C2_CARRIER_SCALED_DEFECT
        ),
        "finite_nonnegative_phi_scale": (
            math.isfinite(float(state["phi_abs_max_V"]))
            and float(state["phi_abs_max_V"]) >= 0.0
        ),
    }
    summary["acceptance"] = acceptance
    summary["status"] = (
        "R4_QF2_PASS_READY_TO_CLOSE_R4"
        if all(acceptance.values())
        else "R4_QF2_EVIDENCE_READY_NOT_ACCEPTED"
    )
    _persist_run_artifacts(root, summary, exe, case_dir)
    _print_terminal(root, summary)
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
