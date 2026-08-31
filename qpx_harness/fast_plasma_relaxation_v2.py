"""Issue #43 second-round fast electron + bulk-Poisson coupling discriminator.

This runner repairs the first relaxation probe, whose nominally "short" dt=1e-10 s
was still ~88 dielectric-relaxation times at the 300 K QVT anchor. The second
round separates electron-only behavior, one-way electron->Poisson coupling, and
full electron<->Poisson feedback before attempting a relaxation-time claim.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from recipes import issue43_fast_relaxation as relaxation_recipe

from . import cases as case_ops
from .moose_input import MooseInput, MooseInputError, self_test as moose_input_self_test
from .petsc import log as petsc_log
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
GAS_TEMPERATURE = 300.0
HEAVY_MACRO_DT = 1.0e-4
DT_ELECTRON_CONTROL = 1.0e-10
DT_FEEDBACK_BASE = 1.0e-13   # ~0.088 tau_DR at the 300 K anchor
DT_FEEDBACK_SMALL = 1.0e-14  # ~0.0088 tau_DR
DT_FEEDBACK_LARGE = 1.0e-12  # ~0.88 tau_DR
N_STEPS = 5

_RUNTIME_PURGE_DIRECTORY_NAMES = (".jitcache",)
_RUNTIME_PURGE_PATTERNS = (
    "input_out*",
    "r43_csv*",
    "perfgraph*",
    "petsc_log*",
    "metrics*",
)

MEAN_ENERGY_EV = relaxation_recipe.MEAN_ENERGY_EV
E_CHARGE = relaxation_recipe.E_CHARGE
FastPlasmaRelaxationError = relaxation_recipe.Issue43FastRelaxationError


class FastPlasmaV2Error(RuntimeError):
    pass


# Temporary attribute-level compatibility for the already-absorbed v5 error path.
# This is not a module import and therefore does not keep the historical v1 owner live.
v1 = SimpleNamespace(FastPlasmaRelaxationError=FastPlasmaRelaxationError)


def _fmt(value: float) -> str:
    return f"{value:.17g}"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _create_root(results_root: Path) -> Path:
    results_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    stem = f"fast_plasma_discriminator_v2_Issue43_{stamp}"
    root = results_root / stem
    index = 1
    while root.exists():
        root = results_root / f"{stem}_{index:02d}"
        index += 1
    root.mkdir()
    return root


def _stage_case(source: Path, target: Path, input_text: str | None = None) -> None:
    try:
        case_ops.stage_case(
            source,
            target,
            input_text=input_text,
            purge_directory_names=_RUNTIME_PURGE_DIRECTORY_NAMES,
            purge_patterns=_RUNTIME_PURGE_PATTERNS,
        )
    except case_ops.CaseError as exc:
        raise FastPlasmaRelaxationError(f"case staging failed: {exc}") from exc


def _validate_assets(case_dir: Path) -> list[str]:
    try:
        refs = case_ops.validate_case_references(case_dir)
    except case_ops.CaseError as exc:
        raise FastPlasmaRelaxationError(f"asset validation failed: {exc}") from exc
    return [ref["resolved"] for ref in refs]


def _failure_signature(log: Path) -> str | None:
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
        signature = _failure_signature(p3_log)
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


def _run_known_good(
    *,
    repo_root: Path,
    exe: Path,
    cases_root: Path,
    measurements_root: Path,
) -> dict[str, Any]:
    source = repo_root / BASE_CASE_RELATIVE
    target = cases_root / "known_good_qvt_prepoisson"
    _stage_case(source, target)
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


def _build_electron_300k(base_text: str, *, dt: float, steps: int) -> str:
    try:
        text, _ = MooseInput(base_text).replace_parameters(
            "FunctorMaterials/electron_constants",
            {
                "prop_values": (
                    f"'{_fmt(MEAN_ENERGY_EV)} {_fmt(DEFAULT_PRESSURE)} "
                    f"{_fmt(GAS_TEMPERATURE)} 1.0'"
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
        raise FastPlasmaV2Error(f"electron 300 K control transform failed: {exc}") from exc
    if "potential = phi_prescribed" not in text:
        raise FastPlasmaV2Error("electron 300 K control lost prescribed-field path")
    return text


def _build_oneway(
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
        raise FastPlasmaV2Error(f"one-way transform failed: {exc}") from exc
    drift = MooseInput(text).unique("FVKernels/drift")
    if "potential = potential_plasma" in MooseInput(text).text[drift.start : drift.end]:
        raise FastPlasmaV2Error("one-way case retained phi->electron feedback")
    return text


def _build_feedback(
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


def _residual_summary(log_path: str | None) -> dict[str, Any] | None:
    if not log_path:
        return None
    path = Path(log_path)
    if not path.is_file():
        return None
    text = path.read_text(errors="replace")
    pattern = r"(?m)^\s*(\d+)\s+Nonlinear\s+\|R\|\s*=\s*([0-9.+\-eE]+)"
    import re

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


def _attach_residual(result: dict[str, Any]) -> dict[str, Any]:
    result["nonlinear_residual_summary"] = _residual_summary(result.get("p3_log"))
    return result


def _run_case(
    *,
    base_case: Path,
    case_dir: Path,
    input_text: str,
    case_id: str,
    exe: Path,
    measurements_root: Path,
    analyze: bool,
) -> dict[str, Any]:
    _stage_case(base_case, case_dir, input_text)
    _validate_assets(case_dir)
    validate_parser_symbols_text(input_text)
    result = _run_qpx_case(
        case_dir=case_dir,
        case_id=case_id,
        exe=exe,
        out_root=measurements_root,
        analyze=analyze,
        electron_density=DEFAULT_ELECTRON_DENSITY,
    )
    return _attach_residual(result)


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


def _v1_compat_self_test() -> int:
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
        transformed, _ = relaxation_recipe.build_fast_input(
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
            synthetic.append(
                {
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
            )
        result = relaxation_recipe.analyze_relaxation(
            synthetic,
            electron_density=1.0e16,
            relax_tol=2.0e-4,
        )
        if result["status"] != "PASS":
            raise AssertionError("positive relaxation control failed")

        bad = [dict(row) for row in synthetic]
        bad[-1]["inventory"] *= 1.01
        if (
            relaxation_recipe.analyze_relaxation(
                bad, electron_density=1.0e16
            )["status"]
            != "FAIL"
        ):
            raise AssertionError("inventory mutation was not rejected")

        with tempfile.TemporaryDirectory() as tmp_name:
            root = Path(tmp_name)
            source = root / "source"
            source.mkdir()
            (source / "asset.dat").write_text("asset\n")
            (source / "input.i").write_text("table_file = asset.dat\n")
            (source / "input_out.csv").write_text("stale\n")
            (source / ".jitcache").mkdir()
            (source / ".jitcache" / "jit.o").write_text("stale\n")

            target = root / "target"
            _stage_case(source, target, "table_file = asset.dat\n")
            if (target / "input_out.csv").exists() or (target / ".jitcache").exists():
                raise AssertionError("v1-compatible staging retained stale runtime artifacts")
            expected_asset = str((target / "asset.dat").resolve())
            if _validate_assets(target) != [expected_asset]:
                raise AssertionError("v1-compatible asset validation changed path schema")

            (target / "asset.dat").unlink()
            try:
                _validate_assets(target)
            except FastPlasmaRelaxationError:
                pass
            else:
                raise AssertionError("v1-compatible asset validation accepted a missing asset")
    except Exception as exc:
        print(f"ISSUE43_FAST_RELAXATION_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE43_FAST_RELAXATION_SELFTEST: PASS")
    return 0


def self_test() -> int:
    try:
        if _v1_compat_self_test() != 0:
            raise AssertionError("v1 compatibility self-test failed")
        sample = (
            " 0 Nonlinear |R| = 1.0e+03\n"
            " 1 Nonlinear |R| = 1.0e+01\n"
            " 2 Nonlinear |R| = 2.0e+00\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "log.txt"
            path.write_text(sample)
            summary = _residual_summary(str(path))
            if summary is None or summary["minimum_residual"] != 2.0:
                raise AssertionError("residual parser failed")

        synthetic_good = {
            "class": "P3_PASS",
            "analysis": {"status": "PASS"},
        }
        kge = {
            "class": "P3_PASS",
            "canonical_checker": {"status": "PASS"},
        }
        decision = classify(
            kge,
            synthetic_good,
            synthetic_good,
            synthetic_good,
            None,
            synthetic_good,
            1.0e-12,
        )
        if decision["class"] != "FEEDBACK_IMPLICIT_COUPLING_RECOVERS_NEAR_TAU_DR":
            raise AssertionError("classification positive control failed")
    except Exception as exc:
        print(f"ISSUE43_FAST_V2_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE43_FAST_V2_SELFTEST: PASS")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run Issue43 electron/Poisson coupling discriminator v2"
    )
    parser.add_argument("--qpx", help="path to user-local qpx-opt")
    parser.add_argument("--results-root")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()
    if self_test() != 0:
        return 1

    repo_root = Path(__file__).resolve().parents[1]
    base_case = repo_root / BASE_CASE_RELATIVE
    if not base_case.is_dir():
        raise SystemExit(f"missing accepted qvt electron control: {base_case}")

    exe = resolve_executable(args.qpx)
    validate_executable(exe)
    results_root = (
        Path(args.results_root).expanduser().resolve()
        if args.results_root
        else exe.parent / "temp" / "results"
    )
    root = _create_root(results_root)
    cases_root = root / "cases"
    measurements_root = root / "measurements"
    cases_root.mkdir(exist_ok=True)
    measurements_root.mkdir(exist_ok=True)

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
    tau_dr = float(scales["electron"]["dielectric_relaxation_s"])
    radial_span = float(mesh["bbox_span_m"]["x"])
    base_text = (base_case / "input.i").read_text()

    known_good = _run_known_good(
        repo_root=repo_root,
        exe=exe,
        cases_root=cases_root,
        measurements_root=measurements_root,
    )
    if (
        known_good.get("class") != "P3_PASS"
        or known_good.get("canonical_checker", {}).get("status") != "PASS"
    ):
        decision = classify(known_good, None, None, None, None, None, tau_dr)
        summary_path = root / "summary.json"
        _write_json(
            summary_path,
            {"scale_map": scales, "known_good": known_good, "decision": decision},
        )
        print(f"ISSUE43_FAST2_PRECLASS: {decision['class']}")
        print(f"ISSUE43_FAST2_REASON: {decision['reason']}")
        print(f"ISSUE43_FAST2_SUMMARY: {summary_path}")
        return 2

    e300_text = _build_electron_300k(
        base_text,
        dt=DT_ELECTRON_CONTROL,
        steps=N_STEPS,
    )
    electron_300k = _run_case(
        base_case=base_case,
        case_dir=cases_root / "electron_300K",
        input_text=e300_text,
        case_id="Issue43_FAST2_electron_300K",
        exe=exe,
        measurements_root=measurements_root,
        analyze=False,
    )

    oneway = None
    feedback_base = None
    feedback_small = None
    feedback_large = None

    if _physics_pass(electron_300k):
        oneway_text = _build_oneway(
            base_text,
            dt=DT_ELECTRON_CONTROL,
            steps=N_STEPS,
            radial_span=radial_span,
        )
        oneway = _run_case(
            base_case=base_case,
            case_dir=cases_root / "oneway_e_to_phi",
            input_text=oneway_text,
            case_id="Issue43_FAST2_oneway_e_to_phi",
            exe=exe,
            measurements_root=measurements_root,
            analyze=True,
        )

    if oneway is not None and _physics_pass(oneway):
        feedback_text = _build_feedback(
            base_text,
            dt=DT_FEEDBACK_BASE,
            steps=N_STEPS,
            radial_span=radial_span,
        )
        feedback_base = _run_case(
            base_case=base_case,
            case_dir=cases_root / "feedback_dt1e13",
            input_text=feedback_text,
            case_id="Issue43_FAST2_feedback_dt1e13",
            exe=exe,
            measurements_root=measurements_root,
            analyze=True,
        )

        if _physics_pass(feedback_base):
            large_text = _build_feedback(
                base_text,
                dt=DT_FEEDBACK_LARGE,
                steps=N_STEPS,
                radial_span=radial_span,
            )
            feedback_large = _run_case(
                base_case=base_case,
                case_dir=cases_root / "feedback_dt1e12",
                input_text=large_text,
                case_id="Issue43_FAST2_feedback_dt1e12",
                exe=exe,
                measurements_root=measurements_root,
                analyze=True,
            )
        else:
            small_text = _build_feedback(
                base_text,
                dt=DT_FEEDBACK_SMALL,
                steps=N_STEPS,
                radial_span=radial_span,
            )
            feedback_small = _run_case(
                base_case=base_case,
                case_dir=cases_root / "feedback_dt1e14",
                input_text=small_text,
                case_id="Issue43_FAST2_feedback_dt1e14",
                exe=exe,
                measurements_root=measurements_root,
                analyze=True,
            )

    decision = classify(
        known_good,
        electron_300k,
        oneway,
        feedback_base,
        feedback_small,
        feedback_large,
        tau_dr,
    )
    summary = {
        "scale_map": scales,
        "dt_over_tau_dr": {
            "electron_control": DT_ELECTRON_CONTROL / tau_dr,
            "feedback_base": DT_FEEDBACK_BASE / tau_dr,
            "feedback_small": DT_FEEDBACK_SMALL / tau_dr,
            "feedback_large": DT_FEEDBACK_LARGE / tau_dr,
        },
        "known_good": known_good,
        "electron_300k": electron_300k,
        "oneway": oneway,
        "feedback_base": feedback_base,
        "feedback_small": feedback_small,
        "feedback_large": feedback_large,
        "decision": decision,
    }
    summary_path = root / "summary.json"
    _write_json(summary_path, summary)

    print(f"ISSUE43_FAST2_KGE: {known_good.get('class')}")
    print(f"ISSUE43_FAST2_E300: {electron_300k.get('class')}")
    if oneway is not None:
        print(f"ISSUE43_FAST2_ONEWAY: {oneway.get('class')}")
    if feedback_base is not None:
        print(f"ISSUE43_FAST2_FEEDBACK_1E13: {feedback_base.get('class')}")
        print(
            "ISSUE43_FAST2_FEEDBACK_1E13_RESIDUAL: "
            f"{feedback_base.get('nonlinear_residual_summary')}"
        )
    if feedback_small is not None:
        print(f"ISSUE43_FAST2_FEEDBACK_1E14: {feedback_small.get('class')}")
        print(
            "ISSUE43_FAST2_FEEDBACK_1E14_RESIDUAL: "
            f"{feedback_small.get('nonlinear_residual_summary')}"
        )
    if feedback_large is not None:
        print(f"ISSUE43_FAST2_FEEDBACK_1E12: {feedback_large.get('class')}")
        print(
            "ISSUE43_FAST2_FEEDBACK_1E12_RESIDUAL: "
            f"{feedback_large.get('nonlinear_residual_summary')}"
        )
    print(f"ISSUE43_FAST2_PRECLASS: {decision['class']}")
    print(f"ISSUE43_FAST2_REASON: {decision['reason']}")
    print(f"ISSUE43_FAST2_SUMMARY: {summary_path}")
    return 0 if decision["class"] not in {
        "KNOWN_GOOD_ELECTRON_CONTROL_FAIL",
        "ELECTRON_300K_CONTROL_FAIL",
        "POISSON_OR_BLOCK_SCALING_FAIL",
        "FEEDBACK_JACOBIAN_SCALING_OR_INITIALIZATION_FAIL",
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
