"""Issue #43 fast electron + bulk-Poisson relaxation audit.

The runner asks whether a frozen-heavy-state electron/Poisson block relaxes fast enough
relative to the heavy macrostep to justify quasi-steady inner coupling.  It does not
promote a specific electron production timestep.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .moose_input import MooseInput, MooseInputError, self_test as moose_input_self_test
from .preflight import validate_parser_symbols_text
from .runtime import resolve_executable, run_qpx, validate_executable
from .scale_audit import (
    DEFAULT_D_N,
    DEFAULT_ELECTRON_DENSITY,
    DEFAULT_MU_N,
    DEFAULT_PRESSURE,
    anchor_scales,
    mesh_stats,
)

BASE_CASE_RELATIVE = Path("tests/Issue2_electron_bulk_drift/qvt_prepoisson")
HEAVY_MACRO_DT = 1.0e-4
GAS_TEMPERATURE = 300.0
MEAN_ENERGY_EV = 5.73276
PERTURBATION_FRACTION = 1.0e-6
SHORT_DT = 1.0e-10
SHORT_STEPS = 20
COARSE_DT = 1.0e-8
FINE_DT = 5.0e-9
RELAX_TOL = 1.0e-4
INVENTORY_REL_TOL = 1.0e-6
CHARGE_REL_TOL = 1.0e-6
REFINEMENT_REL_TOL = 0.25
FAST_SEPARATION = 100.0
SUBCYCLE_SEPARATION = 10.0
E_CHARGE = 1.602176634e-19
EPS0 = 8.8541878128e-12

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


class FastPlasmaRelaxationError(RuntimeError):
    pass


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _create_root(results_root: Path) -> Path:
    results_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    stem = f"fast_plasma_relaxation_Issue43_{stamp}"
    root = results_root / stem
    index = 1
    while root.exists():
        root = results_root / f"{stem}_{index:02d}"
        index += 1
    root.mkdir()
    return root


def _purge_runtime_artifacts(root: Path) -> None:
    for path in root.rglob(".jitcache"):
        if path.is_dir():
            shutil.rmtree(path)
    for pattern in ("input_out*", "r43_csv*", "perfgraph*", "petsc_log*", "metrics*"):
        for path in root.rglob(pattern):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                shutil.rmtree(path)


def _insert_top_level_before(text: str, marker: str, block: str) -> str:
    needle = f"\n[{marker}]\n"
    if text.count(needle) != 1:
        raise FastPlasmaRelaxationError(
            f"expected one top-level [{marker}] marker, found {text.count(needle)}"
        )
    payload = block
    if not payload.endswith("\n"):
        payload += "\n"
    return text.replace(needle, "\n" + payload + needle, 1)


def _format_float(value: float) -> str:
    return f"{value:.17g}"


def build_fast_input(
    base_text: str,
    *,
    gas_temperature: float,
    electron_density: float,
    dt: float,
    end_time: float,
    radial_span: float,
) -> tuple[str, dict[str, Any]]:
    if radial_span <= 0 or dt <= 0 or end_time <= 0:
        raise FastPlasmaRelaxationError("radial span, dt and end_time must be positive")

    try:
        text, constants_meta = MooseInput(base_text).replace_parameters(
            "FunctorMaterials/electron_constants",
            {
                "prop_values": (
                    f"'{_format_float(MEAN_ENERGY_EV)} "
                    f"{_format_float(DEFAULT_PRESSURE)} "
                    f"{_format_float(gas_temperature)} 1.0'"
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
            f"{_format_float(electron_density)}*"
            f"(1.0+{_format_float(PERTURBATION_FRACTION)}*"
            f"cos(2*pi*x/{_format_float(radial_span)}))"
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
    expression = '{_format_float(E_CHARGE)}*qnum'
    block = plasma
  []
  [r43_poisson_source]
    type = ADParsedFunctorMaterial
    property_name = r43_poisson_source
    functor_names = 'r43_charge_number_density'
    functor_symbols = 'qnum'
    expression = '{_format_float(e_over_eps0)}*qnum'
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
                "dt": _format_float(dt),
                "end_time": _format_float(end_time),
                "compute_scaling_once": "true",
            },
        )
    except MooseInputError as exc:
        raise FastPlasmaRelaxationError(f"fast-block input transform failed: {exc}") from exc

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
        raise FastPlasmaRelaxationError("prescribed-field electron drift remained active")
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
        raise FastPlasmaRelaxationError(
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


def _copy_case(source: Path, target: Path, input_text: str | None = None) -> None:
    shutil.copytree(source, target)
    _purge_runtime_artifacts(target)
    if input_text is not None:
        (target / "input.i").write_text(input_text)


def _find_csv(case_dir: Path) -> Path:
    candidates: list[Path] = []
    for path in sorted(case_dir.glob("*.csv")):
        try:
            with path.open(newline="") as handle:
                reader = csv.DictReader(handle)
                fields = set(reader.fieldnames or ())
        except (OSError, csv.Error):
            continue
        if set(REQUIRED_COLUMNS).issubset(fields):
            candidates.append(path)
    if not candidates:
        raise FastPlasmaRelaxationError("no runtime CSV contains the r43 relaxation observables")
    preferred = case_dir / "input_out.csv"
    if preferred in candidates:
        return preferred
    return candidates[0]


def _rows(path: Path) -> list[dict[str, float]]:
    with path.open(newline="") as handle:
        raw = list(csv.DictReader(handle))
    rows: list[dict[str, float]] = []
    for row in raw:
        try:
            parsed = {key: float(row[key]) for key in REQUIRED_COLUMNS}
        except (KeyError, ValueError) as exc:
            raise FastPlasmaRelaxationError(f"invalid relaxation CSV row in {path}") from exc
        if not all(math.isfinite(value) for value in parsed.values()):
            raise FastPlasmaRelaxationError(f"non-finite relaxation observable in {path}")
        if parsed["time"] > 1.0e-15:
            rows.append(parsed)
    if not rows:
        raise FastPlasmaRelaxationError(f"no positive physical timestep in {path}")
    return rows


def _state_scales(rows: list[dict[str, float]]) -> dict[str, float]:
    """Normalize relaxation by the transient excursion, not the absolute state."""
    scales: dict[str, float] = {}
    for key in STATE_COLUMNS:
        values = [row[key] for row in rows]
        spread = max(values) - min(values)
        endpoint_change = abs(values[0] - values[-1])
        scales[key] = max(abs(spread), endpoint_change, 1.0e-300)
    return scales


def _distance(row: dict[str, float], ref: dict[str, float], scales: dict[str, float]) -> float:
    return max(abs(row[key] - ref[key]) / scales[key] for key in STATE_COLUMNS)


def analyze_relaxation(
    rows: list[dict[str, float]],
    *,
    electron_density: float,
    relax_tol: float = RELAX_TOL,
) -> dict[str, Any]:
    if len(rows) < 3:
        raise FastPlasmaRelaxationError("relaxation analysis requires at least three physical rows")

    volume = rows[-1]["domain_volume"]
    expected_inventory = electron_density * volume
    inventory_errors = [
        abs(row["inventory"] - expected_inventory) / max(abs(expected_inventory), 1.0e-300)
        for row in rows
    ]
    if any(row["n_min"] <= 0 or row["n_max"] < row["n_min"] for row in rows):
        positivity = False
    else:
        positivity = True

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
    relaxation_time = rows[relaxation_index]["time"] if relaxation_index is not None else None

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


def _failure_signature(log: Path) -> str | None:
    if not log.is_file():
        return None
    text = log.read_text(errors="replace")
    for name, pattern in (
        ("DIVERGED_MAX_IT", r"DIVERGED_MAX_IT"),
        ("DIVERGED_LINE_SEARCH", r"DIVERGED_LINE_SEARCH"),
        ("DIVERGED_FNORM_NAN", r"DIVERGED_FNORM_NAN|NaN"),
        ("NONLINEAR_DID_NOT_CONVERGE", r"Nonlinear solve did not converge|Solve Did NOT Converge"),
    ):
        if re.search(pattern, text, re.IGNORECASE):
            return name
    return None


def _validate_assets(case_dir: Path) -> list[str]:
    text = (case_dir / "input.i").read_text()
    refs: list[str] = []
    for raw in re.findall(r"(?m)^\s*(?:file|[A-Za-z_][A-Za-z0-9_]*_file)\s*=\s*['\"]?([^\s'\"]+)", text):
        path = Path(raw)
        resolved = path if path.is_absolute() else case_dir / path
        if not resolved.is_file():
            raise FastPlasmaRelaxationError(f"missing referenced file: {resolved}")
        refs.append(str(resolved.resolve()))
    return refs


def _run_qpx_case(
    *,
    case_dir: Path,
    case_id: str,
    exe: Path,
    out_root: Path,
    analyze: bool,
    electron_density: float,
) -> dict[str, Any]:
    result_root = out_root / case_id
    result_root.mkdir(parents=True)
    p2_log = result_root / "p2_check_input.log"
    p3_log = result_root / "p3_runtime.log"

    print(f"ISSUE43_FAST_CASE_START: {case_id} P2")
    p2 = run_qpx(
        exe,
        cwd=case_dir,
        input_name="input.i",
        log_path=p2_log,
        extra_args=("--check-input",),
        stream=True,
    )
    print(f"ISSUE43_FAST_CASE_END: {case_id} P2 rc={p2.returncode}")
    if p2.returncode != 0:
        return {
            "case_id": case_id,
            "class": "HARNESS_OR_CONSTRUCTION_FAIL",
            "p2_returncode": p2.returncode,
            "p2_log": str(p2_log),
        }

    print(f"ISSUE43_FAST_CASE_START: {case_id} P3")
    p3 = run_qpx(
        exe,
        cwd=case_dir,
        input_name="input.i",
        log_path=p3_log,
        stream=True,
    )
    print(f"ISSUE43_FAST_CASE_END: {case_id} P3 rc={p3.returncode}")
    if p3.returncode != 0:
        return {
            "case_id": case_id,
            "class": "SOLVER_CONVERGENCE_FAIL"
            if _failure_signature(p3_log)
            else "RUNTIME_FAIL",
            "p2_returncode": p2.returncode,
            "p3_returncode": p3.returncode,
            "p3_failure_signature": _failure_signature(p3_log),
            "p2_log": str(p2_log),
            "p3_log": str(p3_log),
        }

    payload: dict[str, Any] = {
        "case_id": case_id,
        "class": "P3_PASS",
        "p2_returncode": p2.returncode,
        "p3_returncode": p3.returncode,
        "p2_wall_seconds": p2.wall_seconds,
        "p3_wall_seconds": p3.wall_seconds,
        "p2_log": str(p2_log),
        "p3_log": str(p3_log),
    }
    if analyze:
        csv_path = _find_csv(case_dir)
        payload["csv"] = str(csv_path)
        payload["analysis"] = analyze_relaxation(
            _rows(csv_path), electron_density=electron_density
        )
    return payload


def _run_known_good(
    *,
    repo_root: Path,
    exe: Path,
    cases_root: Path,
    measurements_root: Path,
) -> dict[str, Any]:
    source = repo_root / BASE_CASE_RELATIVE
    target = cases_root / "known_good_qvt_prepoisson"
    _copy_case(source, target)
    result = _run_qpx_case(
        case_dir=target,
        case_id="Issue43_KGE_qvt_prepoisson",
        exe=exe,
        out_root=measurements_root,
        analyze=False,
        electron_density=DEFAULT_ELECTRON_DENSITY,
    )
    if result.get("class") != "P3_PASS":
        return result

    checker = repo_root / BASE_CASE_RELATIVE.parent / "check_case.py"
    expected = target / "expected.json"
    csv_path = target / "input_out.csv"
    log = measurements_root / "Issue43_KGE_qvt_prepoisson" / "canonical_checker.log"
    with log.open("w") as handle:
        proc = subprocess.run(
            [sys.executable, str(checker), str(csv_path), str(expected)],
            cwd=target,
            stdout=handle,
            stderr=subprocess.STDOUT,
        )
    result["canonical_checker"] = {
        "returncode": proc.returncode,
        "status": "PASS" if proc.returncode == 0 else "FAIL",
        "log": str(log),
    }
    if proc.returncode != 0:
        result["class"] = "KNOWN_GOOD_ELECTRON_CONTROL_FAIL"
    return result


def _case_relaxed(case: dict[str, Any]) -> bool:
    analysis = case.get("analysis")
    return (
        case.get("class") == "P3_PASS"
        and isinstance(analysis, dict)
        and analysis.get("status") == "PASS"
        and bool(analysis.get("relaxed"))
    )


def classify(
    known_good: dict[str, Any],
    short_case: dict[str, Any] | None,
    coarse: dict[str, Any] | None,
    fine: dict[str, Any] | None,
) -> dict[str, Any]:
    if known_good.get("class") != "P3_PASS" or known_good.get("canonical_checker", {}).get("status") != "PASS":
        return {
            "class": "KNOWN_GOOD_ELECTRON_CONTROL_FAIL",
            "reason": "historical qvt pre-Poisson electron control did not reproduce",
        }

    if short_case is None:
        return {"class": "HARNESS_OR_CONSTRUCTION_FAIL", "reason": "short relaxation case missing"}
    if short_case.get("class") in {"HARNESS_OR_CONSTRUCTION_FAIL", "RUNTIME_FAIL"}:
        return {"class": short_case["class"], "reason": "short relaxation case failed before interpretable relaxation evidence"}
    if short_case.get("class") == "SOLVER_CONVERGENCE_FAIL":
        return {
            "class": "SOLVER_CONVERGENCE_FAIL",
            "reason": "fast electron-Poisson block did not converge even at the short microstep",
        }
    if short_case.get("analysis", {}).get("status") == "FAIL":
        return {
            "class": "PHYSICS_CHECK_FAIL",
            "reason": "short relaxation runtime violated positivity/inventory/charge identity",
        }

    if _case_relaxed(short_case):
        tau = float(short_case["analysis"]["relaxation_time_s"])
        separation = HEAVY_MACRO_DT / max(tau, 1.0e-300)
        return {
            "class": "FAST_RELAXATION_CONFIRMED_CANDIDATE",
            "reason": "electron-Poisson state reached the relaxation criterion inside the short probe",
            "relaxation_time_upper_bound_s": tau,
            "heavy_to_fast_separation": separation,
            "branch": "short_probe",
        }

    if coarse is None or fine is None:
        return {
            "class": "LONG_REFINEMENT_REQUIRED",
            "reason": "short probe did not relax and the long refinement pair is incomplete",
        }
    for label, case in (("coarse", coarse), ("fine", fine)):
        if case.get("class") == "HARNESS_OR_CONSTRUCTION_FAIL":
            return {"class": "HARNESS_OR_CONSTRUCTION_FAIL", "reason": f"{label} case failed P2"}
        if case.get("class") == "SOLVER_CONVERGENCE_FAIL":
            return {"class": "SOLVER_CONVERGENCE_FAIL", "reason": f"{label} case failed nonlinear convergence"}
        if case.get("class") != "P3_PASS":
            return {"class": "RUNTIME_FAIL", "reason": f"{label} case did not complete"}
        if case.get("analysis", {}).get("status") != "PASS":
            return {"class": "PHYSICS_CHECK_FAIL", "reason": f"{label} case violated invariants"}

    if not _case_relaxed(coarse) or not _case_relaxed(fine):
        return {
            "class": "QUASI_STEADY_NOT_YET_JUSTIFIED_CANDIDATE",
            "reason": "one or both long refinement cases did not reach the relaxation criterion",
        }

    tau_c = float(coarse["analysis"]["relaxation_time_s"])
    tau_f = float(fine["analysis"]["relaxation_time_s"])
    refinement_error = abs(tau_c - tau_f) / max(abs(tau_f), 1.0e-300)
    separation = HEAVY_MACRO_DT / max(tau_c, tau_f, 1.0e-300)
    if refinement_error > REFINEMENT_REL_TOL:
        return {
            "class": "TEMPORAL_REFINEMENT_UNRESOLVED",
            "reason": "coarse/fine inferred relaxation times disagree beyond tolerance",
            "tau_coarse_s": tau_c,
            "tau_fine_s": tau_f,
            "relative_difference": refinement_error,
        }
    if separation >= FAST_SEPARATION:
        cls = "FAST_RELAXATION_CONFIRMED_CANDIDATE"
    elif separation >= SUBCYCLE_SEPARATION:
        cls = "SUBCYCLING_REQUIRED_CANDIDATE"
    else:
        cls = "QUASI_STEADY_NOT_JUSTIFIED_CANDIDATE"
    return {
        "class": cls,
        "reason": "coarse/fine relaxation times agree and are classified by separation from the heavy macrostep",
        "tau_coarse_s": tau_c,
        "tau_fine_s": tau_f,
        "relative_difference": refinement_error,
        "heavy_to_fast_separation": separation,
        "branch": "long_refinement",
    }


def self_test() -> int:
    try:
        if moose_input_self_test() != 0:
            raise AssertionError("MooseInput self-test failed")

        base = """[Variables]
  [n_e]
    type = MooseVariableFVReal
    initial_condition = 1e16
    block = plasma
  []
[]
[Functions]
  [phi_prescribed]
    type = ParsedFunction
    expression = '-0.01*x'
  []
[]
[FunctorMaterials]
  [electron_constants]
    type = ADGenericFunctorMaterial
    prop_names = 'mean_en p_abs T_g carrier_one'
    prop_values = '5.73276 1.33322 600.0 1.0'
    block = plasma
  []
[]
[FVKernels]
  [drift]
    type = QPXFVElectrostaticDrift
    variable = n_e
    potential = phi_prescribed
    mobility = electron_mobility
    carrier = carrier_one
    charge_number = -1
    block = plasma
  []
[]
[Postprocessors]
  [n_min]
    type = ADElementExtremeFunctorValue
    functor = n_e
    value_type = min
    block = plasma
  []
[]
[Executioner]
  type = Transient
  dt = 1e-8
  end_time = 2e-8
  compute_scaling_once = true
[]
[Outputs]
  csv = true
[]
"""
        transformed, _ = build_fast_input(
            base,
            gas_temperature=300.0,
            electron_density=1.0e16,
            dt=1.0e-10,
            end_time=2.0e-9,
            radial_span=0.243,
        )
        if "potential = potential_plasma" not in transformed:
            raise AssertionError("electron-Poisson feedback was not constructed")
        if "r43_positive_background" not in transformed or "T_g" not in transformed:
            raise AssertionError("fast-block materials missing")

        synthetic: list[dict[str, float]] = []
        for i in range(1, 6):
            decay = 10.0 ** (-i)
            row = {
                "time": i * 1.0e-10,
                "n_min": 1.0e16 * (1.0 - 1.0e-6 * decay),
                "n_max": 1.0e16 * (1.0 + 1.0e-6 * decay),
                "inventory": 1.0e16,
                "domain_volume": 1.0,
                "r43_n_l2": 1.0e16 * (1.0 + 1.0e-7 * decay),
                "r43_phi_l2": decay,
                "r43_phi_min": -decay,
                "r43_phi_max": decay,
                "r43_phi_integral": 0.0,
                "r43_charge_integral": 0.0,
                "r43_background_inventory": 1.0e16,
                "r43_charge_min": -E_CHARGE * 1.0e10 * decay,
                "r43_charge_max": E_CHARGE * 1.0e10 * decay,
            }
            synthetic.append(row)
        result = analyze_relaxation(synthetic, electron_density=1.0e16, relax_tol=2.0e-4)
        if result["status"] != "PASS":
            raise AssertionError("positive relaxation control failed")

        bad = [dict(row) for row in synthetic]
        bad[-1]["inventory"] *= 1.01
        if analyze_relaxation(bad, electron_density=1.0e16)["status"] != "FAIL":
            raise AssertionError("inventory mutation was not rejected")
    except Exception as exc:
        print(f"ISSUE43_FAST_RELAXATION_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE43_FAST_RELAXATION_SELFTEST: PASS")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run Issue43 frozen-heavy electron + bulk-Poisson relaxation audit"
    )
    parser.add_argument("--qpx", help="path to user-local qpx-opt")
    parser.add_argument("--results-root")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    repo_root = Path(__file__).resolve().parents[1]
    base_case = repo_root / BASE_CASE_RELATIVE
    if not base_case.is_dir():
        raise SystemExit(f"missing accepted qvt electron control: {base_case}")

    if self_test() != 0:
        return 1

    exe = resolve_executable(args.qpx)
    validate_executable(exe)

    mesh = mesh_stats(base_case / "qvt.msh")
    scales = anchor_scales(
        pressure=DEFAULT_PRESSURE,
        gas_temperature=GAS_TEMPERATURE,
        electron_density=DEFAULT_ELECTRON_DENSITY,
        mu_n=DEFAULT_MU_N,
        d_n=DEFAULT_D_N,
        dt=HEAVY_MACRO_DT,
        mesh=mesh,
        rf_frequency=None,
    )
    d_e = float(scales["electron"]["diffusion_m2_s"])
    radial_span = float(mesh["bbox_span_m"]["x"])
    l_reactor = float(mesh["reactor_characteristic_length_m"])
    slow_diffusion_mode = l_reactor * l_reactor / (math.pi * math.pi * d_e)
    long_end = 10.0 * slow_diffusion_mode

    results_root = (
        Path(args.results_root).expanduser().resolve()
        if args.results_root
        else exe.parent / "temp" / "results"
    )
    root = _create_root(results_root)
    cases_root = root / "cases"
    measurements_root = root / "measurements"
    cases_root.mkdir()
    measurements_root.mkdir()

    base_text = (base_case / "input.i").read_text()
    validate_parser_symbols_text(base_text)

    known_good = _run_known_good(
        repo_root=repo_root,
        exe=exe,
        cases_root=cases_root,
        measurements_root=measurements_root,
    )
    if known_good.get("class") != "P3_PASS" or known_good.get("canonical_checker", {}).get("status") != "PASS":
        decision = classify(known_good, None, None, None)
        summary = {
            "scale_map": scales,
            "known_good": known_good,
            "short": None,
            "coarse": None,
            "fine": None,
            "decision": decision,
        }
        summary_path = root / "summary.json"
        _write_json(summary_path, summary)
        print(f"ISSUE43_FAST_PRECLASS: {decision['class']}")
        print(f"ISSUE43_FAST_REASON: {decision['reason']}")
        print(f"ISSUE43_FAST_SUMMARY: {summary_path}")
        return 2

    short_text, short_meta = build_fast_input(
        base_text,
        gas_temperature=GAS_TEMPERATURE,
        electron_density=DEFAULT_ELECTRON_DENSITY,
        dt=SHORT_DT,
        end_time=SHORT_DT * SHORT_STEPS,
        radial_span=radial_span,
    )
    validate_parser_symbols_text(short_text)
    short_dir = cases_root / "short_dt1e10"
    _copy_case(base_case, short_dir, short_text)
    _validate_assets(short_dir)
    short = _run_qpx_case(
        case_dir=short_dir,
        case_id="Issue43_FAST_short_dt1e10",
        exe=exe,
        out_root=measurements_root,
        analyze=True,
        electron_density=DEFAULT_ELECTRON_DENSITY,
    )
    short["construction"] = short_meta

    coarse = None
    fine = None
    if not _case_relaxed(short) and short.get("class") == "P3_PASS" and short.get("analysis", {}).get("status") == "PASS":
        for label, dt in (("coarse_dt1e8", COARSE_DT), ("fine_dt5e9", FINE_DT)):
            text, meta = build_fast_input(
                base_text,
                gas_temperature=GAS_TEMPERATURE,
                electron_density=DEFAULT_ELECTRON_DENSITY,
                dt=dt,
                end_time=long_end,
                radial_span=radial_span,
            )
            validate_parser_symbols_text(text)
            case_dir = cases_root / label
            _copy_case(base_case, case_dir, text)
            _validate_assets(case_dir)
            result = _run_qpx_case(
                case_dir=case_dir,
                case_id=f"Issue43_FAST_{label}",
                exe=exe,
                out_root=measurements_root,
                analyze=True,
                electron_density=DEFAULT_ELECTRON_DENSITY,
            )
            result["construction"] = meta
            if label.startswith("coarse"):
                coarse = result
            else:
                fine = result

    decision = classify(known_good, short, coarse, fine)
    summary = {
        "scale_map": scales,
        "derived_long_window": {
            "reactor_characteristic_length_m": l_reactor,
            "electron_diffusion_m2_s": d_e,
            "fundamental_diffusion_mode_s": slow_diffusion_mode,
            "long_end_time_s": long_end,
        },
        "known_good": known_good,
        "short": short,
        "coarse": coarse,
        "fine": fine,
        "decision": decision,
    }
    summary_path = root / "summary.json"
    _write_json(summary_path, summary)

    print(f"ISSUE43_FAST_KGE: {known_good.get('class')}")
    print(f"ISSUE43_FAST_SHORT: {short.get('class')} relaxed={short.get('analysis', {}).get('relaxed')}")
    if coarse is not None:
        print(f"ISSUE43_FAST_COARSE: {coarse.get('class')} relaxed={coarse.get('analysis', {}).get('relaxed')}")
    if fine is not None:
        print(f"ISSUE43_FAST_FINE: {fine.get('class')} relaxed={fine.get('analysis', {}).get('relaxed')}")
    print(f"ISSUE43_FAST_PRECLASS: {decision['class']}")
    print(f"ISSUE43_FAST_REASON: {decision['reason']}")
    if "heavy_to_fast_separation" in decision:
        print(f"ISSUE43_FAST_SEPARATION: {decision['heavy_to_fast_separation']:.6e}")
    print(f"ISSUE43_FAST_SUMMARY: {summary_path}")
    return 0 if decision["class"].endswith("_CANDIDATE") else 2


if __name__ == "__main__":
    raise SystemExit(main())
