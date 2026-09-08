#!/usr/bin/env python3
"""Issue #93 J2 one-shot real-QVT electron operator decomposition.

The batch preflights every diagnostic case at P2 before launching any P3 run.
Once P3 begins, the returned adaptive batch is one Issue #93 scientific EVR
(EVR2) regardless of how many predeclared subcases are needed before the first
failing owner is isolated.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from experiments.Issue2_electron_bulk_drift.check_case import evaluate
from experiments.Issue93_r3_electron_isolation.prepare import (
    DEFAULT_DT,
    ELECTRON_REFERENCE_CASE,
    EXPECTED_MESH_SHA256,
    SOURCE_CASE,
    PrepareError,
    _assignment,
    _sha256,
)
from experiments.Issue93_r3_electron_isolation.run import (
    DEFAULT_TIMEOUT,
    RunError,
    _electron_residuals,
    _resolve_qpx,
    _run,
    _tail,
)

CASE_ORDER = ("C0", "C1", "C2", "C3", "C4")
TIME_TOL = 1.0e-15
ISSUE93_ENTERING_EVR = 1

CASE_SPECS: dict[str, dict[str, Any]] = {
    "C0": {
        "label": "accepted_issue2_control",
        "field": "E=0.01 V/m",
        "operators": ("time", "diffusion", "drift"),
        "failure_decision": "E4_CURRENT_EXECUTABLE_CONTROL_REGRESSION_FAVORED",
    },
    "C1": {
        "label": "zero_field_time_only",
        "field": "E=0",
        "operators": ("time",),
        "failure_decision": "E3_TRANSIENT_OR_RUNTIME_REPRESENTATION_FAVORED",
    },
    "C2": {
        "label": "zero_field_time_plus_diffusion",
        "field": "E=0",
        "operators": ("time", "diffusion"),
        "failure_decision": "E2_DIFFUSION_OR_FV_BOUNDARY_PATH_FAVORED",
    },
    "C3": {
        "label": "zero_field_time_plus_drift",
        "field": "E=0",
        "operators": ("time", "drift"),
        "failure_decision": "E1_ZERO_FIELD_DRIFT_PATH_FAVORED",
    },
    "C4": {
        "label": "zero_field_full_electron_repeat",
        "field": "E=0",
        "operators": ("time", "diffusion", "drift"),
        "failure_decision": "E6_ELECTRON_OPERATOR_INTERACTION_FAVORED",
    },
}


class J2Error(RuntimeError):
    pass


def _replace_exact_once(text: str, old: str, new: str, claim: str) -> str:
    count = text.count(old)
    if count != 1:
        raise J2Error(f"{claim}: expected exactly one {old!r}, found {count}")
    return text.replace(old, new, 1)


def _remove_child_block(text: str, parent: str, child: str) -> str:
    """Remove one named child block from one top-level MOOSE input block."""
    lines = text.splitlines(keepends=True)
    parent_start: int | None = None
    parent_depth = 0
    child_start: int | None = None

    for i, raw in enumerate(lines):
        stripped = raw.strip()
        if parent_start is None:
            if stripped == f"[{parent}]":
                parent_start = i
                parent_depth = 1
            continue

        if stripped.startswith("[") and stripped.endswith("]"):
            if stripped == "[]":
                parent_depth -= 1
                if parent_depth == 0:
                    break
            else:
                if parent_depth == 1 and stripped == f"[{child}]":
                    child_start = i
                    break
                parent_depth += 1

    if child_start is None:
        raise J2Error(f"[{parent}] child [{child}] not found")

    local_depth = 1
    child_end: int | None = None
    for j in range(child_start + 1, len(lines)):
        stripped = lines[j].strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if stripped == "[]":
                local_depth -= 1
                if local_depth == 0:
                    child_end = j
                    break
            else:
                local_depth += 1
    if child_end is None:
        raise J2Error(f"unterminated [{parent}] child [{child}]")

    return "".join(lines[:child_start] + lines[child_end + 1 :])


def build_case_input(case_id: str, electron_reference_case: Path = ELECTRON_REFERENCE_CASE) -> str:
    if case_id not in CASE_SPECS:
        raise J2Error(f"unknown J2 case: {case_id}")
    reference = (electron_reference_case / "input.i").read_text()
    if abs(_assignment(reference, "dt") - DEFAULT_DT) > 1.0e-30:
        raise J2Error("accepted #2 control timestep changed unexpectedly")

    if case_id == "C0":
        return reference

    text = _replace_exact_once(
        reference,
        "expression = '-0.01*x'",
        "expression = '0.0*x'",
        f"{case_id} zero-field discriminator",
    )
    operators = set(CASE_SPECS[case_id]["operators"])
    if "diffusion" not in operators:
        text = _remove_child_block(text, "FVKernels", "diffusion")
    if "drift" not in operators:
        text = _remove_child_block(text, "FVKernels", "drift")

    marker = (
        f"# Issue #93 J2 {case_id}: {CASE_SPECS[case_id]['label']}\n"
        f"# Operators: {', '.join(CASE_SPECS[case_id]['operators'])}; E=0 diagnostic.\n"
    )
    return marker + text


def _reference_identity(
    source_case: Path = SOURCE_CASE,
    electron_reference_case: Path = ELECTRON_REFERENCE_CASE,
) -> dict[str, str]:
    source_case = source_case.resolve()
    electron_reference_case = electron_reference_case.resolve()
    for root, names in (
        (source_case, ("qvt.msh", "electron_moments.txt")),
        (electron_reference_case, ("input.i", "qvt.msh", "electron_moments.txt", "expected.json")),
    ):
        for name in names:
            if not (root / name).is_file():
                raise J2Error(f"missing J2 reference asset: {root / name}")

    ref_mesh = _sha256(electron_reference_case / "qvt.msh")
    r3_mesh = _sha256(source_case / "qvt.msh")
    if ref_mesh != r3_mesh or ref_mesh != EXPECTED_MESH_SHA256:
        raise J2Error(f"real-qvt mesh identity mismatch: #2={ref_mesh} #91={r3_mesh}")

    ref_table = _sha256(electron_reference_case / "electron_moments.txt")
    r3_table = _sha256(source_case / "electron_moments.txt")
    if ref_table != r3_table:
        raise J2Error(f"electron table identity mismatch: #2={ref_table} #91={r3_table}")

    return {
        "mesh_sha256": ref_mesh,
        "electron_table_sha256": ref_table,
        "reference_input_sha256": hashlib.sha256(
            (electron_reference_case / "input.i").read_bytes()
        ).hexdigest(),
        "expected_sha256": hashlib.sha256(
            (electron_reference_case / "expected.json").read_bytes()
        ).hexdigest(),
    }


def prepare_batch(
    root: Path,
    source_case: Path = SOURCE_CASE,
    electron_reference_case: Path = ELECTRON_REFERENCE_CASE,
) -> dict[str, Any]:
    root = root.resolve()
    source_case = source_case.resolve()
    electron_reference_case = electron_reference_case.resolve()
    identity = _reference_identity(source_case, electron_reference_case)
    reference = (electron_reference_case / "input.i").read_text()

    cases: dict[str, Any] = {}
    for case_id in CASE_ORDER:
        case_dir = root / "cases" / case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(electron_reference_case / "qvt.msh", case_dir / "qvt.msh")
        shutil.copy2(electron_reference_case / "electron_moments.txt", case_dir / "electron_moments.txt")
        shutil.copy2(electron_reference_case / "expected.json", case_dir / "expected.json")
        text = build_case_input(case_id, electron_reference_case)
        (case_dir / "input.i").write_text(text)
        cases[case_id] = {
            **CASE_SPECS[case_id],
            "case_dir": str(case_dir),
            "input_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "identical_to_control_input": text == reference,
        }

    manifest = {
        "issue": 93,
        "stage": "J2_OPERATOR_DECOMPOSITION_PREPARE",
        "qpx_executed": False,
        "scientific_evr_consumed": 0,
        "scientific_acceptance_eligible": False,
        "source_case": str(source_case),
        "electron_reference_case": str(electron_reference_case),
        "identity": identity,
        "cases": cases,
        "case_order": list(CASE_ORDER),
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def _check_accepted_qvt_csv(csv_path: Path, expected_path: Path) -> dict[str, Any]:
    if not csv_path.is_file():
        return {"pass": False, "error": f"CSV does not exist: {csv_path}"}
    try:
        with csv_path.open(newline="") as f:
            rows = list(csv.DictReader(f))
        physical = [r for r in rows if float(r.get("time", "nan")) > TIME_TOL]
        if not physical:
            return {"pass": False, "error": "CSV has no positive-time physical row"}
        expected = json.loads(expected_path.read_text())
        checks, diagnostics = evaluate(physical[-1], expected)
    except (OSError, ValueError, KeyError, SystemExit) as exc:
        return {"pass": False, "error": str(exc)}

    failed = [name for name, ok in checks if not ok]
    return {
        "pass": not failed,
        "failed": failed,
        "physical_rows": len(physical),
        "time_s": float(physical[-1]["time"]),
        "diagnostics": diagnostics,
        "contract": "ACCEPTED_ISSUE2_QVT_PREPOISSON",
    }


def classify_first_failure(case_id: str | None) -> tuple[str, dict[str, str]]:
    status = {
        "E1_ZERO_FIELD_DRIFT": "OPEN",
        "E2_DIFFUSION_OR_FV_BOUNDARY": "OPEN",
        "E3_TRANSIENT_OR_RUNTIME": "OPEN",
        "E4_CURRENT_EXECUTABLE_CONTROL": "OPEN",
        "E5_HEAVY_ELECTRON_COUPLING_NECESSARY": "DISFAVORED_BY_J1",
        "E6_ELECTRON_OPERATOR_INTERACTION": "OPEN",
    }
    if case_id is None:
        for key in ("E1_ZERO_FIELD_DRIFT", "E2_DIFFUSION_OR_FV_BOUNDARY", "E3_TRANSIENT_OR_RUNTIME", "E4_CURRENT_EXECUTABLE_CONTROL", "E6_ELECTRON_OPERATOR_INTERACTION"):
            status[key] = "DISFAVORED_FOR_J2_TESTED_CASES"
        return "J2_ALL_OPERATOR_CASES_SUPPORTED_J1_REPEATABILITY_HOLD", status

    decision = str(CASE_SPECS[case_id]["failure_decision"])
    if case_id == "C0":
        status["E4_CURRENT_EXECUTABLE_CONTROL"] = "FAVORED"
    elif case_id == "C1":
        status["E4_CURRENT_EXECUTABLE_CONTROL"] = "DISFAVORED"
        status["E3_TRANSIENT_OR_RUNTIME"] = "FAVORED"
    elif case_id == "C2":
        status["E4_CURRENT_EXECUTABLE_CONTROL"] = "DISFAVORED"
        status["E3_TRANSIENT_OR_RUNTIME"] = "DISFAVORED"
        status["E2_DIFFUSION_OR_FV_BOUNDARY"] = "FAVORED"
    elif case_id == "C3":
        status["E4_CURRENT_EXECUTABLE_CONTROL"] = "DISFAVORED"
        status["E3_TRANSIENT_OR_RUNTIME"] = "DISFAVORED"
        status["E2_DIFFUSION_OR_FV_BOUNDARY"] = "DISFAVORED"
        status["E1_ZERO_FIELD_DRIFT"] = "FAVORED"
    elif case_id == "C4":
        for key in ("E1_ZERO_FIELD_DRIFT", "E2_DIFFUSION_OR_FV_BOUNDARY", "E3_TRANSIENT_OR_RUNTIME", "E4_CURRENT_EXECUTABLE_CONTROL"):
            status[key] = "DISFAVORED"
        status["E6_ELECTRON_OPERATOR_INTERACTION"] = "FAVORED"
    return decision, status


def _write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")


def run(args: argparse.Namespace) -> int:
    qpx = _resolve_qpx(args.qpx)
    source = args.source_case.resolve()
    reference = args.electron_reference_case.resolve()
    root = args.work_dir.resolve() if args.work_dir else Path(tempfile.mkdtemp(prefix="issue93_j2_"))
    logs = root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    manifest = prepare_batch(root, source, reference)

    summary: dict[str, Any] = {
        "issue": 93,
        "stage": "J2_REAL_QVT_ELECTRON_OPERATOR_DECOMPOSITION",
        "artifact_root": str(root),
        "qpx": qpx,
        "manifest": manifest,
        "p2_preflight_complete": False,
        "cases": {},
        "selected_failure_case": None,
        "decision": "NOT_RUN",
        "hypotheses": {},
        "batch_scientific_evr_consumed": 0,
        "issue93_evr_total": ISSUE93_ENTERING_EVR,
        "scientific_acceptance_eligible": False,
    }

    # P2 every predeclared case before any P3 launch. A construction failure
    # therefore cannot consume the remaining scientific diagnostic budget.
    for case_id in CASE_ORDER:
        case_dir = Path(manifest["cases"][case_id]["case_dir"])
        p2 = _run(
            [qpx, "-i", "input.i", "--check-input"],
            case_dir,
            logs / f"{case_id.lower()}_p2.log",
            args.timeout,
        )
        summary["cases"][case_id] = {
            "spec": manifest["cases"][case_id],
            "p2": p2,
            "p2_log_tail": _tail(Path(p2["log"]).read_text()),
            "p3": None,
            "checker": None,
            "electron_residuals": [],
            "passed": None,
        }
        if p2["returncode"] != 0:
            summary["decision"] = f"J2_P2_CONSTRUCTION_OR_FRAMEWORK_CONTRACT_FAIL_{case_id}"
            _write_json(root / "summary.json", summary)
            print(f"ISSUE93_J2_P2: FAIL {case_id}")
            print(f"ISSUE93_J2_DECISION: {summary['decision']}")
            print("ISSUE93_J2_BATCH_EVR: 0")
            print(f"ISSUE93_EVR: {ISSUE93_ENTERING_EVR}")
            print("ISSUE93_J2_P2_LOG_TAIL_BEGIN")
            print(summary["cases"][case_id]["p2_log_tail"])
            print("ISSUE93_J2_P2_LOG_TAIL_END")
            print(f"ARTIFACT_ROOT: {root}")
            return 2

    summary["p2_preflight_complete"] = True

    failure: str | None = None
    for case_id in CASE_ORDER:
        case_dir = Path(manifest["cases"][case_id]["case_dir"])
        p3 = _run(
            [
                qpx,
                "-i",
                "input.i",
                "-snes_monitor",
                "-snes_converged_reason",
                "-ksp_converged_reason",
            ],
            case_dir,
            logs / f"{case_id.lower()}_runtime.log",
            args.timeout,
        )
        summary["batch_scientific_evr_consumed"] = 1
        summary["issue93_evr_total"] = ISSUE93_ENTERING_EVR + 1
        runtime_text = Path(p3["log"]).read_text()
        checker = _check_accepted_qvt_csv(case_dir / "input_out.csv", case_dir / "expected.json")
        passed = p3["returncode"] == 0 and checker.get("pass") is True
        summary["cases"][case_id].update(
            {
                "p3": p3,
                "runtime_log_tail": _tail(runtime_text),
                "checker": checker,
                "electron_residuals": _electron_residuals(runtime_text),
                "passed": passed,
            }
        )
        if not passed:
            failure = case_id
            break

    decision, hypotheses = classify_first_failure(failure)
    summary["selected_failure_case"] = failure
    summary["decision"] = decision
    summary["hypotheses"] = hypotheses
    _write_json(root / "summary.json", summary)

    print("ISSUE93_J2_P2: PASS ALL")
    for case_id in CASE_ORDER:
        case = summary["cases"].get(case_id)
        if not case or case.get("p3") is None:
            continue
        print(
            f"ISSUE93_J2_{case_id}: "
            f"{'PASS' if case['passed'] else 'FAIL'} "
            f"RC={case['p3']['returncode']} "
            f"RESIDUALS={case['electron_residuals']}"
        )
    print(f"ISSUE93_J2_SELECTED_CASE: {failure if failure is not None else 'NONE'}")
    print(f"ISSUE93_J2_DECISION: {decision}")
    print("ISSUE93_J2_BATCH_EVR: 1")
    print(f"ISSUE93_EVR: {ISSUE93_ENTERING_EVR + 1}")
    print("SCIENTIFIC_ACCEPTANCE_ELIGIBLE: false")
    if failure is not None:
        failing = summary["cases"][failure]
        print(f"ISSUE93_J2_CHECKER: {failing['checker']}")
        print("ISSUE93_J2_RUNTIME_LOG_TAIL_BEGIN")
        print(failing["runtime_log_tail"])
        print("ISSUE93_J2_RUNTIME_LOG_TAIL_END")
    print(f"ARTIFACT_ROOT: {root}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qpx", required=True)
    parser.add_argument("--source-case", type=Path, default=SOURCE_CASE)
    parser.add_argument("--electron-reference-case", type=Path, default=ELECTRON_REFERENCE_CASE)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    try:
        return run(args)
    except (J2Error, RunError, PrepareError, OSError, ValueError, KeyError) as exc:
        print(f"ISSUE93_J2_ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
