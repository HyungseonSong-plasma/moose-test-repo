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
from qpx_harness.adapters.moose import log as moose_log
from qpx_harness.adapters.moose import parameters as mp
from qpx_harness.adapters.moose import petsc_options as po
from qpx_harness.petsc import ksp
from qpx_harness.petsc import log as petsc_log

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


def _positive_floats(text: str) -> list[float]:
    values: list[float] = []
    for token in text.replace(",", " ").split():
        try:
            value = float(token)
        except ValueError:
            continue
        if math.isfinite(value) and value > 0.0:
            values.append(value)
    return values


def _parse_singular_values(text: str) -> list[dict[str, float]]:
    rows: list[dict[str, float]] = []
    for raw in text.splitlines():
        lower = raw.lower()
        if "singular" not in lower and "sigma" not in lower:
            continue
        values = _positive_floats(raw)
        if len(values) < 2:
            continue
        sigma_max = max(values[-2:])
        sigma_min = min(values[-2:])
        if sigma_min <= 0.0:
            continue
        rows.append(
            {
                "sigma_max": sigma_max,
                "sigma_min": sigma_min,
                "sigma_max_over_min": sigma_max / sigma_min,
            }
        )
    return rows


def _conditioning_proxy(text: str) -> dict[str, Any]:
    rows = _parse_singular_values(text)
    if not rows:
        return {
            "available": False,
            "rows": [],
            "max_sigma_max_over_min": None,
        }
    return {
        "available": True,
        "rows": rows,
        "max_sigma_max_over_min": max(row["sigma_max_over_min"] for row in rows),
    }


def _ksp_residual_fidelity(text: str) -> dict[str, Any]:
    rows = ksp.parse_monitor_true_residual(text)
    audit = ksp.residual_fidelity_audit(
        rows,
        restart=30,
        ratio_threshold=RESIDUAL_FIDELITY_RATIO_THRESHOLD,
    )
    return {
        "available": bool(rows),
        "rows": rows,
        **audit,
    }


def _solver_reasons(text: str) -> dict[str, Any]:
    return {
        "linear": [item.__dict__ for item in petsc_log.parse_linear_solve_terminations(text)],
        "nonlinear": [item.__dict__ for item in petsc_log.parse_nonlinear_solve_terminations(text)],
    }


def _scaling_facts(text: str) -> dict[str, Any]:
    blocks = moose_log.parse_automatic_scaling_factors(text)
    selected: list[dict[str, float]] = []
    for block in blocks:
        row: dict[str, float] = {}
        for name in SCALING_VARIABLES:
            value = block.get(name)
            if value is not None and math.isfinite(value):
                row[name] = value
        if row:
            selected.append(row)
    ratios: list[float] = []
    for row in selected:
        positive = [abs(value) for value in row.values() if value != 0.0]
        if len(positive) >= 2:
            ratios.append(max(positive) / min(positive))
    return {
        "blocks": blocks,
        "selected": selected,
        "max_selected_ratio": max(ratios) if ratios else None,
    }


def _ensure_required_flags(text: str) -> None:
    missing = [flag for flag in REQUIRED_FLAGS if flag not in text]
    if missing:
        raise RuntimeError(f"missing required EVR3 PETSc flags: {missing}")
    present_forbidden = [flag for flag in FORBIDDEN_FLAGS if flag in text]
    if present_forbidden:
        raise RuntimeError(f"forbidden EVR3 PETSc flags present: {present_forbidden}")


def _build_input(source: Path, output: Path) -> dict[str, Any]:
    text = source.read_text()
    _ensure_required_flags(text)
    document = mp.load_input(source)
    block = document.find_block("Executioner")
    if block is None:
        raise RuntimeError("Issue45 EVR3 source lacks [Executioner]")
    current = mp.get_parameter(block, "petsc_options_iname") or ""
    current_values = mp.get_parameter(block, "petsc_options_value") or ""
    inames, values = po.parse_name_value_options(current, current_values)
    merged_names = list(inames)
    merged_values = list(values)
    for name, value in EXPECTED_NAME_VALUE_PAIRS:
        if name in merged_names:
            idx = merged_names.index(name)
            merged_values[idx] = value
        else:
            merged_names.append(name)
            merged_values.append(value)
    mp.set_parameter(block, "petsc_options_iname", "'" + " ".join(merged_names) + "'")
    mp.set_parameter(block, "petsc_options_value", "'" + " ".join(merged_values) + "'")
    output.write_text(document.render())
    return {"input": str(output), "petsc_names": merged_names, "petsc_values": merged_values}


def _run(args: argparse.Namespace) -> int:
    executable = resolve_executable(args.qpx)
    validate_executable(executable)
    source = Path(args.input).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    result_root = Path(args.results_root).expanduser().resolve()
    result_root.mkdir(parents=True, exist_ok=True)
    input_path = result_root / f"{STEM}.i"
    build = _build_input(source, input_path)
    result = run_qpx(executable, input_path, cwd=result_root)
    log_path = result_root / f"{STEM}.log"
    log_path.write_text(result.stdout + result.stderr)
    text = log_path.read_text(errors="replace")
    payload = {
        "issue": ISSUE,
        "work_issue": WORK_ISSUE,
        "experiment": "EVR3",
        "run": {
            "returncode": result.returncode,
            "input": str(input_path),
            "log": str(log_path),
            **build,
        },
        "solver_reasons": _solver_reasons(text),
        "scaling": _scaling_facts(text),
        "conditioning_proxy": _conditioning_proxy(text),
        "residual_fidelity": _ksp_residual_fidelity(text),
    }
    out = result_root / f"{STEM}.json"
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(out)
    return 0 if result.returncode == 0 else result.returncode


def _self_test() -> int:
    parsed = _parse_singular_values(
        "KSP singular values sigma_max=1e3 sigma_min=1e-2\n"
        "KSP singular values 2e3 4e-3\n"
    )
    assert len(parsed) == 2
    assert parsed[0]["sigma_max_over_min"] == 1e5
    assert parsed[1]["sigma_max_over_min"] == 5e5
    print("ISSUE45_EVR3_DISCRIMINATOR_SELFTEST: PASS")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qpx")
    parser.add_argument("--input", default=str(orch.DEFAULT_CASE / "input.i"))
    parser.add_argument("--results-root", default=str(ROOT / "temp/results/issue45_evr3"))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return _self_test()
    return _run(args)


if __name__ == "__main__":
    raise SystemExit(main())
