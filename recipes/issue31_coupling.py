"""Issue #31 transport/Poisson coupling recipe semantics.

This module owns experiment-specific input construction and r29 runtime-physics
interpretation shared by EVR1/EVR2. Runtime orchestration, filesystem staging,
measurement execution, and executable policy remain in qpx_harness.
"""
from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any

from qpx_harness.moose_input import MooseInput, MooseInputError

BASE_INPUT_RELATIVE = Path(
    "archive/Issue29_monolithic_performance_bound/monolithic_q0_reference.i"
)
DEFAULT_ASSET_CASE_RELATIVE = Path(
    "temp/tests/Issue22_qvt_transient_species_accumulation"
)
SOURCE_RELATIVE = Path("src/materials/QPXThermalDiffusionMaterial.C")
SPECIES = ("O2s", "O2p", "O", "Om", "Op", "Os")
TRANSPORT_REMOVE_PATHS = (
    "Variables/potential_plasma",
    "FVKernels/r30_phi_diffusion",
    "FVKernels/r30_phi_charge_source",
    "FVBCs/r30_phi_plasma_metal",
    "FVBCs/r30_phi_plasma_electrode",
    "FVBCs/r30_phi_plasma_right",
    "FVBCs/r30_phi_inlet",
    "FVBCs/r30_phi_outlet",
    "Postprocessors/r29_phi_min",
    "Postprocessors/r29_phi_max",
    "Postprocessors/r29_phi_integral",
)
E_CHARGE = 1.602176634e-19
SUM_W_TOL = 1.0e-10
BOUND_TOL = 1.0e-10
CHARGE_REL_TOL = 1.0e-3
PHI_NONTRIVIAL_TOL = 1.0e-14


class Issue31CouplingError(RuntimeError):
    pass


def transport_only_input(base_text: str) -> tuple[str, dict[str, Any]]:
    """Remove Poisson state while retaining the accepted solved-electron control."""
    try:
        transformed, removed = MooseInput(base_text).remove_paths(TRANSPORT_REMOVE_PATHS)
    except MooseInputError as exc:
        raise Issue31CouplingError(
            f"transport-only structural transform failed: {exc}"
        ) from exc

    if "potential_plasma" in transformed:
        raise Issue31CouplingError(
            "transport-only transform left a potential_plasma reference; "
            "refuse to run an ambiguously coupled control"
        )
    required = ("n_e_solved", "r30_e_time", "r30_e_diffusion", "r30_charge_density")
    missing = [token for token in required if token not in transformed]
    if missing:
        raise Issue31CouplingError(
            "transport-only transform removed required electron/charge state: "
            + ", ".join(missing)
        )
    return transformed, {
        "removed_paths": list(TRANSPORT_REMOVE_PATHS),
        "removed_spans": removed,
        "retained_required_tokens": list(required),
    }


def _float(row: dict[str, str], key: str) -> float:
    try:
        value = float(row[key])
    except (KeyError, ValueError) as exc:
        raise Issue31CouplingError(f"missing/non-numeric physics column {key!r}") from exc
    if not math.isfinite(value):
        raise Issue31CouplingError(f"non-finite physics value {key}={value}")
    return value


def required_physics_columns(*, monolithic: bool) -> set[str]:
    required = {
        "time",
        "r29_ne_min",
        "r29_ne_max",
        "r29_charge_min",
        "r29_charge_max",
        "r29_charge_integral",
        "r29_heavy_charge_number_integral",
        "r29_electron_charge_number_integral",
        "r29_sum_w_min",
        "r29_sum_w_max",
    }
    for species in SPECIES:
        required.add(f"r29_w_{species}_min")
        required.add(f"r29_w_{species}_max")
    if monolithic:
        required.update({"r29_phi_min", "r29_phi_max", "r29_phi_integral"})
    return required


def physics_csv(case_dir: Path, *, monolithic: bool) -> tuple[Path, dict[str, str]]:
    """Select one deterministic r29-observable CSV and its last solved-time row."""
    required = required_physics_columns(monolithic=monolithic)
    candidates: list[tuple[Path, list[dict[str, str]]]] = []
    for path in sorted(case_dir.glob("*.csv")):
        try:
            with path.open(newline="") as handle:
                rows = list(csv.DictReader(handle))
        except (OSError, csv.Error):
            continue
        if rows and required.issubset(rows[0].keys()):
            candidates.append((path, rows))

    if not candidates:
        raise Issue31CouplingError(
            "no runtime physics CSV contains the required r29 observables"
        )

    preferred = [item for item in candidates if item[0].name == "input_out.csv"]
    path, rows = preferred[0] if preferred else candidates[0]
    physical = [row for row in rows if _float(row, "time") > 1.0e-15]
    if not physical:
        raise Issue31CouplingError(f"no positive solved-time row in {path}")
    return path, physical[-1]


def physics_check(case_dir: Path, *, monolithic: bool) -> dict[str, Any]:
    """Evaluate the accepted Issue31 r29 runtime-physics contract."""
    path, row = physics_csv(case_dir, monolithic=monolithic)
    checks: dict[str, bool] = {}

    ne_min = _float(row, "r29_ne_min")
    ne_max = _float(row, "r29_ne_max")
    checks["electron_nonnegative"] = ne_min >= -BOUND_TOL and ne_max >= ne_min

    sum_min = _float(row, "r29_sum_w_min")
    sum_max = _float(row, "r29_sum_w_max")
    checks["constrained_sum_unity"] = (
        abs(sum_min - 1.0) <= SUM_W_TOL and abs(sum_max - 1.0) <= SUM_W_TOL
    )

    species_values: dict[str, dict[str, float]] = {}
    for species in SPECIES:
        low = _float(row, f"r29_w_{species}_min")
        high = _float(row, f"r29_w_{species}_max")
        species_values[species] = {"min": low, "max": high}
        checks[f"{species}_bounds"] = (
            low >= -BOUND_TOL and high <= 1.0 + BOUND_TOL and high >= low
        )

    charge_min = _float(row, "r29_charge_min")
    charge_max = _float(row, "r29_charge_max")
    charge_integral = _float(row, "r29_charge_integral")
    heavy_number = _float(row, "r29_heavy_charge_number_integral")
    electron_number = _float(row, "r29_electron_charge_number_integral")
    expected_charge = E_CHARGE * (heavy_number + electron_number)
    charge_scale = max(abs(charge_integral), abs(expected_charge), 1.0e-300)
    charge_rel = abs(charge_integral - expected_charge) / charge_scale
    checks["charge_finite_ordered"] = charge_max >= charge_min
    checks["charge_integral_identity"] = charge_rel <= CHARGE_REL_TOL

    phi: dict[str, float] | None = None
    if monolithic:
        phi = {
            "min": _float(row, "r29_phi_min"),
            "max": _float(row, "r29_phi_max"),
            "integral": _float(row, "r29_phi_integral"),
        }
        checks["potential_ordered"] = phi["max"] >= phi["min"]
        checks["potential_nontrivial"] = (
            max(abs(phi["min"]), abs(phi["max"])) > PHI_NONTRIVIAL_TOL
        )

    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "csv": str(path),
        "time": _float(row, "time"),
        "checks": checks,
        "electron": {"min": ne_min, "max": ne_max},
        "sum_w": {"min": sum_min, "max": sum_max},
        "species": species_values,
        "charge": {
            "min": charge_min,
            "max": charge_max,
            "integral": charge_integral,
            "expected_integral": expected_charge,
            "relative_identity_error": charge_rel,
        },
        "potential": phi,
    }
