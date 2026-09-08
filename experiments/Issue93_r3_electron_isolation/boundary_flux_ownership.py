#!/usr/bin/env python3
"""Issue #93 J3: focused C2 diffusion boundary-flux ownership confirmation.

J3 is one bounded scientific batch for the owner selected by J2. It first tests
whether the C2 residual disappears when FVDiffusion is prevented from executing
on the real-QVT plasma interface sidesets. Only if that discriminator does not
confirm boundary-flux ownership does the batch launch one finite-difference
Jacobian comparison for the original C2 case.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from experiments.Issue93_r3_electron_isolation.operator_decomposition import (
    _check_accepted_qvt_csv,
    _reference_identity,
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

ISSUE93_ENTERING_EVR = 2
ZERO_RESIDUAL_TOL = 1.0e-12
PLASMA_INTERFACE_BOUNDARIES = (
    "inlet",
    "outlet",
    "plasma_electrode",
    "plasma_metal",
    "plasma_right",
    "plasma_cover",
    "plasma_wafer",
    "plasma_focus_ring",
)

_DIFFUSION_BLOCK = """  [diffusion]
    type = FVDiffusion
    variable = n_e
    coeff = electron_diffusion
    block = plasma
  []
"""


class J3Error(RuntimeError):
    pass


def _replace_exact_once(text: str, old: str, new: str, claim: str) -> str:
    count = text.count(old)
    if count != 1:
        raise J3Error(f"{claim}: expected exactly one target block, found {count}")
    return text.replace(old, new, 1)


def build_boundary_excluded_input(
    electron_reference_case: Path = ELECTRON_REFERENCE_CASE,
) -> str:
    """Return J2 C2 with only plasma-interface FVDiffusion execution excluded."""
    c2 = build_case_input("C2", electron_reference_case)
    boundary_text = " ".join(PLASMA_INTERFACE_BOUNDARIES)
    replacement = _DIFFUSION_BLOCK.replace(
        "    block = plasma\n",
        f"    boundaries_to_avoid = '{boundary_text}'\n"
        "    block = plasma\n",
        1,
    )
    candidate = _replace_exact_once(
        c2,
        _DIFFUSION_BLOCK,
        replacement,
        "J3 diffusion boundary-execution discriminator",
    )
    return (
        "# Issue #93 J3 D0: C2 with only framework diffusion execution removed "
        "from plasma interfaces.\n"
        "# No wall/surface-reaction physics is added in this diagnostic.\n"
        + candidate
    )


def build_jacobian_input(
    electron_reference_case: Path = ELECTRON_REFERENCE_CASE,
) -> str:
    """Return the exact original J2 C2 input for fallback AD-vs-FD checking."""
    return build_case_input("C2", electron_reference_case)


def residual_trace_is_zero(
    residuals: list[float], tol: float = ZERO_RESIDUAL_TOL
) -> bool:
    return bool(residuals) and max(abs(value) for value in residuals) <= tol


def prepare_batch(
    root: Path,
    source_case: Path = SOURCE_CASE,
    electron_reference_case: Path = ELECTRON_REFERENCE_CASE,
) -> dict[str, Any]:
    root = root.resolve()
    source_case = source_case.resolve()
    electron_reference_case = electron_reference_case.resolve()
    identity = _reference_identity(source_case, electron_reference_case)

    inputs = {
        "D0": build_boundary_excluded_input(electron_reference_case),
        "JAC": build_jacobian_input(electron_reference_case),
    }
    cases: dict[str, Any] = {}
    for case_id, text in inputs.items():
        case_dir = root / "cases" / case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        for name in ("qvt.msh", "electron_moments.txt", "expected.json"):
            shutil.copy2(electron_reference_case / name, case_dir / name)
        (case_dir / "input.i").write_text(text)
        cases[case_id] = {
            "case_dir": str(case_dir),
            "input_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "role": (
                "C2_WITH_PLASMA_INTERFACE_DIFFUSION_EXECUTION_EXCLUDED"
                if case_id == "D0"
                else "EXACT_J2_C2_FOR_AD_VS_FD_JACOBIAN_FALLBACK"
            ),
        }

    manifest = {
        "issue": 93,
        "stage": "J3_DIFFUSION_BOUNDARY_FLUX_OWNERSHIP_PREPARE",
        "qpx_executed": False,
        "scientific_evr_consumed": 0,
        "scientific_acceptance_eligible": False,
        "source_case": str(source_case),
        "electron_reference_case": str(electron_reference_case),
        "identity": identity,
        "plasma_interface_boundaries": list(PLASMA_INTERFACE_BOUNDARIES),
        "case_order": ["D0", "JAC"],
        "cases": cases,
        "contract": (
            "D0 changes only FVDiffusion boundary execution; "
            "JAC is exact J2 C2 and launches only if D0 does not confirm ownership"
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
    extra_petsc: tuple[str, ...] = (),
) -> dict[str, Any]:
    p3 = _run(
        [
            qpx,
            "-i",
            "input.i",
            "-snes_monitor",
            "-snes_converged_reason",
            "-ksp_converged_reason",
            *extra_petsc,
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
        else Path(tempfile.mkdtemp(prefix="issue93_j3_"))
    )
    logs = root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    manifest = prepare_batch(root, source, reference)

    summary: dict[str, Any] = {
        "issue": 93,
        "stage": "J3_DIFFUSION_BOUNDARY_FLUX_OWNERSHIP_CONFIRMATION",
        "artifact_root": str(root),
        "qpx": qpx,
        "manifest": manifest,
        "p2_preflight_complete": False,
        "cases": {},
        "decision": "NOT_RUN",
        "batch_scientific_evr_consumed": 0,
        "issue93_evr_total": ISSUE93_ENTERING_EVR,
        "scientific_acceptance_eligible": False,
    }

    # Preflight every predeclared J3 input before consuming EVR3.
    for case_id in ("D0", "JAC"):
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
            summary["decision"] = f"J3_P2_CONSTRUCTION_OR_FRAMEWORK_CONTRACT_FAIL_{case_id}"
            _write_json(root / "summary.json", summary)
            print(f"ISSUE93_J3_P2: FAIL {case_id}")
            print(f"ISSUE93_J3_DECISION: {summary['decision']}")
            print("ISSUE93_J3_BATCH_EVR: 0")
            print(f"ISSUE93_EVR: {ISSUE93_ENTERING_EVR}")
            print("ISSUE93_J3_P2_LOG_TAIL_BEGIN")
            print(summary["cases"][case_id]["p2_log_tail"])
            print("ISSUE93_J3_P2_LOG_TAIL_END")
            print(f"ARTIFACT_ROOT: {root}")
            return 2

    summary["p2_preflight_complete"] = True

    d0_dir = Path(manifest["cases"]["D0"]["case_dir"])
    d0 = _run_case(
        qpx=qpx,
        case_dir=d0_dir,
        log_path=logs / "d0_runtime.log",
        timeout=args.timeout,
    )
    summary["batch_scientific_evr_consumed"] = 1
    summary["issue93_evr_total"] = ISSUE93_ENTERING_EVR + 1
    summary["cases"]["D0"].update(d0)

    d0_zero = d0["passed"] and residual_trace_is_zero(d0["electron_residuals"])
    summary["cases"]["D0"]["zero_residual_contract"] = d0_zero

    if d0_zero:
        summary["decision"] = (
            "FRAMEWORK_EFFECTIVE_DIFFUSION_BOUNDARY_FLUX_OWNERSHIP_CONFIRMED"
        )
    else:
        jac_dir = Path(manifest["cases"]["JAC"]["case_dir"])
        jac = _run_case(
            qpx=qpx,
            case_dir=jac_dir,
            log_path=logs / "jacobian_runtime.log",
            timeout=args.timeout,
            extra_petsc=("-snes_test_jacobian",),
        )
        summary["cases"]["JAC"].update(jac)
        summary["decision"] = (
            "J3_BOUNDARY_OWNERSHIP_NOT_CONFIRMED_FD_JACOBIAN_EVIDENCE_RETURNED"
        )

    _write_json(root / "summary.json", summary)

    print("ISSUE93_J3_P2: PASS ALL")
    print(
        "ISSUE93_J3_D0: "
        f"{'PASS' if d0['passed'] else 'FAIL'} "
        f"RC={d0['p3']['returncode']} "
        f"RESIDUALS={d0['electron_residuals']} "
        f"ZERO_RESIDUAL={d0_zero}"
    )
    if summary["cases"]["JAC"].get("p3") is not None:
        jac = summary["cases"]["JAC"]
        print(
            "ISSUE93_J3_JAC: "
            f"RC={jac['p3']['returncode']} "
            f"RESIDUALS={jac['electron_residuals']}"
        )
        print("ISSUE93_J3_JACOBIAN_LOG_TAIL_BEGIN")
        print(jac["runtime_log_tail"])
        print("ISSUE93_J3_JACOBIAN_LOG_TAIL_END")
    print(f"ISSUE93_J3_DECISION: {summary['decision']}")
    print("ISSUE93_J3_BATCH_EVR: 1")
    print(f"ISSUE93_EVR: {ISSUE93_ENTERING_EVR + 1}")
    print("SCIENTIFIC_ACCEPTANCE_ELIGIBLE: false")
    if not d0_zero:
        print(f"ISSUE93_J3_D0_CHECKER: {d0['checker']}")
        print("ISSUE93_J3_D0_RUNTIME_LOG_TAIL_BEGIN")
        print(d0["runtime_log_tail"])
        print("ISSUE93_J3_D0_RUNTIME_LOG_TAIL_END")
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
    except (J3Error, RunError, OSError, ValueError, KeyError) as exc:
        print(f"ISSUE93_J3_ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
