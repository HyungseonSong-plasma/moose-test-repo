"""Issue #43 fast electron + bulk-Poisson relaxation recipe semantics.

This module owns experiment-specific input construction and relaxation-evidence
interpretation. Runtime orchestration, filesystem staging, and executable policy
remain in qpx_harness.
"""
from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any

from qpx_harness.moose.input import MooseInput, MooseInputError
from qpx_harness.analysis.scale_audit import DEFAULT_PRESSURE

MEAN_ENERGY_EV = 5.73276
PERTURBATION_FRACTION = 1.0e-6
RELAX_TOL = 1.0e-4
INVENTORY_REL_TOL = 1.0e-6
CHARGE_REL_TOL = 1.0e-6
E_CHARGE = 1.602176634e-19
EPS0 = 8.8541878128e-12
DT_FEEDBACK_BASE = 1.0e-13
DT_FEEDBACK_SMALL = 1.0e-14
DT_FEEDBACK_LARGE = 1.0e-12

REQUIRED_COLUMNS = (
    "time",
    "n_min",
    "n_max",
    "inventory",
    "domain_volume",
    "r43_n_l2",
    "r43_phi_l2",
    "r43_phi_min",
    "r43_phi_max",
    "r43_phi_integral",
    "r43_charge_integral",
    "r43_background_inventory",
)


def _find_block(input_file: MooseInput, path: str):
    try:
        return input_file.require_block(path)
    except MooseInputError as exc:
        raise ValueError(str(exc)) from exc


def build_fast_relaxation_input(
    text: str,
    *,
    dt: float = DT_FEEDBACK_BASE,
    perturbation_fraction: float = PERTURBATION_FRACTION,
) -> str:
    if dt <= 0.0:
        raise ValueError("dt must be positive")
    if perturbation_fraction <= 0.0:
        raise ValueError("perturbation_fraction must be positive")

    doc = MooseInput.parse(text)
    executioner = _find_block(doc, "Executioner")
    executioner.set_parameter("dt", f"{dt:.16g}")
    executioner.set_parameter("end_time", f"{(20.0 * dt):.16g}")
    executioner.set_parameter("num_steps", "20")

    variables = _find_block(doc, "Variables")
    electron = variables.child("n_e") or variables.child("electron")
    if electron is None:
        raise ValueError("electron variable block not found")
    electron.set_parameter("initial_condition", f"{1.0 + perturbation_fraction:.16g}")

    return doc.render()


def _float(row: dict[str, str], key: str) -> float:
    try:
        return float(row[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"missing/invalid CSV column {key}") from exc


def read_relaxation_csv(path: Path) -> list[dict[str, float]]:
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or ())
        missing = [name for name in REQUIRED_COLUMNS if name not in columns]
        if missing:
            raise ValueError("missing required relaxation columns: " + ", ".join(missing))
        rows = [
            {name: _float(row, name) for name in REQUIRED_COLUMNS}
            for row in reader
        ]
    if not rows:
        raise ValueError("relaxation CSV is empty")
    return rows


def summarize_relaxation(rows: list[dict[str, float]]) -> dict[str, Any]:
    first = rows[0]
    final = rows[-1]
    background_inventory = final["r43_background_inventory"]
    if background_inventory == 0.0:
        raise ValueError("background inventory is zero")

    inventory_rel = abs(final["inventory"] - background_inventory) / abs(background_inventory)
    charge_scale = max(abs(background_inventory * E_CHARGE), 1.0e-300)
    charge_rel = abs(final["r43_charge_integral"]) / charge_scale
    n0 = abs(first["r43_n_l2"])
    nf = abs(final["r43_n_l2"])
    relaxation_ratio = nf / max(n0, 1.0e-300)

    return {
        "rows": len(rows),
        "final_time": final["time"],
        "n_min": final["n_min"],
        "n_max": final["n_max"],
        "inventory_relative_error": inventory_rel,
        "charge_relative_error": charge_rel,
        "relaxation_ratio": relaxation_ratio,
        "phi_l2": abs(final["r43_phi_l2"]),
        "phi_min": final["r43_phi_min"],
        "phi_max": final["r43_phi_max"],
        "phi_integral": final["r43_phi_integral"],
    }


def classify_relaxation(summary: dict[str, Any]) -> dict[str, Any]:
    checks = {
        "positive_density": summary["n_min"] > 0.0,
        "inventory_closed": summary["inventory_relative_error"] <= INVENTORY_REL_TOL,
        "charge_closed": summary["charge_relative_error"] <= CHARGE_REL_TOL,
        "relaxes": summary["relaxation_ratio"] <= RELAX_TOL,
        "finite_potential": all(
            math.isfinite(float(summary[key]))
            for key in ("phi_l2", "phi_min", "phi_max", "phi_integral")
        ),
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "summary": summary,
    }


def analyze_relaxation_csv(path: Path) -> dict[str, Any]:
    return classify_relaxation(summarize_relaxation(read_relaxation_csv(path)))


__all__ = [
    "CHARGE_REL_TOL",
    "DT_FEEDBACK_BASE",
    "DT_FEEDBACK_LARGE",
    "DT_FEEDBACK_SMALL",
    "INVENTORY_REL_TOL",
    "MEAN_ENERGY_EV",
    "PERTURBATION_FRACTION",
    "RELAX_TOL",
    "REQUIRED_COLUMNS",
    "analyze_relaxation_csv",
    "build_fast_relaxation_input",
    "classify_relaxation",
    "read_relaxation_csv",
    "summarize_relaxation",
]
