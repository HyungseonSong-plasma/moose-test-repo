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

from qpx_harness.moose_input import MooseInput, MooseInputError
from qpx_harness.scale_audit import DEFAULT_PRESSURE

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
    "r43_charge_min",
    "r43_charge_max",
)

STATE_COLUMNS = (
    "r43_n_l2",
    "n_min",
    "n_max",
    "r43_phi_l2",
    "r43_phi_min",
    "r43_phi_max",
)


class Issue43FastRelaxationError(RuntimeError):
    pass


def _fmt(value: float) -> str:
    return f"{value:.17g}"


def _insert_top_level_before(text: str, marker: str, block: str) -> str:
    needle = f"\n[{marker}]\n"
    if text.count(needle) != 1:
        raise Issue43FastRelaxationError(
            f"expected one top-level [{marker}] marker, found {text.count(needle)}"
        )
    payload = block if block.endswith("\n") else block + "\n"
    return text.replace(needle, "\n" + payload + needle, 1)


def build_fast_input(
    base_text: str,
    *,
    gas_temperature: float,
    electron_density: float,
    dt: float,
    end_time: float,
    radial_span: float,
) -> tuple[str, dict[str, Any]]:
    """Construct the Issue43 frozen-heavy electron/Poisson relaxation input."""
    if radial_span <= 0 or dt <= 0 or end_time <= 0:
        raise Issue43FastRelaxationError(
            "radial span, dt and end_time must be positive"
        )

    try:
        text, constants_meta = MooseInput(base_text).replace_parameters(
            "FunctorMaterials/electron_constants",
            {
                "prop_values": (
                    f"'{_fmt(MEAN_ENERGY_EV)} "
                    f"{_fmt(DEFAULT_PRESSURE)} "
                    f"{_fmt(gas_temperature)} 1.0'"
                )
            },
        )
        text, drift_meta = MooseInput(text).replace_parameters(
            "FVKernels/drift", {"potential": "potential_plasma"}
        )
        text, _ = MooseInput(text).insert_before_close(
            "Variables",
            """  [potential_plasma]
    type = MooseVariableFVReal
    initial_condition = 0
    block = plasma
  []""",
        )

        e_over_eps0 = E_CHARGE / EPS0
        background_expr = (
            f"{_fmt(electron_density)}*"
            f"(1.0+{_fmt(PERTURBATION_FRACTION)}*"
            f"cos(2*pi*x/{_fmt(radial_span)}))"
        )
        text, _ = MooseInput(text).insert_before_close(
            "FunctorMaterials",
            f"""  [r43_background]
    type = ADParsedFunctorMaterial
    property_name = r43_positive_background
    expression = '{background_expr}'
    block = plasma
  []
  [r43_relative_permittivity]
    type = ADGenericFunctorMaterial
    prop_names = 'r43_relative_permittivity'
    prop_values = '1.0'
    block = plasma
  []
  [r43_charge_number_density]
    type = ADParsedFunctorMaterial
    property_name = r43_charge_number_density
    functor_names = 'r43_positive_background n_e'
    functor_symbols = 'nb nelec'
    expression = 'nb-nelec'
    block = plasma
  []
  [r43_charge_density]
    type = ADParsedFunctorMaterial
    property_name = r43_charge_density
    functor_names = 'r43_charge_number_density'
    functor_symbols = 'qnum'
    expression = '{_fmt(E_CHARGE)}*qnum'
    block = plasma
  []
  [r43_poisson_source]
    type = ADParsedFunctorMaterial
    property_name = r43_poisson_source
    functor_names = 'r43_charge_number_density'
    functor_symbols = 'qnum'
    expression = '{_fmt(e_over_eps0)}*qnum'
    block = plasma
  []""",
        )
        text, _ = MooseInput(text).insert_before_close(
            "FVKernels",
            """  [r43_phi_diffusion]
    type = FVDiffusion
    variable = potential_plasma
    coeff = r43_relative_permittivity
    block = plasma
  []
  [r43_phi_charge_source]
    type = FVCoupledForce
    variable = potential_plasma
    v = r43_poisson_source
    coef = 1
    block = plasma
  []""",
        )
        text, _ = MooseInput(text).insert_before_close(
            "Postprocessors",
            """  [r43_n_l2]
    type = ElementL2Norm
    variable = n_e
    block = plasma
  []
  [r43_phi_l2]
    type = ElementL2Norm
    variable = potential_plasma
    block = plasma
  []
  [r43_phi_min]
    type = ADElementExtremeFunctorValue
    functor = potential_plasma
    value_type = min
    block = plasma
  []
  [r43_phi_max]
    type = ADElementExtremeFunctorValue
    functor = potential_plasma
    value_type = max
    block = plasma
  []
  [r43_phi_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = potential_plasma
    block = plasma
  []
  [r43_charge_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = r43_charge_density
    block = plasma
  []
  [r43_background_inventory]
    type = ADElementIntegralFunctorPostprocessor
    functor = r43_positive_background
    block = plasma
  []
  [r43_charge_min]
    type = ADElementExtremeFunctorValue
    functor = r43_charge_density
    value_type = min
    block = plasma
  []
  [r43_charge_max]
    type = ADElementExtremeFunctorValue
    functor = r43_charge_density
    value_type = max
    block = plasma
  []""",
        )
        text, execution_meta = MooseInput(text).replace_parameters(
            "Executioner",
            {
                "dt": _fmt(dt),
                "end_time": _fmt(end_time),
                "compute_scaling_once": "true",
            },
        )
    except MooseInputError as exc:
        raise Issue43FastRelaxationError(
            f"fast-block input transform failed: {exc}"
        ) from exc

    fvbc = """[FVBCs]
  [r43_phi_plasma_metal]
    type = FVDirichletBC
    variable = potential_plasma
    boundary = plasma_metal
    value = 0
  []
  [r43_phi_plasma_electrode]
    type = FVDirichletBC
    variable = potential_plasma
    boundary = plasma_electrode
    value = 0
  []
  [r43_phi_plasma_right]
    type = FVDirichletBC
    variable = potential_plasma
    boundary = plasma_right
    value = 0
  []
  [r43_phi_inlet]
    type = FVDirichletBC
    variable = potential_plasma
    boundary = inlet
    value = 0
  []
  [r43_phi_outlet]
    type = FVDirichletBC
    variable = potential_plasma
    boundary = outlet
    value = 0
  []
[]
"""
    text = _insert_top_level_before(text, "Postprocessors", fvbc)

    if "potential = phi_prescribed" in text:
        raise Issue43FastRelaxationError(
            "prescribed-field electron drift remained active"
        )
    required = (
        "potential = potential_plasma",
        "r43_positive_background",
        "r43_phi_diffusion",
        "r43_phi_charge_source",
        "r43_phi_plasma_metal",
        "r43_n_l2",
        "r43_phi_l2",
    )
    missing = [token for token in required if token not in text]
    if missing:
        raise Issue43FastRelaxationError(
            "generated fast-block input is missing: " + ", ".join(missing)
        )

    return text, {
        "gas_temperature_K": gas_temperature,
        "electron_density_m-3": electron_density,
        "dt_s": dt,
        "end_time_s": end_time,
        "radial_span_m": radial_span,
        "background_perturbation_fraction": PERTURBATION_FRACTION,
        "diagnostic_state": "frozen quasi-neutral positive background with a small reactor-scale charge perturbation",
        "electron_constants_change": constants_meta,
        "drift_change": drift_meta,
        "executioner_change": execution_meta,
    }


def find_relaxation_csv(case_dir: Path) -> Path:
    """Locate the Issue43 CSV containing all required relaxation observables."""
    candidates: list[Path] = []
    for path in sorted(Path(case_dir).glob("*.csv")):
        try:
            with path.open(newline="") as handle:
                reader = csv.DictReader(handle)
                fields = set(reader.fieldnames or ())
        except (OSError, csv.Error):
            continue
        if set(REQUIRED_COLUMNS).issubset(fields):
            candidates.append(path)
    if not candidates:
        raise Issue43FastRelaxationError(
            "no runtime CSV contains the r43 relaxation observables"
        )
    preferred = Path(case_dir) / "input_out.csv"
    return preferred if preferred in candidates else candidates[0]


def read_relaxation_rows(path: Path) -> list[dict[str, float]]:
    """Parse finite, positive-time Issue43 relaxation rows."""
    path = Path(path)
    with path.open(newline="") as handle:
        raw = list(csv.DictReader(handle))
    rows: list[dict[str, float]] = []
    for row in raw:
        try:
            parsed = {key: float(row[key]) for key in REQUIRED_COLUMNS}
        except (KeyError, ValueError) as exc:
            raise Issue43FastRelaxationError(
                f"invalid relaxation CSV row in {path}"
            ) from exc
        if not all(math.isfinite(value) for value in parsed.values()):
            raise Issue43FastRelaxationError(
                f"non-finite relaxation observable in {path}"
            )
        if parsed["time"] > 1.0e-15:
            rows.append(parsed)
    if not rows:
        raise Issue43FastRelaxationError(
            f"no positive physical timestep in {path}"
        )
    return rows


def _state_scales(rows: list[dict[str, float]]) -> dict[str, float]:
    scales: dict[str, float] = {}
    for key in STATE_COLUMNS:
        values = [row[key] for row in rows]
        spread = max(values) - min(values)
        endpoint_change = abs(values[0] - values[-1])
        scales[key] = max(abs(spread), endpoint_change, 1.0e-300)
    return scales


def _distance(
    row: dict[str, float],
    ref: dict[str, float],
    scales: dict[str, float],
) -> float:
    return max(abs(row[key] - ref[key]) / scales[key] for key in STATE_COLUMNS)


def analyze_relaxation(
    rows: list[dict[str, float]],
    *,
    electron_density: float,
    relax_tol: float = RELAX_TOL,
) -> dict[str, Any]:
    """Interpret the Issue43 relaxation trajectory without runtime policy."""
    if len(rows) < 3:
        raise Issue43FastRelaxationError(
            "relaxation analysis requires at least three physical rows"
        )

    volume = rows[-1]["domain_volume"]
    expected_inventory = electron_density * volume
    inventory_errors = [
        abs(row["inventory"] - expected_inventory)
        / max(abs(expected_inventory), 1.0e-300)
        for row in rows
    ]
    positivity = not any(
        row["n_min"] <= 0 or row["n_max"] < row["n_min"] for row in rows
    )

    charge_errors: list[float] = []
    for row in rows:
        expected_charge = E_CHARGE * (
            row["r43_background_inventory"] - row["inventory"]
        )
        scale = max(
            abs(expected_charge),
            abs(row["r43_charge_integral"]),
            E_CHARGE * max(abs(row["r43_background_inventory"]), 1.0),
        )
        charge_errors.append(
            abs(row["r43_charge_integral"] - expected_charge) / scale
        )

    scales = _state_scales(rows)
    final = rows[-1]
    distances = [_distance(row, final, scales) for row in rows]
    tail_start = max(0, len(rows) - 3)
    tail_change = max(distances[tail_start:])

    relaxation_index: int | None = None
    for idx, value in enumerate(distances):
        if value <= relax_tol and max(distances[idx:]) <= relax_tol:
            relaxation_index = idx
            break
    relaxation_time = (
        rows[relaxation_index]["time"] if relaxation_index is not None else None
    )

    physics_ok = (
        positivity
        and max(inventory_errors) <= INVENTORY_REL_TOL
        and max(charge_errors) <= CHARGE_REL_TOL
    )
    relaxed = relaxation_time is not None and tail_change <= relax_tol

    return {
        "status": "PASS" if physics_ok else "FAIL",
        "relaxed": relaxed,
        "relaxation_time_s": relaxation_time,
        "tail_change": tail_change,
        "relax_tolerance": relax_tol,
        "positive": positivity,
        "max_inventory_relative_error": max(inventory_errors),
        "max_charge_identity_relative_error": max(charge_errors),
        "first_time_s": rows[0]["time"],
        "final_time_s": rows[-1]["time"],
        "physical_rows": len(rows),
        "distance_to_final": [
            {"time": row["time"], "distance": distance}
            for row, distance in zip(rows, distances)
        ],
    }


def _physics_pass(result: dict[str, Any]) -> bool:
    if result.get("class") != "P3_PASS":
        return False
    analysis = result.get("analysis")
    return not isinstance(analysis, dict) or analysis.get("status") == "PASS"


def classify(
    known_good: dict[str, Any],
    electron_300k: dict[str, Any] | None,
    oneway: dict[str, Any] | None,
    feedback_base: dict[str, Any] | None,
    feedback_small: dict[str, Any] | None,
    feedback_large: dict[str, Any] | None,
    tau_dr: float,
) -> dict[str, Any]:
    """Classify the Issue43 discriminator from runtime evidence supplied by the runner."""
    if (
        known_good.get("class") != "P3_PASS"
        or known_good.get("canonical_checker", {}).get("status") != "PASS"
    ):
        return {
            "class": "KNOWN_GOOD_ELECTRON_CONTROL_FAIL",
            "reason": "historical qvt pre-Poisson electron control did not reproduce",
        }
    if electron_300k is None or not _physics_pass(electron_300k):
        return {
            "class": "ELECTRON_300K_CONTROL_FAIL",
            "reason": "electron-only path did not reproduce at the 300 K anchor",
        }
    if oneway is None or not _physics_pass(oneway):
        return {
            "class": "POISSON_OR_BLOCK_SCALING_FAIL",
            "reason": "electron and Poisson did not converge as a one-way triangular system",
        }
    if feedback_base is None:
        return {
            "class": "FEEDBACK_CASE_MISSING",
            "reason": "base feedback discriminator missing",
        }

    base_ratio = DT_FEEDBACK_BASE / tau_dr
    small_ratio = DT_FEEDBACK_SMALL / tau_dr
    large_ratio = DT_FEEDBACK_LARGE / tau_dr

    if _physics_pass(feedback_base):
        if feedback_large is not None and _physics_pass(feedback_large):
            return {
                "class": "FEEDBACK_IMPLICIT_COUPLING_RECOVERS_NEAR_TAU_DR",
                "reason": "full feedback converged both below and near the dielectric relaxation time",
                "dt_over_tau": {"base": base_ratio, "large": large_ratio},
            }
        if feedback_large is not None:
            return {
                "class": "DIELECTRIC_TIMESTEP_STIFFNESS_CONFIRMED",
                "reason": "full feedback converged below tau_DR but failed near tau_DR",
                "dt_over_tau": {"base": base_ratio, "large": large_ratio},
            }
        return {
            "class": "FEEDBACK_RECOVERS_BELOW_TAU_DR",
            "reason": "full feedback converged at the below-tau discriminator",
            "dt_over_tau": {"base": base_ratio},
        }

    if feedback_small is not None and _physics_pass(feedback_small):
        return {
            "class": "DIELECTRIC_TIMESTEP_STIFFNESS_STRONG",
            "reason": "feedback failed at ~0.09 tau_DR but recovered at ~0.009 tau_DR",
            "dt_over_tau": {"base": base_ratio, "small": small_ratio},
        }
    if feedback_small is not None:
        return {
            "class": "FEEDBACK_JACOBIAN_SCALING_OR_INITIALIZATION_FAIL",
            "reason": "electron-only and one-way systems pass, but two-way feedback fails even far below tau_DR",
            "dt_over_tau": {"base": base_ratio, "small": small_ratio},
        }
    return {
        "class": "FEEDBACK_DISCRIMINATOR_INCOMPLETE",
        "reason": "base feedback failed before the smaller-dt branch was completed",
    }
