"""Issue #31 transport/Poisson coupling recipe semantics.

This module owns experiment-specific input construction and runtime-physics /
discriminator interpretation shared by EVR1/EVR2. Runtime orchestration,
filesystem staging, measurement execution, checker subprocesses, and
executable policy remain in qpx_harness.
"""
from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any

from qpx_harness.moose.input import MooseInput, MooseInputError

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

KG_E_PARENT_RELATIVE = Path("tests/Issue2_electron_bulk_drift")
EVR1_BASELINE = {
    "dt": 1.0e-4,
    "status": "RUNTIME_FAIL_OR_NONCONVERGENCE",
    "signature": "DIVERGED_MAX_IT",
    "nonlinear_iterations": 80,
    "physics": "NOT_RUN",
    "source": "user-returned Issue31 EVR1 transport-only evidence",
}
DT_1E6 = 1.0e-6
DT_1E8 = 1.0e-8
EVR2_TERMINAL_CLASSES = {
    "TIMESTEP_STIFFNESS_CONFIRMED_RECOVERY_BY_1E6",
    "TIMESTEP_STIFFNESS_CONFIRMED_RECOVERY_ONLY_BY_1E8",
    "NONLINEAR_SCALING_SENSITIVITY_CONFIRMED",
    "T3_COUPLING_OR_JACOBIAN_FAIL_PERSISTS",
    "NONMONOTONIC_TIMESTEP_RESPONSE",
}


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


def configured_transport_input(
    base_text: str,
    *,
    dt: float,
    compute_scaling_once: bool,
) -> tuple[str, dict[str, Any]]:
    """Build the EVR2 transport control with only timestep/scaling changed."""
    try:
        transport_text, transport_meta = transport_only_input(base_text)
        transformed, param_meta = MooseInput(transport_text).replace_parameters(
            "Executioner",
            {
                "dt": f"{dt:.17g}",
                "end_time": f"{dt:.17g}",
                "compute_scaling_once": "true" if compute_scaling_once else "false",
            },
        )
    except (Issue31CouplingError, MooseInputError) as exc:
        raise Issue31CouplingError(f"transport configuration failed: {exc}") from exc

    if "potential_plasma" in transformed:
        raise Issue31CouplingError(
            "configured transport case unexpectedly references potential_plasma"
        )
    if "r30_e_diffusion" not in transformed or "n_e_solved" not in transformed:
        raise Issue31CouplingError(
            "configured transport case lost solved electron diffusion state"
        )
    return transformed, {
        "transport_transform": transport_meta,
        "executioner_parameters": param_meta,
        "dt": dt,
        "compute_scaling_once": compute_scaling_once,
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


def _result_status(case: dict[str, Any] | None) -> str | None:
    if not case:
        return None
    result = case.get("result")
    if not isinstance(result, dict):
        return None
    return result.get("validation", {}).get("status")


def _runtime_nonconvergence(case: dict[str, Any] | None) -> bool:
    return (
        _result_status(case) == "RUNTIME_FAIL_OR_NONCONVERGENCE"
        and (case or {}).get("failure", {}).get("signature")
        in {
            "DIVERGED_MAX_IT",
            "DIVERGED_LINE_SEARCH",
            "DIVERGED_FNORM_NAN",
            "NONLINEAR_DID_NOT_CONVERGE",
        }
    )


def _case_pass(case: dict[str, Any] | None) -> bool:
    return (
        _result_status(case) == "P2_PASS_P3_PASS"
        and isinstance((case or {}).get("physics"), dict)
        and (case or {})["physics"].get("status") == "PASS"
    )


def _kg_e_pass(case: dict[str, Any]) -> bool:
    return (
        _result_status(case) == "P2_PASS_P3_PASS"
        and case.get("canonical_checker", {}).get("status") == "PASS"
    )


def classify_evr2(
    kg_e: dict[str, Any],
    dt1e6: dict[str, Any] | None,
    dt1e8: dict[str, Any] | None,
    scaling1e8: dict[str, Any] | None,
) -> dict[str, Any]:
    """Classify the accepted EVR2 timestep/scaling discriminator branches."""
    if not _kg_e_pass(kg_e):
        status = _result_status(kg_e)
        cls = (
            "HARNESS_OR_CONSTRUCTION_FAIL"
            if status == "HARNESS_OR_CONSTRUCTION_FAIL"
            else "KNOWN_GOOD_ELECTRON_CONTROL_FAIL"
        )
        return {
            "class": cls,
            "reason": (
                "accepted real-qvt electron control did not pass on the current "
                "executable/environment"
            ),
        }

    for label, case in (("dt1e6", dt1e6), ("dt1e8", dt1e8)):
        if case is None:
            return {
                "class": "HARNESS_OR_CONSTRUCTION_FAIL",
                "reason": f"{label} was not run",
            }
        if _result_status(case) == "HARNESS_OR_CONSTRUCTION_FAIL":
            return {
                "class": "HARNESS_OR_CONSTRUCTION_FAIL",
                "reason": f"{label} failed before interpretable physics runtime",
            }
        if _result_status(case) == "P2_PASS_P3_PASS" and not _case_pass(case):
            return {
                "class": "PHYSICS_CHECK_FAIL",
                "reason": f"{label} runtime completed but transport physics checks failed",
            }

    p6 = _case_pass(dt1e6)
    p8 = _case_pass(dt1e8)

    if p6 and p8:
        return {
            "class": "TIMESTEP_STIFFNESS_CONFIRMED_RECOVERY_BY_1E6",
            "reason": (
                "EVR1 dt=1e-4 failed; unchanged transport/scaling recovers at "
                "both 1e-6 and 1e-8"
            ),
        }
    if (not p6) and p8 and _runtime_nonconvergence(dt1e6):
        return {
            "class": "TIMESTEP_STIFFNESS_CONFIRMED_RECOVERY_ONLY_BY_1E8",
            "reason": (
                "dt=1e-6 still fails by nonlinear convergence while dt=1e-8 "
                "recovers with unchanged scaling"
            ),
        }
    if p6 and (not p8):
        return {
            "class": "NONMONOTONIC_TIMESTEP_RESPONSE",
            "reason": (
                "dt=1e-6 passes but smaller dt=1e-8 does not; simple "
                "timestep-stiffness explanation is insufficient"
            ),
        }

    if _runtime_nonconvergence(dt1e6) and _runtime_nonconvergence(dt1e8):
        if scaling1e8 is None:
            return {
                "class": "SCALING_BRANCH_REQUIRED",
                "reason": "both smaller timesteps remain nonlinear-convergence failures",
            }
        if _result_status(scaling1e8) == "HARNESS_OR_CONSTRUCTION_FAIL":
            return {
                "class": "HARNESS_OR_CONSTRUCTION_FAIL",
                "reason": (
                    "scaling discriminator failed before interpretable physics runtime"
                ),
            }
        if _result_status(scaling1e8) == "P2_PASS_P3_PASS" and not _case_pass(
            scaling1e8
        ):
            return {
                "class": "PHYSICS_CHECK_FAIL",
                "reason": "scaling discriminator converged but physics checks failed",
            }
        if _case_pass(scaling1e8):
            return {
                "class": "NONLINEAR_SCALING_SENSITIVITY_CONFIRMED",
                "reason": (
                    "dt=1e-8 fails with current scaling policy and recovers when "
                    "only compute_scaling_once changes to true"
                ),
            }
        if _runtime_nonconvergence(scaling1e8):
            return {
                "class": "T3_COUPLING_OR_JACOBIAN_FAIL_PERSISTS",
                "reason": (
                    "accepted electron control passes, but T3 fails at 1e-6 and "
                    "1e-8 and does not recover with accepted scaling-once policy"
                ),
            }

    return {
        "class": "UNRESOLVED_RUNTIME_RESPONSE",
        "reason": (
            "observed result signature does not match a predeclared discriminator branch"
        ),
    }
