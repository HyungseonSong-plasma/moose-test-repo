"""Canonical runtime-evidence adapters for electron-inventory closure."""
from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any

from recipes import issue45_inventory_constraint as constraint_policy

from qpx_harness.adapters.moose.electron_inventory.constants import LAMBDA_VARIABLE, RUNTIME_COLUMNS
from qpx_harness.domains.plasma.electron_inventory import ElectronInventoryNullspaceError


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
    result = constraint_policy.evaluate_runtime_case_data(
        target=target,
        returncode=returncode,
        converged_marker=converged_marker,
        diagnostic=diagnostic,
        row=row,
    )
    if "aggregate_consistency_relative_error" in result:
        result = {
            **result,
            "aggregate_consistency_rel_error": result[
                "aggregate_consistency_relative_error"
            ],
        }
    return result


def _evaluate_runtime_pair(
    c0: dict[str, Any], c1: dict[str, Any], *, target0: float, target1: float
) -> dict[str, Any]:
    try:
        return constraint_policy.evaluate_runtime_pair(
            c0,
            c1,
            target0=target0,
            target1=target1,
        )
    except constraint_policy.Issue45InventoryConstraintError as exc:
        raise ElectronInventoryNullspaceError(str(exc)) from exc


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
