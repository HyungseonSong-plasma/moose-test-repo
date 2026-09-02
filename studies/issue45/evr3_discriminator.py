#!/usr/bin/env python3
"""Issue45 final EVR3 science discriminator.

This is intentionally study code, not framework code. It performs one
observability-only C0 first-linear run after P1/P2 gates and freezes the raw
facts needed to distinguish Issue45 H1 conditioning/scaling from H2
Krylov residual-fidelity loss.

No solver tuning is performed here. Any reusable mechanics discovered by this
study are reviewed later by Issue89 before entering qpx_harness.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from recipes import issue45_closure_basis as closure_basis
from recipes import issue45_inventory_constraint as inventory_policy
from qpx_harness import evidence
from qpx_harness.execution.runtime import resolve_executable, run_qpx, validate_executable
from qpx_harness.inventory import first_linear_orchestration as orch
from qpx_harness.moose import log as moose_log
from qpx_harness.moose import parameters as mp
from qpx_harness.petsc import ksp
from qpx_harness.petsc import log as petsc_log
from qpx_harness.petsc import options as po

ISSUE = 45
WORK_ISSUE = 88
TARGET = 1.0e16
NL_MAX_ITS = 1
RESIDUAL_FIDELITY_RATIO_THRESHOLD = 1.0e6
STEM = "issue45_evr3_h1_h2_discriminator"
CONSUMED_MARKER = "EVR3_CONSUMED.json"

REQUIRED_FLAGS = (
    "-snes_converged_reason",
    "-ksp_converged_reason",
    "-ksp_view",
    "-ksp_monitor_true_residual",
    "-ksp_monitor_singular_value",
)
FORBIDDEN_FLAGS = (
    "-snes_test_jacobian",
    "-snes_test_jacobian_view",
)
EXPECTED_NAME_VALUE_PAIRS = (
    ("-pc_type", "lu"),
    ("-pc_factor_shift_type", "NONZERO"),
)
SCALING_VARIABLES = ("n_e", "potential_plasma", "r45_inventory_lambda")

_FLOAT = r"[+\-]?(?:(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+\-]?\d+)?|nan|inf(?:inity)?)"
_SINGULAR_MONITOR = re.compile(
    rf"(?mi)^\s*(\d+)\s+KSP\s+Residual\s+norm\s+({_FLOAT})\s+%\s+"
    rf"max\s+({_FLOAT})\s+min\s+({_FLOAT})\s+max/min\s+({_FLOAT})\s*$"
)


class Issue45EVR3Error(RuntimeError):
    pass


def _jsonable(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return "Infinity" if value > 0 else "-Infinity" if value < 0 else "NaN"
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_jsonable(payload), indent=2, sort_keys=True) + "\n")


def _normalized_observability_text(text: str) -> str:
    out = mp.upsert_parameter(
        text,
        "Executioner",
        "nl_max_its",
        "<ISSUE45_EVR3_NL_MAX_ITS>",
    )
    return mp.upsert_parameter(
        out,
        "Executioner",
        "petsc_options",
        "'<ISSUE45_EVR3_OBSERVABILITY_FLAGS>'",
    )


def _build_evr3_input() -> tuple[Path, str, str, dict[str, Any]]:
    base_case, base_text, radial_span = orch._base_case_context()
    baseline, closure_meta = closure_basis.build_constrained_quasisteady_input(
        base_text,
        radial_span=radial_span,
        macro_avg=TARGET,
        runtime_observability=True,
    )

    baseline_flags = po.get_flags(baseline)
    leaked = [flag for flag in FORBIDDEN_FLAGS if flag in baseline_flags]
    if leaked:
        raise Issue45EVR3Error(
            "C0 closure baseline unexpectedly contains forbidden diagnostic flags: "
            + ", ".join(leaked)
        )

    text = mp.upsert_parameter(baseline, "Executioner", "nl_max_its", str(NL_MAX_ITS))
    text = po.add_flags(text, REQUIRED_FLAGS)

    return base_case, baseline, text, {
        "closure_basis": closure_meta,
        "radial_span": radial_span,
        "baseline_flags": baseline_flags,
        "required_flags": list(REQUIRED_FLAGS),
        "forbidden_flags": list(FORBIDDEN_FLAGS),
    }


def _p1_audit(baseline: str, text: str) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(check_id: str, passed: bool, observed: Any, required: Any) -> None:
        checks.append(
            {
                "id": check_id,
                "status": "PASS" if passed else "FAIL",
                "observed": observed,
                "required": required,
            }
        )

    closure_before = inventory_policy.audit_constrained_quasisteady_structure(
        baseline,
        expected_macro_avg=TARGET,
    )
    closure_after = inventory_policy.audit_constrained_quasisteady_structure(
        text,
        expected_macro_avg=TARGET,
    )
    add(
        "baseline-closure",
        closure_before["status"] == "PASS",
        closure_before["status"],
        "PASS",
    )
    add(
        "diagnostic-closure",
        closure_after["status"] == "PASS",
        closure_after["status"],
        "PASS",
    )

    nl_max = mp.unquote(mp.get_parameter(text, "Executioner", "nl_max_its"))
    add("bounded-first-linear-horizon", nl_max == "1", nl_max, "1")

    flags = po.get_flags(text)
    add(
        "required-observability-flags",
        all(flag in flags for flag in REQUIRED_FLAGS),
        flags,
        list(REQUIRED_FLAGS),
    )
    add(
        "historical-wp-jacobian-test-absent",
        all(flag not in flags for flag in FORBIDDEN_FLAGS),
        [flag for flag in flags if flag in FORBIDDEN_FLAGS],
        [],
    )

    before_pairs = tuple(po.get_name_value_pairs(baseline))
    after_pairs = tuple(po.get_name_value_pairs(text))
    add(
        "pc-realization-preserved",
        before_pairs == EXPECTED_NAME_VALUE_PAIRS
        and after_pairs == EXPECTED_NAME_VALUE_PAIRS,
        {"before": before_pairs, "after": after_pairs},
        EXPECTED_NAME_VALUE_PAIRS,
    )

    normalized_same = (
        _normalized_observability_text(baseline)
        == _normalized_observability_text(text)
    )
    add(
        "observability-only-input-difference",
        normalized_same,
        normalized_same,
        True,
    )

    scaling_controls = {
        name: mp.unquote(mp.get_parameter(text, "Executioner", name))
        for name in (
            "automatic_scaling",
            "off_diagonals_in_auto_scaling",
            "compute_scaling_once",
        )
    }
    baseline_scaling_controls = {
        name: mp.unquote(mp.get_parameter(baseline, "Executioner", name))
        for name in scaling_controls
    }
    add(
        "scaling-policy-preserved",
        scaling_controls == baseline_scaling_controls,
        scaling_controls,
        baseline_scaling_controls,
    )

    blockers = [check for check in checks if check["status"] != "PASS"]
    return {
        "status": "PASS" if not blockers else "HOLD",
        "checks": checks,
        "blockers": blockers,
        "closure_before": closure_before,
        "closure_after": closure_after,
    }


def _results_parent(exe: Path, results_root: str | None) -> Path:
    return (
        Path(results_root).expanduser().resolve()
        if results_root
        else exe.parent / "temp" / "results"
    )


def _previous_consumptions(parent: Path) -> list[str]:
    if not parent.is_dir():
        return []
    return sorted(
        str(path)
        for path in parent.glob(f"{STEM}_*/{CONSUMED_MARKER}")
        if path.is_file()
    )


def _prepare(exe: Path, results_root: str | None) -> dict[str, Any]:
    base_case, baseline, text, construction = _build_evr3_input()
    p1 = _p1_audit(baseline, text)
    root = orch._evidence_root(exe=exe, results_root=results_root, stem=STEM)
    case_dir = root / "case"
    orch._stage_case(base_case, case_dir, text)
    return {
        "root": root,
        "case_dir": case_dir,
        "input_path": case_dir / "input.i",
        "baseline": baseline,
        "input_text": text,
        "construction": construction,
        "p1": p1,
    }


def _run_p2(exe: Path, prepared: dict[str, Any]) -> dict[str, Any]:
    log = prepared["root"] / "p2_check_input.log"
    run = run_qpx(
        exe,
        cwd=prepared["case_dir"],
        input_name="input.i",
        log_path=log,
        extra_args=("--check-input", "--color", "off"),
        stream=False,
    )
    return {
        "status": "PASS" if run.returncode == 0 else "HOLD",
        "returncode": run.returncode,
        "wall_seconds": run.wall_seconds,
        "log": str(log),
    }


def _identity(exe: Path, prepared: dict[str, Any]) -> dict[str, Any]:
    return {
        **evidence.identity_record(executable=exe, input_path=prepared["input_path"]),
        "qpx_sha256": evidence.sha256_file(exe),
    }


def _preflight(exe: Path, results_root: str | None) -> dict[str, Any]:
    prepared = _prepare(exe, results_root)
    p2 = _run_p2(exe, prepared) if prepared["p1"]["status"] == "PASS" else {}
    status = (
        "PASS"
        if prepared["p1"]["status"] == "PASS" and p2.get("status") == "PASS"
        else "HOLD"
    )
    summary = {
        "issue": ISSUE,
        "work_issue": WORK_ISSUE,
        "mode": "evr3-preflight",
        "status": status,
        "p3_executed": False,
        "evr_consumed": 0,
        "identity": _identity(exe, prepared),
        "construction": prepared["construction"],
        "p1": prepared["p1"],
        "p2": p2,
        "protocol": "studies/issue45/evr3_protocol.json",
    }
    path = prepared["root"] / "preflight_summary.json"
    _write_json(path, summary)
    summary["summary_path"] = str(path)
    summary["prepared"] = prepared
    return summary


def _parse_singular_monitor(text: str) -> list[dict[str, float | int]]:
    rows: list[dict[str, float | int]] = []
    for match in _SINGULAR_MONITOR.finditer(text):
        try:
            rows.append(
                {
                    "iteration": int(match.group(1)),
                    "residual_norm": float(match.group(2)),
                    "sigma_max": float(match.group(3)),
                    "sigma_min": float(match.group(4)),
                    "sigma_max_over_min": float(match.group(5)),
                }
            )
        except ValueError:
            continue
    return rows


def _scaling_summary(blocks: list[dict[str, float]]) -> dict[str, Any]:
    selected_blocks: list[dict[str, Any]] = []
    for index, block in enumerate(blocks):
        selected = {name: block[name] for name in SCALING_VARIABLES if name in block}
        finite_nonzero = [
            abs(value)
            for value in selected.values()
            if math.isfinite(value) and value != 0.0
        ]
        selected_blocks.append(
            {
                "index": index,
                "selected": selected,
                "selected_spread": (
                    max(finite_nonzero) / min(finite_nonzero)
                    if len(finite_nonzero) >= 2
                    else None
                ),
            }
        )
    return {
        "block_count": len(blocks),
        "variables_requested": list(SCALING_VARIABLES),
        "blocks": selected_blocks,
    }


def _runtime_facts(text: str, returncode: int) -> dict[str, Any]:
    identity = ksp.parse_ksp_view(text)
    residual_rows = ksp.parse_true_residuals(text)
    residual_audit = ksp.residual_fidelity_audit(
        residual_rows,
        restart=identity.get("restart"),
        ratio_threshold=RESIDUAL_FIDELITY_RATIO_THRESHOLD,
    )
    singular_rows = _parse_singular_monitor(text)
    scaling_blocks = moose_log.parse_automatic_scaling_factors(text)
    linear = petsc_log.parse_linear_solve_terminations(text)
    nonlinear = petsc_log.parse_nonlinear_solve_terminations(text)
    pc_failure = petsc_log.parse_pc_failure_reason(text)

    finite_proxies = [
        abs(float(row["sigma_max_over_min"]))
        for row in singular_rows
        if math.isfinite(float(row["sigma_max_over_min"]))
    ]
    return {
        "returncode": returncode,
        "ksp_identity": identity,
        "true_residual_rows": residual_rows,
        "residual_fidelity": residual_audit,
        "singular_value_monitor": {
            "sample_count": len(singular_rows),
            "rows": singular_rows,
            "max_proxy": max(finite_proxies) if finite_proxies else None,
            "interpretation": (
                "preconditioned-operator conditioning proxy only; not an exact global condition number"
            ),
        },
        "automatic_scaling": _scaling_summary(scaling_blocks),
        "linear_terminations": linear,
        "nonlinear_terminations": nonlinear,
        "pc_failure_reason": pc_failure,
        "diagnostic_complete": bool(residual_rows) and bool(singular_rows),
        "restart_causality": "NOT_ESTABLISHED",
    }


def run_preflight(qpx: str | None, results_root: str | None) -> int:
    exe = resolve_executable(qpx)
    validate_executable(exe)
    result = _preflight(exe, results_root)
    print(f"ISSUE45_EVR3_P1: {result['p1']['status']}")
    print(f"ISSUE45_EVR3_P2: {result['p2'].get('status', 'HOLD')}")
    print(f"ISSUE45_EVR3_PREFLIGHT: {result['status']}")
    print("ISSUE45_EVR3_EVR_CONSUMED: 0")
    print(f"ISSUE45_EVR3_SUMMARY: {result['summary_path']}")
    return 0 if result["status"] == "PASS" else 2


def run_evr3(qpx: str | None, results_root: str | None) -> int:
    exe = resolve_executable(qpx)
    validate_executable(exe)
    parent = _results_parent(exe, results_root)
    consumed = _previous_consumptions(parent)
    if consumed:
        print("ISSUE45_EVR3_RUN: REFUSED")
        print("ISSUE45_EVR3_REASON: EVR3 consumption marker already exists")
        for path in consumed:
            print(f"ISSUE45_EVR3_EXISTING_MARKER: {path}")
        return 3

    preflight = _preflight(exe, results_root)
    if preflight["status"] != "PASS":
        print("ISSUE45_EVR3_PREFLIGHT: HOLD")
        print("ISSUE45_EVR3_EVR_CONSUMED: 0")
        print(f"ISSUE45_EVR3_SUMMARY: {preflight['summary_path']}")
        return 2

    prepared = preflight["prepared"]
    marker = prepared["root"] / CONSUMED_MARKER
    _write_json(
        marker,
        {
            "issue": ISSUE,
            "work_issue": WORK_ISSUE,
            "evr": 3,
            "state": "CONSUMED_ON_P3_START",
            "reason": "one final predeclared H1/H2 observability-only discriminator",
            "input_identity": _identity(exe, prepared),
        },
    )

    log = prepared["root"] / "p3_evr3_h1_h2.log"
    print("ISSUE45_EVR3_RUN: START")
    run = run_qpx(
        exe,
        cwd=prepared["case_dir"],
        input_name="input.i",
        log_path=log,
        extra_args=("--color", "off"),
        stream=True,
    )
    text = log.read_text(errors="replace") if log.is_file() else ""
    facts = _runtime_facts(text, run.returncode)
    summary = {
        "issue": ISSUE,
        "work_issue": WORK_ISSUE,
        "mode": "evr3-h1-h2-discriminator",
        "evr": 3,
        "evr_consumed": 1,
        "scope": "one bounded C0 first-linear observability-only discriminator",
        "protocol": "studies/issue45/evr3_protocol.json",
        "runtime": {
            "returncode": run.returncode,
            "wall_seconds": run.wall_seconds,
            "log": str(log),
            "identity": _identity(exe, prepared),
        },
        "p1": preflight["p1"],
        "p2": preflight["p2"],
        "facts": facts,
        "scientific_interpretation": "PENDING_ISSUE88_PROTOCOL_INTERPRETATION",
        "followup_runtime_authorized": False,
    }
    summary_path = prepared["root"] / "evr3_summary.json"
    _write_json(summary_path, summary)

    print(f"ISSUE45_EVR3_CASE_END: rc={run.returncode}")
    print(f"ISSUE45_EVR3_TRUE_RESIDUAL_ROWS: {len(facts['true_residual_rows'])}")
    print(
        "ISSUE45_EVR3_RESIDUAL_FIDELITY_LOSS: "
        f"{facts['residual_fidelity']['residual_fidelity_loss_observed']}"
    )
    print(
        "ISSUE45_EVR3_MAX_RESIDUAL_SEPARATION_RATIO: "
        f"{facts['residual_fidelity']['max_residual_separation_ratio']}"
    )
    print(
        "ISSUE45_EVR3_SINGULAR_VALUE_ROWS: "
        f"{facts['singular_value_monitor']['sample_count']}"
    )
    print(
        "ISSUE45_EVR3_MAX_CONDITIONING_PROXY: "
        f"{facts['singular_value_monitor']['max_proxy']}"
    )
    print(f"ISSUE45_EVR3_SCALING_BLOCKS: {facts['automatic_scaling']['block_count']}")
    print(f"ISSUE45_EVR3_PC_FAILURE_REASON: {facts['pc_failure_reason']}")
    print(f"ISSUE45_EVR3_DIAGNOSTIC_COMPLETE: {facts['diagnostic_complete']}")
    print("ISSUE45_EVR3_RESTART_CAUSALITY: NOT_ESTABLISHED")
    print("ISSUE45_EVR3_FOLLOWUP_RUNTIME_AUTHORIZED: False")
    print(f"ISSUE45_EVR3_LOG: {log}")
    print(f"ISSUE45_EVR3_SUMMARY: {summary_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Issue45 final H1/H2 EVR3 science discriminator"
    )
    parser.add_argument("--qpx", help="path to user-local qpx-opt")
    parser.add_argument("--results-root")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--run", action="store_true")
    args = parser.parse_args(argv)

    try:
        if args.run:
            return run_evr3(args.qpx, args.results_root)
        return run_preflight(args.qpx, args.results_root)
    except Exception as exc:
        print(f"ISSUE45_EVR3: HOLD ({type(exc).__name__}: {exc})")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
