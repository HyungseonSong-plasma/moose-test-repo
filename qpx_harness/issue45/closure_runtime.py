"""Issue45 constrained-closure runtime evidence parsing and acceptance."""
from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any

from .constants import (
    CLOSURE_DELTA_REL_TOL,
    CLOSURE_TARGET_REL_TOL,
    INVENTORY_CONSISTENCY_REL_TOL,
    LAMBDA_VARIABLE,
    RUNTIME_COLUMNS,
)
from .errors import ElectronInventoryNullspaceError


def _synthetic_runtime_row(target: float) -> dict[str, float]:
    volume = 0.05
    return {
        "n_avg": target,
        "inventory": target * volume,
        "domain_volume": volume,
        "n_min": target * 0.99,
        "n_max": target * 1.01,
        "r43_phi_l2": 0.08,
        "r43_phi_min": -0.7,
        "r43_phi_max": 0.05,
        "r43_charge_integral": 0.0,
        "r43_charge_min": -1.0e-8,
        "r43_charge_max": 2.0e-9,
    }


def _evaluate_runtime_case_data(
    *,
    target: float,
    returncode: int,
    converged_marker: bool,
    diagnostic: dict[str, Any],
    row: dict[str, float] | None,
) -> dict[str, Any]:
    zero_pivot = diagnostic.get("pc_failure_reason") in {
        "FACTOR_NUMERIC_ZEROPIVOT",
        "FACTOR_STRUCT_ZEROPIVOT",
    }
    nonfinite_runtime = bool(diagnostic.get("nonfinite_residuals")) or (
        diagnostic.get("nonlinear_reason") == "DIVERGED_FUNCTION_NANORINF"
    )
    if returncode != 0:
        return {
            "status": "HOLD",
            "class": "SECONDARY_SINGULAR_MODE_SUSPECTED" if zero_pivot else "CONSTRAINED_STEADY_SOLVER_FAIL",
            "reason": (
                "constrained steady factorization still reports a zero pivot after explicit inventory closure"
                if zero_pivot
                else "constrained steady runtime did not solve successfully"
            ),
            "target": target,
            "returncode": returncode,
            "diagnostic": diagnostic,
        }
    if not converged_marker or nonfinite_runtime:
        return {
            "status": "HOLD",
            "class": "CLOSURE_EVIDENCE_INSUFFICIENT",
            "reason": "runtime return code was zero but finite accepted nonlinear convergence evidence is incomplete",
            "target": target,
            "returncode": returncode,
            "diagnostic": diagnostic,
        }
    residuals = diagnostic.get("variable_residuals") or []
    if not residuals:
        return {
            "status": "HOLD",
            "class": "CLOSURE_EVIDENCE_INSUFFICIENT",
            "reason": "per-variable nonlinear residual evidence is missing",
            "target": target,
            "diagnostic": diagnostic,
        }
    final_residuals = residuals[-1]
    required_residual_vars = ("n_e", "potential_plasma")
    residual_finite = all(
        name in final_residuals and math.isfinite(float(final_residuals[name]))
        for name in required_residual_vars
    )
    if not residual_finite:
        return {
            "status": "HOLD",
            "class": "CLOSURE_EVIDENCE_INSUFFICIENT",
            "reason": "final electron/Poisson per-variable residual evidence is missing or non-finite",
            "target": target,
            "diagnostic": diagnostic,
        }
    if row is None or any(name not in row for name in RUNTIME_COLUMNS):
        return {
            "status": "HOLD",
            "class": "CLOSURE_EVIDENCE_INSUFFICIENT",
            "reason": "final CSV does not contain the required closure observables",
            "target": target,
            "diagnostic": diagnostic,
        }
    if not all(math.isfinite(float(row[name])) for name in RUNTIME_COLUMNS):
        return {
            "status": "HOLD",
            "class": "CLOSURE_EVIDENCE_INSUFFICIENT",
            "reason": "one or more final closure observables are non-finite",
            "target": target,
            "diagnostic": diagnostic,
        }

    volume = float(row["domain_volume"])
    avg = float(row["n_avg"])
    inventory = float(row["inventory"])
    if volume <= 0.0 or float(row["n_min"]) <= 0.0:
        return {
            "status": "HOLD",
            "class": "CONSTRAINT_TARGET_TRACKING_FAIL",
            "reason": "constrained solution has non-positive domain volume or electron-density minimum",
            "target": target,
            "observables": row,
            "diagnostic": diagnostic,
        }

    target_inventory = target * volume
    avg_rel_error = abs(avg - target) / abs(target)
    inventory_rel_error = abs(inventory - target_inventory) / abs(target_inventory)
    aggregate_consistency_rel_error = abs(avg - inventory / volume) / max(abs(target), 1.0e-300)
    tracking_pass = (
        avg_rel_error <= CLOSURE_TARGET_REL_TOL
        and inventory_rel_error <= CLOSURE_TARGET_REL_TOL
        and aggregate_consistency_rel_error <= INVENTORY_CONSISTENCY_REL_TOL
    )
    return {
        "status": "PASS" if tracking_pass else "HOLD",
        "class": "CONSTRAINED_STEADY_CASE_PASS" if tracking_pass else "CONSTRAINT_TARGET_TRACKING_FAIL",
        "reason": (
            "constrained steady solution converged and its electron average/inventory track the declared target"
            if tracking_pass
            else "constrained steady solution converged but the electron average/inventory does not satisfy the declared target contract"
        ),
        "target": target,
        "target_inventory": target_inventory,
        "target_relative_tolerance": CLOSURE_TARGET_REL_TOL,
        "inventory_consistency_relative_tolerance": INVENTORY_CONSISTENCY_REL_TOL,
        "average_relative_error": avg_rel_error,
        "inventory_relative_error": inventory_rel_error,
        "aggregate_consistency_rel_error": aggregate_consistency_rel_error,
        "observables": row,
        "final_variable_residuals": final_residuals,
        "diagnostic": diagnostic,
    }


def _evaluate_runtime_pair(
    c0: dict[str, Any], c1: dict[str, Any], *, target0: float, target1: float
) -> dict[str, Any]:
    classes = {c0.get("class"), c1.get("class")}
    if "SECONDARY_SINGULAR_MODE_SUSPECTED" in classes:
        return {
            "status": "HOLD",
            "class": "SECONDARY_SINGULAR_MODE_SUSPECTED",
            "reason": "a zero-pivot signature persists after explicit inventory closure",
        }
    if "CONSTRAINED_STEADY_SOLVER_FAIL" in classes:
        return {
            "status": "HOLD",
            "class": "CONSTRAINED_STEADY_SOLVER_FAIL",
            "reason": "at least one constrained steady target case did not solve",
        }
    if "CONSTRAINT_TARGET_TRACKING_FAIL" in classes:
        return {
            "status": "HOLD",
            "class": "CONSTRAINT_TARGET_TRACKING_FAIL",
            "reason": "at least one converged target case failed the predeclared inventory tracking contract",
        }
    if c0.get("status") != "PASS" or c1.get("status") != "PASS":
        return {
            "status": "HOLD",
            "class": "CLOSURE_EVIDENCE_INSUFFICIENT",
            "reason": "at least one target case lacks complete closure evidence",
        }

    avg0 = float(c0["observables"]["n_avg"])
    avg1 = float(c1["observables"]["n_avg"])
    requested_delta = target1 - target0
    observed_delta = avg1 - avg0
    if requested_delta == 0.0:
        raise ElectronInventoryNullspaceError("runtime target pair must have nonzero separation")
    delta_rel_error = abs(observed_delta - requested_delta) / abs(requested_delta)
    if delta_rel_error > CLOSURE_DELTA_REL_TOL:
        return {
            "status": "HOLD",
            "class": "CONSTRAINT_TARGET_TRACKING_FAIL",
            "reason": "C0/C1 observed electron-average shift does not track the requested target shift",
            "requested_delta": requested_delta,
            "observed_delta": observed_delta,
            "delta_relative_error": delta_rel_error,
            "delta_relative_tolerance": CLOSURE_DELTA_REL_TOL,
        }
    return {
        "status": "PASS",
        "class": "CONSTRAINED_QUASISTEADY_RUNTIME_PASS",
        "reason": "both constrained steady target cases converge, satisfy their declared inventory targets, and the observed electron-average shift tracks the requested target shift",
        "requested_delta": requested_delta,
        "observed_delta": observed_delta,
        "delta_relative_error": delta_rel_error,
        "delta_relative_tolerance": CLOSURE_DELTA_REL_TOL,
    }


def _find_runtime_csv(case_dir: Path) -> Path:
    candidates: list[Path] = []
    for path in sorted(case_dir.glob("*.csv")):
        try:
            with path.open(newline="") as handle:
                fields = set(csv.DictReader(handle).fieldnames or ())
        except (OSError, csv.Error):
            continue
        if set(RUNTIME_COLUMNS).issubset(fields):
            candidates.append(path)
    if not candidates:
        raise ElectronInventoryNullspaceError(
            f"no runtime CSV contains the required closure observables in {case_dir}"
        )
    preferred = case_dir / "input_out.csv"
    return preferred if preferred in candidates else candidates[0]


def _read_final_runtime_row(path: Path) -> dict[str, float]:
    try:
        with path.open(newline="") as handle:
            raw_rows = list(csv.DictReader(handle))
    except (OSError, csv.Error) as exc:
        raise ElectronInventoryNullspaceError(
            f"cannot read runtime CSV {path}: {exc}"
        ) from exc
    if not raw_rows:
        raise ElectronInventoryNullspaceError(f"runtime CSV is empty: {path}")
    raw = raw_rows[-1]
    row: dict[str, float] = {}
    for name in RUNTIME_COLUMNS:
        try:
            row[name] = float(raw[name])
        except (KeyError, ValueError) as exc:
            raise ElectronInventoryNullspaceError(
                f"invalid/missing {name} in final runtime CSV row: {path}"
            ) from exc
    if LAMBDA_VARIABLE in raw:
        try:
            value = float(raw[LAMBDA_VARIABLE])
            if math.isfinite(value):
                row[LAMBDA_VARIABLE] = value
        except (TypeError, ValueError):
            pass
    return row
