#!/usr/bin/env python3
"""Diagnostic-only S5-R P3 discriminator matrix for issue #192.

This runner does not establish representative acceptance.  It perturbs the
already assembled S5-R runtime surface only to distinguish timestep/source
stiffness, EDETACH dominance, and electron-energy-loss dominance after a
canonical representative runtime failure.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.Issue192_s5r_representative import run as s5r  # noqa: E402
from physics_harness.adapters.moose import blocks as mb  # noqa: E402
from physics_harness.adapters.moose import parameters as mp  # noqa: E402
from physics_harness.execution.cases import stage_case, validate_case_references  # noqa: E402
from physics_harness.execution.runtime import resolve_executable, validate_executable  # noqa: E402

DIAGNOSTIC_END_TIME_S = s5r.END_TIME_S
CASE_SPECS = (
    {
        "name": "d1_full_dt_25us",
        "dt_s": 2.5e-5,
        "mode": "full",
        "question": "Does halving the failed half-step again remove the lookup-domain failure?",
    },
    {
        "name": "d2_full_dt_10us",
        "dt_s": 1.0e-5,
        "mode": "full",
        "question": "Does a timestep below the initial dominant chemistry timescale remove the failure?",
    },
    {
        "name": "d3_edetach_off_dt_100us",
        "dt_s": s5r.BASELINE_DT_S,
        "mode": "edetach_off",
        "question": "Is EDETACH_OM the dominant trigger of the representative energy collapse?",
    },
    {
        "name": "d4_energy_losses_off_dt_100us",
        "dt_s": s5r.BASELINE_DT_S,
        "mode": "energy_losses_off",
        "question": "Do explicit reaction-energy loss kernels dominate the failure, versus electron birth dilution/transport?",
    },
)

ENERGY_KERNEL_PATHS = (
    "FVKernels/s5r_ei02_elastic_energy",
    "FVKernels/s5r_ei17_elastic_energy",
    *tuple(f"FVKernels/s5r_energy_{channel.lower()}" for channel in s5r.ENERGY_CHANNELS),
)


class DiagnosticMatrixError(RuntimeError):
    pass


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _collision_safe_directory(parent: Path, stem: str) -> Path:
    parent.mkdir(parents=True, exist_ok=True)
    candidate = parent / stem
    if not candidate.exists():
        candidate.mkdir()
        return candidate
    for index in range(1, 10000):
        candidate = parent / f"{stem}_{index:03d}"
        if not candidate.exists():
            candidate.mkdir()
            return candidate
    raise DiagnosticMatrixError(f"cannot allocate result directory under {parent}")


def _disable_edetach(text: str) -> str:
    path = "FunctorMaterials/s5r_edetach_rate"
    if not mb.has_block(text, path):
        raise DiagnosticMatrixError("missing canonical EDETACH progress owner")
    text = mb.remove_block(text, path)
    return mb.insert_child_block(
        text,
        "FunctorMaterials",
        """  [s5r_edetach_rate]
    type = ADGenericFunctorMaterial
    prop_names = 'R_detach_Om'
    prop_values = '0'
    block = plasma
  []""",
    )


def _disable_reaction_energy_losses(text: str) -> str:
    for path in ENERGY_KERNEL_PATHS:
        if not mb.has_block(text, path):
            raise DiagnosticMatrixError(f"missing expected reaction-energy kernel: {path}")
        text = mb.remove_block(text, path)
    return text


def _case_text(*, dt_s: float, mode: str) -> tuple[str, dict[str, Any]]:
    text, meta = s5r._runtime_input(dt_s)
    canonical_audit = s5r.audit_s5r_input(text)
    if canonical_audit["status"] != "PASS":
        raise DiagnosticMatrixError("canonical input failed before diagnostic perturbation")

    perturbation = "NONE"
    if mode == "full":
        pass
    elif mode == "edetach_off":
        text = _disable_edetach(text)
        perturbation = "R_detach_Om replaced by diagnostic constant zero"
    elif mode == "energy_losses_off":
        text = _disable_reaction_energy_losses(text)
        perturbation = "electron-energy reaction/elastic projection kernels removed"
    else:
        raise DiagnosticMatrixError(f"unknown diagnostic mode {mode}")

    for token in s5r.DEFERRED_TOKENS:
        if token in text:
            raise DiagnosticMatrixError(f"deferred channel leaked into diagnostic input: {token}")

    meta = dict(meta)
    meta["diagnostic_matrix"] = {
        "mode": mode,
        "perturbation": perturbation,
        "dt_s": dt_s,
        "end_time_s": DIAGNOSTIC_END_TIME_S,
        "representative_acceptance_claim": False,
        "canonical_semantics_preserved": mode == "full",
    }
    return text, meta


def _stage(case_dir: Path, *, text: str, meta: dict[str, Any]) -> dict[str, Any]:
    staging = stage_case(
        s5r.SOURCE,
        case_dir,
        input_text=text,
        purge_directory_names=(".jitcache", "checkpoint", "checkpoints"),
        purge_patterns=("input_out*", "*.log", "*.e", "*.exo", "prepare_evidence.json"),
    )
    s5r._copy_runtime_assets(case_dir)
    references = validate_case_references(case_dir)
    (case_dir / "prepare_evidence.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True) + "\n"
    )
    return {"staging": staging, "referenced_files": references}


def _float_or_none(value: str | None) -> float | None:
    try:
        result = float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
    return result if result is not None and math.isfinite(result) else None


def _csv_snapshot(case_dir: Path) -> dict[str, Any]:
    path = case_dir / "input_out.csv"
    if not path.is_file():
        return {"status": "MISSING"}
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return {"status": "EMPTY"}
    row = rows[-1]
    keys = (
        "time",
        "s5r_mean_en_min",
        "s5r_mean_en_max",
        "s5r_mean_en_avg",
        "n_e_avg",
        "s5r_n_epsilon_inventory",
        "w_Om_avg",
        "s5r_progress_edetach_om",
    )
    return {
        "status": "AVAILABLE",
        "rows": len(rows),
        "last": {key: _float_or_none(row.get(key)) for key in keys},
    }


def _error_facts(log_path: Path) -> dict[str, Any]:
    if not log_path.is_file():
        return {"status": "MISSING"}
    text = log_path.read_text(errors="replace")
    lines = text.splitlines()
    selected = [
        line.strip()
        for line in lines
        if "*** ERROR ***" in line
        or "mean energy" in line.lower()
        or "outside" in line.lower() and "range" in line.lower()
    ]
    got_values = [
        float(match)
        for match in re.findall(
            r"got\s+([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*eV",
            text,
        )
    ]
    time_values = [
        float(match)
        for match in re.findall(
            r"(?:Time Step\s+\d+[^\n]*?time\s*=|time\s*=)\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)",
            text,
            flags=re.IGNORECASE,
        )
    ]
    return {
        "status": "PARSED",
        "mean_energy_got_eV": got_values[-1] if got_values else None,
        "last_logged_time_s": time_values[-1] if time_values else None,
        "selected_error_lines": selected[-12:],
    }


def _interpret(cases: dict[str, Any]) -> dict[str, Any]:
    success = {name: data["runtime"]["returncode"] == 0 for name, data in cases.items()}
    d1 = success.get("d1_full_dt_25us", False)
    d2 = success.get("d2_full_dt_10us", False)
    d3 = success.get("d3_edetach_off_dt_100us", False)
    d4 = success.get("d4_energy_losses_off_dt_100us", False)

    conclusions: list[str] = []
    if not d1 and not d2:
        conclusions.append(
            "Full chemistry still fails at 25 us and 10 us: failure is not explained by the original 50-100 us timestep alone."
        )
    elif d2 and not d1:
        conclusions.append(
            "10 us survives while 25 us fails: strong timestep/source-stiffness sensitivity is established."
        )
    elif d1 and d2:
        conclusions.append(
            "Both reduced full-chemistry timesteps survive: original failure is primarily timestep/source-stiffness limited over this horizon."
        )

    if d3:
        conclusions.append(
            "Disabling only EDETACH restores runtime completion at 100 us: EDETACH is a dominant trigger."
        )
    else:
        conclusions.append(
            "EDETACH-off still fails at 100 us: EDETACH is not the sole trigger; other energy/particle coupling remains sufficient."
        )

    if d4:
        conclusions.append(
            "Removing explicit reaction-energy loss kernels restores runtime completion: explicit reaction-energy losses dominate the lookup-floor failure."
        )
    else:
        conclusions.append(
            "Energy-loss-off still fails: electron birth dilution, transport, or another coupled mechanism can drive mean energy out of range without explicit reaction-energy sinks."
        )

    return {
        "runtime_success": success,
        "conclusions": conclusions,
        "claim": "DIAGNOSTIC_ONLY",
    }


def self_test() -> None:
    full, _ = _case_text(dt_s=2.5e-5, mode="full")
    assert s5r.audit_s5r_input(full)["status"] == "PASS"
    assert math.isclose(float(mp.get_parameter(full, "Executioner", "dt")), 2.5e-5)

    no_detach, _ = _case_text(dt_s=s5r.BASELINE_DT_S, mode="edetach_off")
    assert mp.get_parameter(no_detach, "FunctorMaterials/s5r_edetach_rate", "type") == "ADGenericFunctorMaterial"
    assert mp.get_parameter(no_detach, "FunctorMaterials/s5r_edetach_rate", "prop_names") == "'R_detach_Om'"
    assert mb.has_block(no_detach, "FVKernels/s5r_energy_edetach_om")

    no_losses, _ = _case_text(dt_s=s5r.BASELINE_DT_S, mode="energy_losses_off")
    for path in ENERGY_KERNEL_PATHS:
        assert not mb.has_block(no_losses, path)
    assert mb.has_block(no_losses, "FVKernels/s5r_electron_source")
    assert mb.has_block(no_losses, "FunctorMaterials/s5r_edetach_rate")

    print("S5R_P3_DIAGNOSTIC_MATRIX_SELFTEST_PASS")
    print("representative_acceptance_claim=false")


def run(args: argparse.Namespace) -> int:
    executable = resolve_executable(args.physics)
    validate_executable(executable)
    results_root = Path(args.results_root).resolve()
    root = _collision_safe_directory(
        results_root, f"issue192_s5r_p3_diagnostic_{_utc_stamp()}"
    )
    cases_root = root / "cases"
    logs_root = root / "logs"
    cases_root.mkdir(parents=True, exist_ok=True)
    logs_root.mkdir(parents=True, exist_ok=True)

    summary: dict[str, Any] = {
        "schema_version": 1,
        "issue": 192,
        "experiment": "s5r-p3-diagnostic-discriminator-matrix",
        "claim_boundary": "DIAGNOSTIC_ONLY_NOT_REPRESENTATIVE_ACCEPTANCE",
        "physics_opt": str(executable.resolve()),
        "cases": {},
        "status": "NOT_RUN",
    }

    for spec in CASE_SPECS:
        case_dir = cases_root / spec["name"]
        text, meta = _case_text(dt_s=float(spec["dt_s"]), mode=str(spec["mode"]))
        staged = _stage(case_dir, text=text, meta=meta)
        p2 = s5r._p2(
            executable,
            case_dir,
            logs_root / f"{spec['name']}_p2.log",
            timeout=args.timeout,
        )
        case_result: dict[str, Any] = {
            "dt_s": spec["dt_s"],
            "end_time_s": DIAGNOSTIC_END_TIME_S,
            "mode": spec["mode"],
            "question": spec["question"],
            "staged": staged,
            "p2": p2,
        }
        summary["cases"][spec["name"]] = case_result
        if p2["returncode"] != 0:
            summary["status"] = f"P2_FAIL_{str(spec['name']).upper()}"
            (root / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
            print(f"S5R_P3_DIAGNOSTIC_ROOT: {root}")
            print(f"S5R_P3_DIAGNOSTIC_STATUS: {summary['status']}")
            return 2

        runtime_log = logs_root / f"{spec['name']}_runtime.log"
        runtime = s5r._runtime(
            executable,
            case_dir,
            runtime_log,
            timeout=args.timeout,
        )
        case_result["runtime"] = runtime
        case_result["runtime_failure_facts"] = _error_facts(runtime_log)
        case_result["csv_snapshot"] = _csv_snapshot(case_dir)

    summary["interpretation"] = _interpret(summary["cases"])
    summary["status"] = "S5R_P3_DIAGNOSTIC_MATRIX_COMPLETE"
    summary_path = root / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(f"S5R_P3_DIAGNOSTIC_ROOT: {root}")
    print(f"S5R_P3_DIAGNOSTIC_STATUS: {summary['status']}")
    for line in summary["interpretation"]["conclusions"]:
        print(f"S5R_P3_DIAGNOSTIC_CONCLUSION: {line}")
    print(f"S5R_P3_DIAGNOSTIC_SUMMARY: {summary_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--physics")
    parser.add_argument("--results-root", type=Path)
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.timeout <= 0.0:
        parser.error("--timeout must be positive")
    if args.self_test:
        self_test()
        return 0
    if args.results_root is None:
        parser.error("--results-root is required")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
