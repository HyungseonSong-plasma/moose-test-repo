"""Issue #43 relaxation runtime composition.

This module owns Issue43-specific runtime construction and execution mechanics.
Scientific interpretation and terminal classification remain in
``recipes.issue43_fast_relaxation``; generic filesystem, parser, PETSc-log, and
executable mechanics remain in their reusable qpx_harness owners.
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from recipes import issue43_fast_relaxation as relaxation_recipe

from . import cases as case_ops
from .moose_input import MooseInput, MooseInputError
from .petsc import log as petsc_log
from .preflight import validate_parser_symbols_text
from .runtime import run_qpx
from .scale_audit import DEFAULT_ELECTRON_DENSITY, DEFAULT_PRESSURE

BASE_CASE_RELATIVE = Path("tests/Issue2_electron_bulk_drift/qvt_prepoisson")
GAS_TEMPERATURE = 300.0
HEAVY_MACRO_DT = 1.0e-4
DT_ELECTRON_CONTROL = 1.0e-10
DT_FEEDBACK_BASE = relaxation_recipe.DT_FEEDBACK_BASE
DT_FEEDBACK_SMALL = relaxation_recipe.DT_FEEDBACK_SMALL
DT_FEEDBACK_LARGE = relaxation_recipe.DT_FEEDBACK_LARGE
N_STEPS = 5

_RUNTIME_PURGE_DIRECTORY_NAMES = (".jitcache",)
_RUNTIME_PURGE_PATTERNS = (
    "input_out*",
    "r43_csv*",
    "perfgraph*",
    "petsc_log*",
    "metrics*",
)


def _fmt(value: float) -> str:
    return f"{value:.17g}"


def stage_case(source: Path, target: Path, input_text: str | None = None) -> None:
    try:
        case_ops.stage_case(
            source,
            target,
            input_text=input_text,
            purge_directory_names=_RUNTIME_PURGE_DIRECTORY_NAMES,
            purge_patterns=_RUNTIME_PURGE_PATTERNS,
        )
    except case_ops.CaseError as exc:
        raise relaxation_recipe.Issue43FastRelaxationError(
            f"case staging failed: {exc}"
        ) from exc


def validate_assets(case_dir: Path) -> list[str]:
    try:
        refs = case_ops.validate_case_references(case_dir)
    except case_ops.CaseError as exc:
        raise relaxation_recipe.Issue43FastRelaxationError(
            f"asset validation failed: {exc}"
        ) from exc
    return [ref["resolved"] for ref in refs]


def failure_signature(log: Path) -> str | None:
    if not log.is_file():
        return None
    text = log.read_text(errors="replace")
    for name, pattern in (
        ("DIVERGED_MAX_IT", r"DIVERGED_MAX_IT"),
        ("DIVERGED_LINE_SEARCH", r"DIVERGED_LINE_SEARCH"),
        ("DIVERGED_FNORM_NAN", r"DIVERGED_FNORM_NAN|NaN"),
        (
            "NONLINEAR_DID_NOT_CONVERGE",
            r"Nonlinear solve did not converge|Solve Did NOT Converge",
        ),
    ):
        if petsc_log.line_hits(text, (pattern,)):
            return name
    return None


def run_qpx_case(
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
        signature = failure_signature(p3_log)
        return {
            "case_id": case_id,
            "class": "SOLVER_CONVERGENCE_FAIL" if signature else "RUNTIME_FAIL",
            "p2_returncode": p2.returncode,
            "p3_returncode": p3.returncode,
            "p3_failure_signature": signature,
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
        csv_path = relaxation_recipe.find_relaxation_csv(case_dir)
        payload["csv"] = str(csv_path)
        payload["analysis"] = relaxation_recipe.analyze_relaxation(
            relaxation_recipe.read_relaxation_rows(csv_path),
            electron_density=electron_density,
        )
    return payload


def run_known_good(
    *,
    repo_root: Path,
    exe: Path,
    cases_root: Path,
    measurements_root: Path,
) -> dict[str, Any]:
    source = repo_root / BASE_CASE_RELATIVE
    target = cases_root / "known_good_qvt_prepoisson"
    stage_case(source, target)
    result = run_qpx_case(
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


def build_electron_300k(base_text: str, *, dt: float, steps: int) -> str:
    try:
        text, _ = MooseInput(base_text).replace_parameters(
            "FunctorMaterials/electron_constants",
            {
                "prop_values": (
                    f"'{_fmt(relaxation_recipe.MEAN_ENERGY_EV)} "
                    f"{_fmt(DEFAULT_PRESSURE)} {_fmt(GAS_TEMPERATURE)} 1.0'"
                )
            },
        )
        text, _ = MooseInput(text).replace_parameters(
            "Executioner",
            {
                "dt": _fmt(dt),
                "end_time": _fmt(dt * steps),
                "compute_scaling_once": "true",
            },
        )
    except MooseInputError as exc:
        raise relaxation_recipe.Issue43FastRelaxationError(
            f"electron 300 K control transform failed: {exc}"
        ) from exc
    if "potential = phi_prescribed" not in text:
        raise relaxation_recipe.Issue43FastRelaxationError(
            "electron 300 K control lost prescribed-field path"
        )
    return text


def build_oneway(
    base_text: str,
    *,
    dt: float,
    steps: int,
    radial_span: float,
) -> str:
    text, _ = relaxation_recipe.build_fast_input(
        base_text,
        gas_temperature=GAS_TEMPERATURE,
        electron_density=DEFAULT_ELECTRON_DENSITY,
        dt=dt,
        end_time=dt * steps,
        radial_span=radial_span,
    )
    try:
        text, _ = MooseInput(text).replace_parameters(
            "FVKernels/drift", {"potential": "phi_prescribed"}
        )
    except MooseInputError as exc:
        raise relaxation_recipe.Issue43FastRelaxationError(
            f"one-way transform failed: {exc}"
        ) from exc
    drift = MooseInput(text).unique("FVKernels/drift")
    if "potential = potential_plasma" in MooseInput(text).text[drift.start : drift.end]:
        raise relaxation_recipe.Issue43FastRelaxationError(
            "one-way case retained phi->electron feedback"
        )
    return text


def build_feedback(
    base_text: str,
    *,
    dt: float,
    steps: int,
    radial_span: float,
) -> str:
    text, _ = relaxation_recipe.build_fast_input(
        base_text,
        gas_temperature=GAS_TEMPERATURE,
        electron_density=DEFAULT_ELECTRON_DENSITY,
        dt=dt,
        end_time=dt * steps,
        radial_span=radial_span,
    )
    return text


def nonlinear_residual_summary(log_path: str | None) -> dict[str, Any] | None:
    if not log_path:
        return None
    path = Path(log_path)
    if not path.is_file():
        return None
    text = path.read_text(errors="replace")
    pattern = r"(?m)^\s*(\d+)\s+Nonlinear\s+\|R\|\s*=\s*([0-9.+\-eE]+)"

    pairs: list[tuple[int, float]] = []
    for match in re.finditer(pattern, text):
        try:
            pairs.append((int(match.group(1)), float(match.group(2))))
        except ValueError:
            continue
    if not pairs:
        return None

    solves: list[list[float]] = []
    current: list[float] = []
    for iteration, residual in pairs:
        if iteration == 0 and current:
            solves.append(current)
            current = []
        current.append(residual)
    if current:
        solves.append(current)

    final = solves[-1]
    initial = final[0]
    minimum = min(final)
    last = final[-1]
    monotone_steps = sum(1 for a, b in zip(final, final[1:]) if b <= a)
    return {
        "solve_count": len(solves),
        "final_solve_points": len(final),
        "initial_residual": initial,
        "minimum_residual": minimum,
        "last_residual": last,
        "initial_to_min_ratio": minimum / max(abs(initial), 1.0e-300),
        "last_to_initial_ratio": last / max(abs(initial), 1.0e-300),
        "monotone_fraction": monotone_steps / max(len(final) - 1, 1),
        "final_solve_residuals": final,
    }


def attach_nonlinear_residual(result: dict[str, Any]) -> dict[str, Any]:
    result["nonlinear_residual_summary"] = nonlinear_residual_summary(
        result.get("p3_log")
    )
    return result


def run_case(
    *,
    base_case: Path,
    case_dir: Path,
    input_text: str,
    case_id: str,
    exe: Path,
    measurements_root: Path,
    analyze: bool,
) -> dict[str, Any]:
    stage_case(base_case, case_dir, input_text)
    validate_assets(case_dir)
    validate_parser_symbols_text(input_text)
    result = run_qpx_case(
        case_dir=case_dir,
        case_id=case_id,
        exe=exe,
        out_root=measurements_root,
        analyze=analyze,
        electron_density=DEFAULT_ELECTRON_DENSITY,
    )
    return attach_nonlinear_residual(result)


def physics_pass(result: dict[str, Any]) -> bool:
    if result.get("class") != "P3_PASS":
        return False
    analysis = result.get("analysis")
    return not isinstance(analysis, dict) or analysis.get("status") == "PASS"


def _fixture() -> str:
    return """[Variables]
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


def self_test() -> int:
    try:
        feedback = build_feedback(
            _fixture(), dt=DT_FEEDBACK_BASE, steps=N_STEPS, radial_span=0.243
        )
        expected, _ = relaxation_recipe.build_fast_input(
            _fixture(),
            gas_temperature=GAS_TEMPERATURE,
            electron_density=DEFAULT_ELECTRON_DENSITY,
            dt=DT_FEEDBACK_BASE,
            end_time=DT_FEEDBACK_BASE * N_STEPS,
            radial_span=0.243,
        )
        if feedback != expected:
            raise AssertionError("feedback builder drifted from canonical recipe")

        oneway = build_oneway(
            _fixture(), dt=DT_FEEDBACK_BASE, steps=N_STEPS, radial_span=0.243
        )
        drift = MooseInput(oneway).unique("FVKernels/drift")
        drift_text = MooseInput(oneway).text[drift.start : drift.end]
        if "potential = phi_prescribed" not in drift_text:
            raise AssertionError("one-way builder lost prescribed potential")
        if "potential = potential_plasma" in drift_text:
            raise AssertionError("one-way builder retained feedback")

        electron = build_electron_300k(
            _fixture(), dt=DT_ELECTRON_CONTROL, steps=N_STEPS
        )
        if "potential = phi_prescribed" not in electron:
            raise AssertionError("electron 300 K builder lost prescribed potential")
        if "300" not in electron:
            raise AssertionError("electron 300 K builder lost gas-temperature control")

        with tempfile.TemporaryDirectory() as tmp_name:
            log = Path(tmp_name) / "runtime.log"
            log.write_text(
                " 0 Nonlinear |R| = 1.0e+03\n"
                " 1 Nonlinear |R| = 1.0e+01\n"
                " 2 Nonlinear |R| = 2.0e+00\n"
            )
            summary = nonlinear_residual_summary(str(log))
            if summary is None or summary["minimum_residual"] != 2.0:
                raise AssertionError("residual parser failed")

        if not physics_pass({"class": "P3_PASS", "analysis": {"status": "PASS"}}):
            raise AssertionError("physics-pass positive control failed")
        if physics_pass({"class": "SOLVER_CONVERGENCE_FAIL"}):
            raise AssertionError("physics-pass negative control failed")
    except Exception as exc:
        print(f"ISSUE43_RELAXATION_RUNTIME_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE43_RELAXATION_RUNTIME_SELFTEST: PASS")
    return 0
