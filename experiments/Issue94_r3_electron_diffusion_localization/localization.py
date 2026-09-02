#!/usr/bin/env python3
"""Issue #94: constant-state electron diffusion residual localization.

The governed batch preflights L0-L3 before any scientific runtime. Once P3
starts, L0->L3 runs adaptively and stops at the first failing residual owner.
No Jacobian sweep or surface-reaction physics is included in this batch.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import tempfile
from pathlib import Path
from typing import Any

from experiments.Issue93_r3_electron_isolation.operator_decomposition import (
    _check_accepted_qvt_csv,
    _reference_identity,
    _replace_exact_once,
    build_case_input,
)
from experiments.Issue93_r3_electron_isolation.prepare import (
    ELECTRON_REFERENCE_CASE,
    SOURCE_CASE,
)
from experiments.Issue93_r3_electron_isolation.run import (
    DEFAULT_TIMEOUT,
    RunError,
    _electron_residuals,
    _resolve_qpx,
    _run,
    _tail,
)

CASE_ORDER = ("L0", "L1", "L2", "L3")
ISSUE94_ENTERING_EVR = 0
KB = 1.380649e-23
FROZEN_DIFFUSION = 41257.29899041419
FROZEN_MOBILITY = 9755.114369721427

_DIFFUSION_COEFF_LINE = "    coeff = electron_diffusion\n"
_QPX_TRANSPORT_BLOCK = """  [electron_transport]
    type = QPXElectronTransportLookupMaterial
    property_table_file = electron_moments.txt
    mean_energy = mean_en
    pressure = p_abs
    gas_temperature = T_g
    bounds_policy = error
    block = plasma
  []
"""


class Issue94Error(RuntimeError):
    pass


def frozen_transport_values(
    electron_reference_case: Path = ELECTRON_REFERENCE_CASE,
) -> dict[str, float]:
    expected = json.loads((electron_reference_case / "expected.json").read_text())
    neutral = float(expected["p"]) / (KB * float(expected["T"]))
    diffusion = float(expected["DN"]) / neutral
    mobility = float(expected["muN"]) / neutral
    if not math.isclose(diffusion, FROZEN_DIFFUSION, rel_tol=1.0e-14, abs_tol=0.0):
        raise Issue94Error(
            f"frozen diffusion changed: expected {FROZEN_DIFFUSION}, derived {diffusion}"
        )
    if not math.isclose(mobility, FROZEN_MOBILITY, rel_tol=1.0e-14, abs_tol=0.0):
        raise Issue94Error(
            f"frozen mobility changed: expected {FROZEN_MOBILITY}, derived {mobility}"
        )
    return {
        "neutral_number_density": neutral,
        "electron_diffusion": diffusion,
        "electron_mobility": mobility,
    }


def build_localization_input(
    case_id: str,
    electron_reference_case: Path = ELECTRON_REFERENCE_CASE,
) -> str:
    """Construct one localization case from accepted Issue #93 J2 derivatives."""
    if case_id not in CASE_ORDER:
        raise Issue94Error(f"unknown Issue94 case: {case_id}")

    if case_id == "L0":
        return build_case_input("C1", electron_reference_case)
    if case_id == "L3":
        return build_case_input("C2", electron_reference_case)

    values = frozen_transport_values(electron_reference_case)
    c2 = build_case_input("C2", electron_reference_case)

    if case_id == "L1":
        literal = repr(values["electron_diffusion"])
        candidate = _replace_exact_once(
            c2,
            _DIFFUSION_COEFF_LINE,
            f"    coeff = {literal}\n",
            "Issue94 L1 literal FVDiffusion coefficient",
        )
        return (
            "# Issue #94 L1: exact J2 C2 with only FVDiffusion coeff routed "
            "directly to the frozen numeric functor.\n"
            "# QPX lookup remains present only for unchanged accepted observables; "
            "it is not the diffusion residual coefficient owner.\n"
            + candidate
        )

    generic_transport = """  [electron_transport]
    type = ADGenericFunctorMaterial
    prop_names = 'electron_mobility electron_diffusion'
    prop_values = '{mobility} {diffusion}'
    block = plasma
  []
""".format(
        mobility=repr(values["electron_mobility"]),
        diffusion=repr(values["electron_diffusion"]),
    )
    candidate = _replace_exact_once(
        c2,
        _QPX_TRANSPORT_BLOCK,
        generic_transport,
        "Issue94 L2 generic constant AD functor replacement",
    )
    return (
        "# Issue #94 L2: exact J2 C2 with QPX transport lookup replaced by "
        "generic constant AD functors at the frozen accepted values.\n"
        + candidate
    )


def classify_first_failure(case_id: str | None) -> tuple[str, dict[str, str]]:
    state = {
        "CONTROL_TIME_ONLY": "OPEN",
        "FRAMEWORK_FV_DIFFUSION_BLOCK_GEOMETRY": "OPEN",
        "GENERIC_FUNCTOR_MATERIAL_COUPLING": "OPEN",
        "QPX_ELECTRON_TRANSPORT_LOOKUP_FUNCTOR": "OPEN",
        "JACOBIAN_ONLY_FOLLOWUP": "HOLD",
    }
    if case_id == "L0":
        state["CONTROL_TIME_ONLY"] = "FAVORED"
        return "L0_CURRENT_EXECUTABLE_CONTROL_REGRESSION_HOLD", state
    if case_id == "L1":
        state["CONTROL_TIME_ONLY"] = "DISFAVORED"
        state["FRAMEWORK_FV_DIFFUSION_BLOCK_GEOMETRY"] = "FAVORED"
        return "FRAMEWORK_FV_DIFFUSION_BLOCK_GEOMETRY_FAVORED", state
    if case_id == "L2":
        state["CONTROL_TIME_ONLY"] = "DISFAVORED"
        state["FRAMEWORK_FV_DIFFUSION_BLOCK_GEOMETRY"] = "DISFAVORED"
        state["GENERIC_FUNCTOR_MATERIAL_COUPLING"] = "FAVORED"
        return "GENERIC_FUNCTOR_MATERIAL_COUPLING_FAVORED", state
    if case_id == "L3":
        state["CONTROL_TIME_ONLY"] = "DISFAVORED"
        state["FRAMEWORK_FV_DIFFUSION_BLOCK_GEOMETRY"] = "DISFAVORED"
        state["GENERIC_FUNCTOR_MATERIAL_COUPLING"] = "DISFAVORED"
        state["QPX_ELECTRON_TRANSPORT_LOOKUP_FUNCTOR"] = "FAVORED"
        return "QPX_ELECTRON_TRANSPORT_LOOKUP_FUNCTOR_FAVORED", state

    for key in (
        "CONTROL_TIME_ONLY",
        "FRAMEWORK_FV_DIFFUSION_BLOCK_GEOMETRY",
        "GENERIC_FUNCTOR_MATERIAL_COUPLING",
        "QPX_ELECTRON_TRANSPORT_LOOKUP_FUNCTOR",
    ):
        state[key] = "DISFAVORED_FOR_RESIDUAL_LADDER"
    state["JACOBIAN_ONLY_FOLLOWUP"] = "FAVORED"
    return "ALL_RESIDUAL_CASES_PASS_JACOBIAN_ONLY_FOLLOWUP", state


def prepare_batch(
    root: Path,
    source_case: Path = SOURCE_CASE,
    electron_reference_case: Path = ELECTRON_REFERENCE_CASE,
) -> dict[str, Any]:
    root = root.resolve()
    source_case = source_case.resolve()
    electron_reference_case = electron_reference_case.resolve()
    identity = _reference_identity(source_case, electron_reference_case)
    frozen = frozen_transport_values(electron_reference_case)

    roles = {
        "L0": "EXACT_J2_C1_TIME_ONLY_CONTROL",
        "L1": "TIME_PLUS_FVDIFFUSION_LITERAL_NUMERIC_COEFF",
        "L2": "TIME_PLUS_FVDIFFUSION_GENERIC_CONSTANT_AD_FUNCTOR",
        "L3": "EXACT_J2_C2_QPX_LOOKUP_DIFFUSION_COEFF",
    }
    cases: dict[str, Any] = {}
    for case_id in CASE_ORDER:
        case_dir = root / "cases" / case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        for name in ("qvt.msh", "electron_moments.txt", "expected.json"):
            shutil.copy2(electron_reference_case / name, case_dir / name)
        text = build_localization_input(case_id, electron_reference_case)
        (case_dir / "input.i").write_text(text)
        cases[case_id] = {
            "case_dir": str(case_dir),
            "input_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "role": roles[case_id],
        }

    manifest = {
        "issue": 94,
        "stage": "CONSTANT_STATE_DIFFUSION_RESIDUAL_LOCALIZATION_PREPARE",
        "qpx_executed": False,
        "scientific_evr_consumed": 0,
        "scientific_acceptance_eligible": False,
        "source_case": str(source_case),
        "electron_reference_case": str(electron_reference_case),
        "identity": identity,
        "frozen_transport": frozen,
        "case_order": list(CASE_ORDER),
        "cases": cases,
        "contract": (
            "All L0-L3 P2 preflights complete before P3. P3 runs adaptively "
            "L0->L3 and stops at the first failed residual contract."
        ),
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    return manifest


def _write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")


def _run_case(
    *,
    qpx: str,
    case_dir: Path,
    log_path: Path,
    timeout: int,
) -> dict[str, Any]:
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
        log_path,
        timeout,
    )
    text = Path(p3["log"]).read_text()
    checker = _check_accepted_qvt_csv(
        case_dir / "input_out.csv", case_dir / "expected.json"
    )
    residuals = _electron_residuals(text)
    return {
        "p3": p3,
        "runtime_log_tail": _tail(text),
        "checker": checker,
        "electron_residuals": residuals,
        "passed": p3["returncode"] == 0 and checker.get("pass") is True,
    }


def run(args: argparse.Namespace) -> int:
    qpx = _resolve_qpx(args.qpx)
    source = args.source_case.resolve()
    reference = args.electron_reference_case.resolve()
    root = (
        args.work_dir.resolve()
        if args.work_dir
        else Path(tempfile.mkdtemp(prefix="issue94_localization_"))
    )
    logs = root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    manifest = prepare_batch(root, source, reference)

    summary: dict[str, Any] = {
        "issue": 94,
        "stage": "CONSTANT_STATE_DIFFUSION_RESIDUAL_LOCALIZATION",
        "artifact_root": str(root),
        "qpx": qpx,
        "manifest": manifest,
        "p2_preflight_complete": False,
        "cases": {},
        "selected_failure_case": None,
        "decision": "NOT_RUN",
        "hypotheses": {},
        "batch_scientific_evr_consumed": 0,
        "issue94_evr_total": ISSUE94_ENTERING_EVR,
        "scientific_acceptance_eligible": False,
    }

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
        }
        if p2["returncode"] != 0:
            summary["decision"] = (
                f"ISSUE94_P2_CONSTRUCTION_OR_FRAMEWORK_CONTRACT_FAIL_{case_id}"
            )
            _write_json(root / "summary.json", summary)
            print(f"ISSUE94_P2: FAIL {case_id}")
            print(f"ISSUE94_DECISION: {summary['decision']}")
            print("ISSUE94_BATCH_EVR: 0")
            print(f"ISSUE94_EVR: {ISSUE94_ENTERING_EVR}")
            print("ISSUE94_P2_LOG_TAIL_BEGIN")
            print(summary["cases"][case_id]["p2_log_tail"])
            print("ISSUE94_P2_LOG_TAIL_END")
            print(f"ARTIFACT_ROOT: {root}")
            return 2

    summary["p2_preflight_complete"] = True
    failure: str | None = None

    for case_id in CASE_ORDER:
        case_dir = Path(manifest["cases"][case_id]["case_dir"])
        result = _run_case(
            qpx=qpx,
            case_dir=case_dir,
            log_path=logs / f"{case_id.lower()}_runtime.log",
            timeout=args.timeout,
        )
        summary["batch_scientific_evr_consumed"] = 1
        summary["issue94_evr_total"] = ISSUE94_ENTERING_EVR + 1
        summary["cases"][case_id].update(result)
        if not result["passed"]:
            failure = case_id
            break

    decision, hypotheses = classify_first_failure(failure)
    summary["selected_failure_case"] = failure
    summary["decision"] = decision
    summary["hypotheses"] = hypotheses
    _write_json(root / "summary.json", summary)

    print("ISSUE94_P2: PASS ALL")
    for case_id in CASE_ORDER:
        case = summary["cases"].get(case_id)
        if not case or case.get("p3") is None:
            continue
        print(
            f"ISSUE94_{case_id}: "
            f"{'PASS' if case['passed'] else 'FAIL'} "
            f"RC={case['p3']['returncode']} "
            f"RESIDUALS={case['electron_residuals']}"
        )
    print(
        "ISSUE94_SELECTED_CASE: "
        f"{failure if failure is not None else 'NONE'}"
    )
    print(f"ISSUE94_DECISION: {decision}")
    print("ISSUE94_BATCH_EVR: 1")
    print(f"ISSUE94_EVR: {ISSUE94_ENTERING_EVR + 1}")
    print("SCIENTIFIC_ACCEPTANCE_ELIGIBLE: false")
    if failure is not None:
        failing = summary["cases"][failure]
        print(f"ISSUE94_CHECKER: {failing['checker']}")
        print("ISSUE94_RUNTIME_LOG_TAIL_BEGIN")
        print(failing["runtime_log_tail"])
        print("ISSUE94_RUNTIME_LOG_TAIL_END")
    print(f"ARTIFACT_ROOT: {root}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qpx", required=True)
    parser.add_argument("--source-case", type=Path, default=SOURCE_CASE)
    parser.add_argument(
        "--electron-reference-case", type=Path, default=ELECTRON_REFERENCE_CASE
    )
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    try:
        return run(args)
    except (Issue94Error, RunError, OSError, ValueError, KeyError) as exc:
        print(f"ISSUE94_ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
