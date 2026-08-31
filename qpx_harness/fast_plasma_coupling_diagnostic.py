"""Bounded Issue #43 electron-Poisson coupling failure localization harness.

The harness instruments, but does not retune, the established discriminator:
T1 is one full-feedback step at dt=1e-14; T2 is one at dt=1e-13.

The optional Jacobian mode checks the assembled Jacobian against PETSc finite
Differences at the same T1/T2 states.  It is diagnostic-only and does not change
accepted physics, boundary conditions, transport coefficients, or the timestep pair.
"""

from __future__ import annotations

import argparse
import math
import re
import tempfile
from pathlib import Path
from typing import Any

from . import artifacts
from . import cases as case_ops
from . import evidence
from . import execution_contract as ec
from . import fast_plasma_relaxation_v5 as v5
from . import output_observation_contract as ooc
from .moose_input import MooseInput, MooseInputError
from .preflight import validate_parser_symbols_text
from .runtime import resolve_executable, run_qpx, validate_executable
from .scale_audit import mesh_stats


BASE_CASE_RELATIVE = Path("tests/Issue2_electron_bulk_drift/qvt_prepoisson")
DT_CONTROL = 1.0e-14
DT_FAIL = 1.0e-13
STEPS = 1
JACOBIAN_REL_TOL = 1.0e-6
DIAGNOSTIC_PETSC_OPTIONS = (
    "-snes_converged_reason",
    "-ksp_converged_reason",
    "-snes_monitor",
    "-ksp_monitor",
)
JACOBIAN_PETSC_OPTIONS = ("-snes_test_jacobian",)
_RUNTIME_PURGE_DIRECTORY_NAMES = (".jitcache",)
_RUNTIME_PURGE_PATTERNS = (
    "input_out*",
    "r43_csv*",
    "perfgraph*",
    "petsc_log*",
    "metrics*",
)


class FastPlasmaCouplingDiagnosticError(RuntimeError):
    pass


def _stage_case(source: Path, target: Path, input_text: str) -> list[str]:
    try:
        case_ops.stage_case(
            source,
            target,
            input_text=input_text,
            purge_directory_names=_RUNTIME_PURGE_DIRECTORY_NAMES,
            purge_patterns=_RUNTIME_PURGE_PATTERNS,
        )
        refs = case_ops.validate_case_references(target)
    except case_ops.CaseError as exc:
        raise FastPlasmaCouplingDiagnosticError(f"case staging failed: {exc}") from exc
    return [ref["resolved"] for ref in refs]


def _write_summary(path: Path, payload: dict[str, Any]) -> None:
    artifacts.write_json_bundle(
        path.parent,
        {"summary": (path.name, payload)},
    )


def _parameter_match(text: str, path: str, name: str) -> tuple[Any, str, list[re.Match[str]]]:
    doc = MooseInput(text)
    span = doc.unique(path)
    block = text[span.start : span.end]
    pattern = re.compile(
        rf"(?m)^(?P<prefix>\s*{re.escape(name)}\s*=\s*)"
        rf"(?P<value>[^#\r\n]*?)"
        rf"(?P<suffix>\s*(?:#.*)?$)"
    )
    return span, block, list(pattern.finditer(block))


def _set_or_insert_parameter(text: str, path: str, name: str, value: str) -> str:
    _, _, matches = _parameter_match(text, path, name)
    if len(matches) > 1:
        raise FastPlasmaCouplingDiagnosticError(
            f"ambiguous diagnostic parameter {path}/{name}: {len(matches)} assignments"
        )
    try:
        if matches:
            return MooseInput(text).replace_parameters(path, {name: value})[0]
        return MooseInput(text).insert_before_close(path, f"  {name} = {value}")[0]
    except MooseInputError as exc:
        raise FastPlasmaCouplingDiagnosticError(
            f"failed to instrument {path}/{name}: {exc}"
        ) from exc


def _parameter_value(text: str, path: str, name: str) -> str | None:
    _, _, matches = _parameter_match(text, path, name)
    if len(matches) > 1:
        raise FastPlasmaCouplingDiagnosticError(
            f"ambiguous diagnostic parameter {path}/{name}: {len(matches)} assignments"
        )
    return matches[0].group("value").strip() if matches else None


def _ensure_debug_block(text: str) -> str:
    matches = MooseInput(text).find("Debug")
    if len(matches) > 1:
        raise FastPlasmaCouplingDiagnosticError("multiple top-level [Debug] blocks")
    if not matches:
        suffix = "" if text.endswith("\n") else "\n"
        text = text + suffix + "\n[Debug]\n  show_var_residual_norms = true\n[]\n"
        MooseInput(text)
        return text
    return _set_or_insert_parameter(text, "Debug", "show_var_residual_norms", "true")


def _petsc_options(text: str) -> list[str]:
    raw = _parameter_value(text, "Executioner", "petsc_options")
    if not raw:
        return []
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return value.split()


def _merge_petsc_options(text: str, required: tuple[str, ...]) -> str:
    merged = list(_petsc_options(text))
    for option in required:
        if option not in merged:
            merged.append(option)
    return _set_or_insert_parameter(
        text,
        "Executioner",
        "petsc_options",
        "'" + " ".join(merged) + "'",
    )


def instrument_input(
    input_text: str, *, jacobian_test: bool = False
) -> tuple[str, dict[str, Any]]:
    """Add diagnostic-only MOOSE/PETSc observability."""
    text = _ensure_debug_block(input_text)
    text = _set_or_insert_parameter(text, "Executioner", "verbose", "true")
    required = DIAGNOSTIC_PETSC_OPTIONS + (JACOBIAN_PETSC_OPTIONS if jacobian_test else ())
    text = _merge_petsc_options(text, required)
    text = _set_or_insert_parameter(text, "Outputs/console", "all_variable_norms", "true")
    return text, {
        "debug_show_var_residual_norms": True,
        "executioner_verbose": True,
        "console_all_variable_norms": True,
        "petsc_options_added": list(required),
        "jacobian_test": jacobian_test,
        "physics_or_numerics_changed": False,
    }


def _build_case(
    base_text: str, *, dt: float, radial_span: float, jacobian_test: bool = False
) -> tuple[str, dict[str, Any]]:
    uninstrumented = v5._build_feedback_v5(
        base_text,
        dt=dt,
        steps=STEPS,
        radial_span=radial_span,
    )
    instrumented, instrumentation = instrument_input(
        uninstrumented, jacobian_test=jacobian_test
    )
    return instrumented, {
        "dt": dt,
        "steps": STEPS,
        "jacobian_test": jacobian_test,
        "instrumentation": instrumentation,
    }


def _contains_petsc_options(text: str, required: tuple[str, ...]) -> bool:
    options = _petsc_options(text)
    return all(option in options for option in required)


def _p1_case(
    case_id: str, text: str, *, dt: float, jacobian_test: bool = False
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(check_id: str, passed: bool, observed: Any, required: Any) -> None:
        checks.append(
            {
                "id": check_id,
                "status": "PASS" if passed else "FAIL",
                "observed": observed,
                "required": required,
            }
        )

    parser_errors = validate_parser_symbols_text(text, f"<{case_id}>")
    add("parser-symbol-preflight", not parser_errors, parser_errors, [])

    contract = v5._augment_execution_contract(case_id, text)
    contract_decision = ec.evaluate_contract(contract, phase="P1")
    add(
        "execution-contract-p1",
        contract_decision["status"] == "PASS",
        contract_decision["status"],
        "PASS",
    )

    output_report = ooc.observation_report(text, required_time_separation=dt)
    output_decision = ooc.evaluate_observation_report(output_report)
    add(
        "output-observation-p1",
        output_decision["status"] == "PASS",
        output_decision["status"],
        "PASS",
    )

    verbose = _parameter_value(text, "Executioner", "verbose")
    debug = _parameter_value(text, "Debug", "show_var_residual_norms")
    all_norms = _parameter_value(text, "Outputs/console", "all_variable_norms")
    add("diagnostic-executioner-verbose", verbose == "true", verbose, "true")
    add("diagnostic-variable-residuals", debug == "true", debug, "true")
    add("diagnostic-console-all-variable-norms", all_norms == "true", all_norms, "true")
    add(
        "diagnostic-petsc-options",
        _contains_petsc_options(text, DIAGNOSTIC_PETSC_OPTIONS),
        _parameter_value(text, "Executioner", "petsc_options"),
        list(DIAGNOSTIC_PETSC_OPTIONS),
    )
    if jacobian_test:
        add(
            "jacobian-petsc-test-option",
            _contains_petsc_options(text, JACOBIAN_PETSC_OPTIONS),
            _parameter_value(text, "Executioner", "petsc_options"),
            list(JACOBIAN_PETSC_OPTIONS),
        )

    expected_end = dt * STEPS
    dt_raw = _parameter_value(text, "Executioner", "dt")
    end_raw = _parameter_value(text, "Executioner", "end_time")
    try:
        dt_value = float(dt_raw) if dt_raw is not None else None
        end_value = float(end_raw) if end_raw is not None else None
    except ValueError:
        dt_value = None
        end_value = None
    numeric_tol = max(abs(dt) * 1.0e-12, 1.0e-300)
    add(
        "numerical-regime-dt-preserved",
        dt_value is not None and abs(dt_value - dt) <= numeric_tol,
        dt_value,
        dt,
    )
    add(
        "numerical-regime-end-time-preserved",
        end_value is not None and abs(end_value - expected_end) <= numeric_tol,
        end_value,
        expected_end,
    )

    blockers = [item for item in checks if item["status"] != "PASS"]
    return {
        "status": "PASS" if not blockers else "HOLD",
        "checks": checks,
        "blockers": blockers,
        "contract": contract,
        "contract_decision": contract_decision,
        "output_report": output_report,
        "output_decision": output_decision,
    }


_FLOAT = r"[+\-]?(?:(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+\-]?\d+)?|nan|inf(?:inity)?)"


def _parse_variable_residuals(text: str) -> list[dict[str, float]]:
    blocks: list[dict[str, float]] = []
    current: dict[str, float] | None = None
    for line in text.splitlines():
        if "|residual|_2 of individual variables:" in line:
            current = {}
            blocks.append(current)
            continue
        if current is None:
            continue
        match = re.match(
            rf"^\s*([A-Za-z_][A-Za-z0-9_]*):\s*({_FLOAT})\s*$",
            line,
            re.IGNORECASE,
        )
        if match:
            try:
                current[match.group(1)] = float(match.group(2))
            except ValueError:
                pass
        elif line.strip() and current:
            current = None
    return [block for block in blocks if block]


def _parse_scaling_factors(text: str) -> list[dict[str, float]]:
    blocks: list[dict[str, float]] = []
    current: dict[str, float] | None = None
    for line in text.splitlines():
        if line.strip() == "Automatic scaling factors:":
            current = {}
            blocks.append(current)
            continue
        if current is None:
            continue
        match = re.match(
            rf"^\s*([A-Za-z_][A-Za-z0-9_]*):\s*({_FLOAT})(?:\s+.*)?$",
            line,
            re.IGNORECASE,
        )
        if match:
            try:
                current[match.group(1)] = float(match.group(2))
            except ValueError:
                pass
        elif not line.strip():
            current = None
        elif current:
            current = None
    return [block for block in blocks if block]


def _line_hits(text: str, patterns: tuple[str, ...]) -> list[str]:
    return [
        line.strip()
        for line in text.splitlines()
        if any(re.search(pattern, line, re.IGNORECASE) for pattern in patterns)
    ]


def _parse_pc_failure_reason(text: str) -> str | None:
    match = re.search(r"PC failed due to\s+([A-Z0-9_]+)", text)
    return match.group(1) if match else None


def _parse_jacobian_tests(text: str) -> list[dict[str, float]]:
    pattern = re.compile(
        rf"\|\|J\s*-\s*Jfd\|\|_F/\|\|J\|\|_F\s*=\s*({_FLOAT})"
        rf"\s*,\s*\|\|J\s*-\s*Jfd\|\|_F\s*=\s*({_FLOAT})",
        re.IGNORECASE,
    )
    results: list[dict[str, float]] = []
    for match in pattern.finditer(text):
        try:
            rel = float(match.group(1))
            absolute = float(match.group(2))
        except ValueError:
            continue
        results.append({"relative_frobenius_error": rel, "absolute_frobenius_error": absolute})
    return results


def analyze_jacobian_text(
    text: str, *, relative_tolerance: float = JACOBIAN_REL_TOL
) -> dict[str, Any]:
    tests = _parse_jacobian_tests(text)
    if not tests:
        return {
            "status": "HOLD",
            "class": "JACOBIAN_EVIDENCE_INSUFFICIENT",
            "reason": "PETSc -snes_test_jacobian produced no parseable Jacobian comparison",
            "relative_tolerance": relative_tolerance,
            "tests": [],
        }
    nonfinite = [
        item for item in tests
        if not math.isfinite(item["relative_frobenius_error"])
        or not math.isfinite(item["absolute_frobenius_error"])
    ]
    worst = max(item["relative_frobenius_error"] for item in tests if math.isfinite(item["relative_frobenius_error"])) if len(nonfinite) < len(tests) else math.inf
    if nonfinite or worst > relative_tolerance:
        return {
            "status": "HOLD",
            "class": "JACOBIAN_MISMATCH",
            "reason": (
                "assembled-vs-finite-difference Jacobian relative Frobenius error exceeds "
                f"the declared tolerance {relative_tolerance:g} or is non-finite"
            ),
            "relative_tolerance": relative_tolerance,
            "worst_relative_frobenius_error": worst,
            "nonfinite": nonfinite,
            "tests": tests,
        }
    return {
        "status": "PASS",
        "class": "JACOBIAN_CORRECTNESS_PASS",
        "reason": "all observed PETSc Jacobian comparisons satisfy the declared relative tolerance",
        "relative_tolerance": relative_tolerance,
        "worst_relative_frobenius_error": worst,
        "nonfinite": [],
        "tests": tests,
    }


def analyze_log_text(text: str, *, returncode: int) -> dict[str, Any]:
    residual_blocks = _parse_variable_residuals(text)
    scaling_blocks = _parse_scaling_factors(text)
    scaling = scaling_blocks[0] if scaling_blocks else {}

    linear_reason = None
    nonlinear_reason = None
    match = re.search(r"Linear solve did not converge due to\s+([A-Z0-9_]+)", text)
    if match:
        linear_reason = match.group(1)
    match = re.search(r"Nonlinear solve did not converge due to\s+([A-Z0-9_]+)", text)
    if match:
        nonlinear_reason = match.group(1)
    pc_failure_reason = _parse_pc_failure_reason(text)

    pc_hits = _line_hits(
        text,
        (
            r"DIVERGED_PC_FAILED",
            r"DIVERGED_PCSETUP_FAILED",
            r"PC failed due to",
            r"zero pivot",
            r"factorization",
            r"PCSetUp.*fail",
        ),
    )
    factorization_hits = _line_hits(
        text,
        (
            r"FACTOR_(?:NUMERIC|STRUCT)_ZEROPIVOT",
            r"zero pivot",
            r"factorization",
            r"MatFactor",
            r"PCSetUp.*fail",
        ),
    )

    nonfinite_residuals: list[dict[str, Any]] = []
    for index, block in enumerate(residual_blocks):
        for name, value in block.items():
            if not math.isfinite(value):
                nonfinite_residuals.append(
                    {"block": index, "variable": name, "value": repr(value)}
                )

    scaling_invalid: list[dict[str, Any]] = []
    for name in ("n_e", "potential_plasma"):
        if name not in scaling:
            continue
        value = scaling[name]
        if not math.isfinite(value) or value == 0.0:
            scaling_invalid.append({"variable": name, "value": repr(value)})

    selected_scaling = [
        abs(scaling[name])
        for name in ("n_e", "potential_plasma")
        if name in scaling and math.isfinite(scaling[name]) and scaling[name] != 0.0
    ]
    scaling_ratio = (
        max(selected_scaling) / min(selected_scaling)
        if len(selected_scaling) == 2
        else None
    )

    finite_residual_blocks = bool(residual_blocks) and not nonfinite_residuals
    if pc_hits or linear_reason in {"DIVERGED_PC_FAILED", "DIVERGED_PCSETUP_FAILED"}:
        decision_class = "PC_OR_FACTORIZATION_FAIL"
        if pc_failure_reason == "FACTOR_NUMERIC_ZEROPIVOT":
            reason = (
                "PETSc LU/preconditioner setup failed with FACTOR_NUMERIC_ZEROPIVOT; "
                "later nonlinear NAN/INF is downstream of the factorization failure"
            )
        else:
            reason = (
                "the first direct linear-solver signature is PETSc preconditioner/setup failure; "
                "later nonlinear NAN/INF is not promoted above that earlier failure"
            )
    elif nonfinite_residuals:
        decision_class = "INITIAL_NONFINITE_FAIL"
        reason = "variable-residual diagnostics contain NaN/Inf without an earlier PC failure"
    elif scaling_invalid:
        decision_class = "SCALING_DOMINATED_FAIL"
        reason = "automatic scaling produced a zero or non-finite factor for a coupled variable"
    elif returncode != 0 and finite_residual_blocks:
        decision_class = "COUPLED_JACOBIAN_OR_RESIDUAL_FAIL"
        reason = (
            "runtime failed with finite per-variable residual evidence and without a direct "
            "PC/non-finite/scaling-invalid signature"
        )
    else:
        decision_class = "DIAGNOSTIC_INSUFFICIENT"
        reason = "available diagnostic signatures do not uniquely identify H1-H4"

    return {
        "class": decision_class,
        "reason": reason,
        "returncode": returncode,
        "linear_reason": linear_reason,
        "nonlinear_reason": nonlinear_reason,
        "pc_failure_reason": pc_failure_reason,
        "pc_hits": pc_hits,
        "factorization_hits": factorization_hits,
        "variable_residuals": residual_blocks,
        "nonfinite_residuals": nonfinite_residuals,
        "automatic_scaling_factors": scaling_blocks,
        "scaling_invalid": scaling_invalid,
        "scaling_factor_ratio_n_e_to_potential": scaling_ratio,
    }


def analyze_log(log_path: Path, *, returncode: int) -> dict[str, Any]:
    if not log_path.is_file():
        return {
            "class": "DIAGNOSTIC_INSUFFICIENT",
            "reason": "runtime log is missing",
            "returncode": returncode,
        }
    return analyze_log_text(log_path.read_text(errors="replace"), returncode=returncode)


def analyze_jacobian_log(log_path: Path) -> dict[str, Any]:
    if not log_path.is_file():
        return {
            "status": "HOLD",
            "class": "JACOBIAN_EVIDENCE_INSUFFICIENT",
            "reason": "runtime log is missing",
            "relative_tolerance": JACOBIAN_REL_TOL,
            "tests": [],
        }
    return analyze_jacobian_text(log_path.read_text(errors="replace"))


def self_test() -> int:
    try:
        base = """[Executioner]
  type = Transient
  dt = 1e-14
  end_time = 1e-14
  petsc_options_iname = '-pc_type'
  petsc_options_value = 'lu'
[]
[Outputs]
  [console]
    type = Console
  []
[]
"""
        tuned, meta = instrument_input(base)
        if meta["physics_or_numerics_changed"] is not False:
            raise AssertionError("diagnostic instrumentation changed physics/numerics metadata")
        if _parameter_value(tuned, "Debug", "show_var_residual_norms") != "true":
            raise AssertionError("Debug residual instrumentation missing")
        if _parameter_value(tuned, "Executioner", "verbose") != "true":
            raise AssertionError("Executioner verbose instrumentation missing")
        if _parameter_value(tuned, "Outputs/console", "all_variable_norms") != "true":
            raise AssertionError("Console variable-norm instrumentation missing")
        if not _contains_petsc_options(tuned, DIAGNOSTIC_PETSC_OPTIONS):
            raise AssertionError("PETSc diagnostic options missing")

        jacobian_tuned, jac_meta = instrument_input(base, jacobian_test=True)
        if jac_meta["physics_or_numerics_changed"] is not False:
            raise AssertionError("Jacobian instrumentation changed physics/numerics metadata")
        if not _contains_petsc_options(jacobian_tuned, JACOBIAN_PETSC_OPTIONS):
            raise AssertionError("PETSc Jacobian test option missing")
        if "-snes_test_jacobian_view" in _petsc_options(jacobian_tuned):
            raise AssertionError("Jacobian mode unexpectedly enabled full matrix dump")

        already = base.replace(
            "  petsc_options_iname = '-pc_type'\n",
            "  petsc_options = '-snes_view'\n  petsc_options_iname = '-pc_type'\n",
        )
        merged, _ = instrument_input(already, jacobian_test=True)
        if "-snes_view" not in _petsc_options(merged):
            raise AssertionError("existing PETSc option was not preserved")

        pc_log = """Automatic scaling factors:
 n_e: 1e-16
 potential_plasma: 1

 0 Nonlinear |R| = 1e+00
 |residual|_2 of individual variables:
 n_e: 8e-01
 potential_plasma: 6e-01
Linear solve did not converge due to DIVERGED_PC_FAILED iterations 0
                   PC failed due to FACTOR_NUMERIC_ZEROPIVOT
Nonlinear solve did not converge due to DIVERGED_FUNCTION_NANORINF iterations 0
"""
        pc_analysis = analyze_log_text(pc_log, returncode=1)
        if pc_analysis["class"] != "PC_OR_FACTORIZATION_FAIL":
            raise AssertionError("PC failure was not given first-failure priority")
        if pc_analysis["pc_failure_reason"] != "FACTOR_NUMERIC_ZEROPIVOT":
            raise AssertionError("numeric zero-pivot reason was not structured")
        if not pc_analysis["factorization_hits"]:
            raise AssertionError("numeric zero-pivot line was not retained as factorization evidence")

        nonfinite_log = """Automatic scaling factors:
 n_e: 1e-16
 potential_plasma: 1

 |residual|_2 of individual variables:
 n_e: nan
 potential_plasma: 1e-2
Nonlinear solve did not converge due to DIVERGED_FUNCTION_NANORINF iterations 0
"""
        if analyze_log_text(nonfinite_log, returncode=1)["class"] != "INITIAL_NONFINITE_FAIL":
            raise AssertionError("non-finite residual signature was not classified")

        scaling_log = """Automatic scaling factors:
 n_e: 0
 potential_plasma: 1

 |residual|_2 of individual variables:
 n_e: 1
 potential_plasma: 1
Solve Did NOT Converge!
"""
        if analyze_log_text(scaling_log, returncode=1)["class"] != "SCALING_DOMINATED_FAIL":
            raise AssertionError("invalid scaling signature was not classified")

        residual_log = """Automatic scaling factors:
 n_e: 1e-16
 potential_plasma: 1

 |residual|_2 of individual variables:
 n_e: 1e-3
 potential_plasma: 2e-3
Nonlinear solve did not converge due to DIVERGED_LINE_SEARCH iterations 1
"""
        if analyze_log_text(residual_log, returncode=1)["class"] != "COUPLED_JACOBIAN_OR_RESIDUAL_FAIL":
            raise AssertionError("finite residual/Jacobian branch was not classified")

        if analyze_log_text("Solve Did NOT Converge!\n", returncode=1)["class"] != "DIAGNOSTIC_INSUFFICIENT":
            raise AssertionError("insufficient evidence was over-classified")

        jac_good = """---------- Testing Jacobian -------------
||J - Jfd||_F/||J||_F = 2.1e-09, ||J - Jfd||_F = 2.3e-08
"""
        if analyze_jacobian_text(jac_good)["class"] != "JACOBIAN_CORRECTNESS_PASS":
            raise AssertionError("good Jacobian comparison did not pass")
        jac_bad = jac_good.replace("2.1e-09", "2.1e-03")
        if analyze_jacobian_text(jac_bad)["class"] != "JACOBIAN_MISMATCH":
            raise AssertionError("Jacobian mismatch negative control did not fail")
        if analyze_jacobian_text("no jacobian report\n")["class"] != "JACOBIAN_EVIDENCE_INSUFFICIENT":
            raise AssertionError("missing Jacobian evidence was over-classified")

        with tempfile.TemporaryDirectory() as tmp_name:
            root = Path(tmp_name)
            source = root / "source"
            source.mkdir()
            (source / "input.i").write_text("table_file = asset.dat\n")
            (source / "asset.dat").write_text("asset\n")
            (source / "input_out.csv").write_text("stale\n")
            (source / ".jitcache").mkdir()
            target = root / "target"
            refs = _stage_case(source, target, "table_file = asset.dat\n")
            expected_asset = str((target / "asset.dat").resolve())
            if refs != [expected_asset]:
                raise AssertionError("canonical case-reference path schema changed")
            if (target / "input_out.csv").exists() or (target / ".jitcache").exists():
                raise AssertionError("canonical case staging retained stale runtime artifacts")
            (target / "asset.dat").unlink()
            try:
                case_ops.validate_case_references(target)
            except case_ops.CaseError:
                pass
            else:
                raise AssertionError("missing staged asset negative control was accepted")
    except Exception as exc:
        print(f"ISSUE43_COUPLING_DIAGNOSTIC_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE43_COUPLING_DIAGNOSTIC_SELFTEST: PASS")
    return 0


def _prepare_cases(
    *, exe: Path, results_root: str | None, jacobian_test: bool = False
) -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[1]
    base_case = repo_root / BASE_CASE_RELATIVE
    if not base_case.is_dir():
        raise FastPlasmaCouplingDiagnosticError(
            f"missing accepted qvt electron control: {base_case}"
        )

    mesh = mesh_stats(base_case / "qvt.msh")
    radial_span = float(mesh["bbox_span_m"]["x"])
    base_text = (base_case / "input.i").read_text()
    variants = {
        "T1_dt1e14": _build_case(
            base_text, dt=DT_CONTROL, radial_span=radial_span, jacobian_test=jacobian_test
        ),
        "T2_dt1e13": _build_case(
            base_text, dt=DT_FAIL, radial_span=radial_span, jacobian_test=jacobian_test
        ),
    }

    p1 = {
        label: _p1_case(
            label,
            text,
            dt=float(meta["dt"]),
            jacobian_test=jacobian_test,
        )
        for label, (text, meta) in variants.items()
    }
    p1_status = "PASS" if all(item["status"] == "PASS" for item in p1.values()) else "HOLD"

    evidence_root = (
        Path(results_root).expanduser().resolve()
        if results_root
        else exe.parent / "temp" / "results"
    )
    stem = "issue43_jacobian_diagnostic" if jacobian_test else "issue43_coupling_diagnostic"
    root = evidence.ensure_fresh_directory(
        evidence_root / f"{stem}_{evidence.utc_timestamp()}"
    )
    cases_root = root / "cases"
    cases_root.mkdir()

    cases: dict[str, Any] = {}
    for label, (text, meta) in variants.items():
        case_dir = cases_root / label
        _stage_case(base_case, case_dir, text)
        cases[label] = {
            "case_dir": case_dir,
            "input_path": case_dir / "input.i",
            "meta": meta,
            "p1": p1[label],
        }

    return {
        "root": root,
        "cases": cases,
        "p1": p1,
        "p1_status": p1_status,
        "jacobian_test": jacobian_test,
    }


def _run_p2(*, exe: Path, prepared: dict[str, Any]) -> dict[str, Any]:
    p2: dict[str, Any] = {}
    for label, case in prepared["cases"].items():
        log_path = prepared["root"] / f"p2_{label}.log"
        run = run_qpx(
            exe,
            cwd=case["case_dir"],
            input_name="input.i",
            log_path=log_path,
            extra_args=("--check-input", "--color", "off"),
            stream=False,
        )
        p2[label] = {
            "returncode": run.returncode,
            "wall_seconds": run.wall_seconds,
            "log": str(log_path),
            "failure": v5._classify_p2_failure(log_path, run.returncode),
            "identity": {
                **evidence.identity_record(executable=exe, input_path=case["input_path"]),
                "qpx_sha256": evidence.sha256_file(exe),
            },
        }
    return p2


def _emit_preflight_markers(
    *,
    prepared: dict[str, Any],
    p2: dict[str, Any],
    status: str,
    summary_path: Path,
    prefix: str = "ISSUE43_COUPLING_DIAGNOSTIC",
) -> None:
    print(f"{prefix}_P1: {prepared['p1_status']}")
    for label in ("T1_dt1e14", "T2_dt1e13"):
        result = p2.get(label)
        if result is None:
            print(f"{prefix}_P2_{label}: HOLD")
            continue
        print(f"{prefix}_P2_{label}: " + ("PASS" if result["returncode"] == 0 else "FAIL"))
        if result["returncode"] != 0:
            failure = result["failure"]
            print(f"{prefix}_P2_{label}_CLASS: {failure.get('class')}")
            print(f"{prefix}_P2_{label}_REASON: {failure.get('reason')}")
            if failure.get("detail"):
                print(f"{prefix}_P2_{label}_DETAIL: {failure['detail']}")
    print(f"{prefix}_PREFLIGHT: {status}")
    print(f"{prefix}_SUMMARY: {summary_path}")


def _preflight_result(*, qpx: str | None, results_root: str | None, jacobian_test: bool) -> tuple[Path, dict[str, Any], dict[str, Any], str]:
    exe = resolve_executable(qpx)
    validate_executable(exe)
    prepared = _prepare_cases(exe=exe, results_root=results_root, jacobian_test=jacobian_test)
    p2 = _run_p2(exe=exe, prepared=prepared) if prepared["p1_status"] == "PASS" else {}
    p2_pass = bool(p2) and all(item["returncode"] == 0 for item in p2.values())
    status = "PASS" if prepared["p1_status"] == "PASS" and p2_pass else "HOLD"
    return exe, prepared, p2, status


def run_preflight(
    *, qpx: str | None, results_root: str | None, jacobian_test: bool = False
) -> int:
    _, prepared, p2, status = _preflight_result(
        qpx=qpx, results_root=results_root, jacobian_test=jacobian_test
    )
    summary_path = prepared["root"] / "summary.json"
    mode = "jacobian-diagnostic-preflight" if jacobian_test else "coupling-diagnostic-preflight"
    claim = (
        "construction readiness for PETSc assembled-vs-finite-difference Jacobian comparison on the fixed T1/T2 discriminator"
        if jacobian_test
        else "construction and observability readiness for the dt=1e-14 control vs dt=1e-13 failing coupling discriminator"
    )
    _write_summary(
        summary_path,
        {
            "issue": 43,
            "mode": mode,
            "status": status,
            "p3_executed": False,
            "jacobian_relative_tolerance": JACOBIAN_REL_TOL if jacobian_test else None,
            "claim": claim,
            "p1": prepared["p1"],
            "p2": p2,
        },
    )
    prefix = "ISSUE43_JACOBIAN_DIAGNOSTIC" if jacobian_test else "ISSUE43_COUPLING_DIAGNOSTIC"
    _emit_preflight_markers(
        prepared=prepared,
        p2=p2,
        status=status,
        summary_path=summary_path,
        prefix=prefix,
    )
    return 0 if status == "PASS" else 2


def _run_cases(*, exe: Path, prepared: dict[str, Any], jacobian_test: bool) -> dict[str, Any]:
    runtime: dict[str, Any] = {}
    prefix = "ISSUE43_JACOBIAN_DIAGNOSTIC" if jacobian_test else "ISSUE43_COUPLING_DIAGNOSTIC"
    for label in ("T1_dt1e14", "T2_dt1e13"):
        case = prepared["cases"][label]
        log_path = prepared["root"] / f"p3_{label}.log"
        print(f"{prefix}_CASE_START: {label}")
        run = run_qpx(
            exe,
            cwd=case["case_dir"],
            input_name="input.i",
            log_path=log_path,
            extra_args=("--color", "off"),
            stream=True,
        )
        print(f"{prefix}_CASE_END: {label} rc={run.returncode}")
        item = {
            "returncode": run.returncode,
            "wall_seconds": run.wall_seconds,
            "log": str(log_path),
            "trajectory": v5._solver_trajectory(log_path),
            "diagnostic": analyze_log(log_path, returncode=run.returncode),
        }
        if jacobian_test:
            item["jacobian"] = analyze_jacobian_log(log_path)
        runtime[label] = item
    return runtime


def run_runtime(*, qpx: str | None, results_root: str | None) -> int:
    exe, prepared, p2, status = _preflight_result(
        qpx=qpx, results_root=results_root, jacobian_test=False
    )
    if status != "PASS":
        summary_path = prepared["root"] / "summary.json"
        _write_summary(
            summary_path,
            {
                "issue": 43,
                "mode": "coupling-diagnostic-runtime",
                "status": "HOLD",
                "class": "HARNESS_OR_CONSTRUCTION_FAIL",
                "p3_executed": False,
                "p1": prepared["p1"],
                "p2": p2,
            },
        )
        _emit_preflight_markers(
            prepared=prepared,
            p2=p2,
            status="HOLD",
            summary_path=summary_path,
        )
        return 2

    print("ISSUE43_COUPLING_DIAGNOSTIC_PREFLIGHT: PASS")
    runtime = _run_cases(exe=exe, prepared=prepared, jacobian_test=False)
    t1 = runtime["T1_dt1e14"]
    t2 = runtime["T2_dt1e13"]
    t1_pass = (
        t1["returncode"] == 0
        and t1["trajectory"].get("time_steps_seen") == 1
        and t1["trajectory"].get("converged_steps", 0) >= 1
    )
    if not t1_pass:
        decision = {
            "status": "HOLD",
            "class": "DIAGNOSTIC_INSUFFICIENT",
            "reason": "diagnostic-only instrumentation did not reproduce the dt=1e-14 advancement control",
        }
    elif t2["returncode"] == 0:
        decision = {
            "status": "HOLD",
            "class": "DIAGNOSTIC_INSUFFICIENT",
            "reason": "historical dt=1e-13 failing branch unexpectedly passed under diagnostic-only instrumentation",
        }
    else:
        diagnostic = t2["diagnostic"]
        decision = {
            "status": "PASS" if diagnostic["class"] != "DIAGNOSTIC_INSUFFICIENT" else "HOLD",
            "class": diagnostic["class"],
            "reason": diagnostic["reason"],
            "pc_failure_reason": diagnostic.get("pc_failure_reason"),
        }

    summary_path = prepared["root"] / "summary.json"
    _write_summary(
        summary_path,
        {
            "issue": 43,
            "mode": "coupling-diagnostic-runtime",
            "status": decision["status"],
            "class": decision["class"],
            "scope": "failure localization only; no timestep tuning, relaxation-time promotion, or production architecture decision",
            "p3_executed": True,
            "p1": prepared["p1"],
            "p2": p2,
            "runtime": runtime,
            "decision": decision,
        },
    )

    print("ISSUE43_COUPLING_DIAGNOSTIC_T1_CONTROL: " + ("PASS" if t1_pass else "HOLD"))
    print(
        "ISSUE43_COUPLING_DIAGNOSTIC_T2_REPRODUCED: "
        + ("PASS" if t2["returncode"] != 0 else "HOLD")
    )
    print(f"ISSUE43_COUPLING_DIAGNOSTIC_PRECLASS: {decision['status']}")
    print(f"ISSUE43_COUPLING_DIAGNOSTIC_CLASS: {decision['class']}")
    if decision.get("pc_failure_reason"):
        print(f"ISSUE43_COUPLING_DIAGNOSTIC_PC_REASON: {decision['pc_failure_reason']}")
    print(f"ISSUE43_COUPLING_DIAGNOSTIC_REASON: {decision['reason']}")
    print(f"ISSUE43_COUPLING_DIAGNOSTIC_T1_LOG: {t1['log']}")
    print(f"ISSUE43_COUPLING_DIAGNOSTIC_T2_LOG: {t2['log']}")
    print(f"ISSUE43_COUPLING_DIAGNOSTIC_SUMMARY: {summary_path}")
    return 0 if decision["status"] == "PASS" else 2


def run_jacobian_runtime(*, qpx: str | None, results_root: str | None) -> int:
    exe, prepared, p2, status = _preflight_result(
        qpx=qpx, results_root=results_root, jacobian_test=True
    )
    prefix = "ISSUE43_JACOBIAN_DIAGNOSTIC"
    if status != "PASS":
        summary_path = prepared["root"] / "summary.json"
        _write_summary(
            summary_path,
            {
                "issue": 43,
                "mode": "jacobian-diagnostic-runtime",
                "status": "HOLD",
                "class": "HARNESS_OR_CONSTRUCTION_FAIL",
                "p3_executed": False,
                "p1": prepared["p1"],
                "p2": p2,
            },
        )
        _emit_preflight_markers(
            prepared=prepared,
            p2=p2,
            status="HOLD",
            summary_path=summary_path,
            prefix=prefix,
        )
        return 2

    print(f"{prefix}_PREFLIGHT: PASS")
    runtime = _run_cases(exe=exe, prepared=prepared, jacobian_test=True)
    t1 = runtime["T1_dt1e14"]
    t2 = runtime["T2_dt1e13"]

    t1_control = (
        t1["returncode"] == 0
        and t1["trajectory"].get("time_steps_seen") == 1
        and t1["trajectory"].get("converged_steps", 0) >= 1
    )
    t2_zero_pivot = (
        t2["returncode"] != 0
        and t2["diagnostic"].get("pc_failure_reason") == "FACTOR_NUMERIC_ZEROPIVOT"
    )
    t1_jacobian_pass = t1["jacobian"].get("status") == "PASS"
    t2_jacobian_pass = t2["jacobian"].get("status") == "PASS"

    if not t1_jacobian_pass or not t2_jacobian_pass:
        classes = {t1["jacobian"].get("class"), t2["jacobian"].get("class")}
        decision_class = (
            "JACOBIAN_MISMATCH"
            if "JACOBIAN_MISMATCH" in classes
            else "JACOBIAN_EVIDENCE_INSUFFICIENT"
        )
        decision = {
            "status": "HOLD",
            "class": decision_class,
            "reason": "at least one T1/T2 Jacobian comparison did not establish assembled-vs-finite-difference agreement",
        }
    elif not t1_control:
        decision = {
            "status": "HOLD",
            "class": "DIAGNOSTIC_INSUFFICIENT",
            "reason": "Jacobian instrumentation did not preserve the dt=1e-14 advancement control",
        }
    elif not t2_zero_pivot:
        decision = {
            "status": "HOLD",
            "class": "DIAGNOSTIC_INSUFFICIENT",
            "reason": "Jacobian instrumentation did not reproduce the dt=1e-13 FACTOR_NUMERIC_ZEROPIVOT signature",
        }
    else:
        decision = {
            "status": "PASS",
            "class": "JACOBIAN_CORRECT_ZERO_PIVOT_REPRODUCED",
            "reason": (
                "both T1/T2 assembled Jacobians agree with PETSc finite differences within the declared tolerance, "
                "while T2 still fails with FACTOR_NUMERIC_ZEROPIVOT"
            ),
        }

    summary_path = prepared["root"] / "summary.json"
    _write_summary(
        summary_path,
        {
            "issue": 43,
            "mode": "jacobian-diagnostic-runtime",
            "status": decision["status"],
            "class": decision["class"],
            "scope": "Jacobian correctness and zero-pivot reproduction only; no solver retuning or production architecture promotion",
            "jacobian_relative_tolerance": JACOBIAN_REL_TOL,
            "p3_executed": True,
            "p1": prepared["p1"],
            "p2": p2,
            "runtime": runtime,
            "decision": decision,
        },
    )

    print(f"{prefix}_T1_CONTROL: " + ("PASS" if t1_control else "HOLD"))
    print(f"{prefix}_T1_JACOBIAN: {t1['jacobian'].get('status')}")
    print(f"{prefix}_T2_JACOBIAN: {t2['jacobian'].get('status')}")
    print(f"{prefix}_T2_NUMERIC_ZERO_PIVOT: " + ("PASS" if t2_zero_pivot else "HOLD"))
    print(f"{prefix}_PRECLASS: {decision['status']}")
    print(f"{prefix}_CLASS: {decision['class']}")
    print(f"{prefix}_REASON: {decision['reason']}")
    print(f"{prefix}_T1_LOG: {t1['log']}")
    print(f"{prefix}_T2_LOG: {t2['log']}")
    print(f"{prefix}_SUMMARY: {summary_path}")
    return 0 if decision["status"] == "PASS" else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the bounded Issue43 electron-Poisson coupling failure diagnostic"
    )
    parser.add_argument("--qpx", help="path to user-local qpx-opt")
    parser.add_argument("--results-root")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-test", action="store_true")
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--jacobian-preflight", action="store_true")
    mode.add_argument("--jacobian-run", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()
    if self_test() != 0:
        return 1
    try:
        if args.jacobian_run:
            return run_jacobian_runtime(qpx=args.qpx, results_root=args.results_root)
        if args.jacobian_preflight:
            return run_preflight(qpx=args.qpx, results_root=args.results_root, jacobian_test=True)
        if args.run:
            return run_runtime(qpx=args.qpx, results_root=args.results_root)
        return run_preflight(qpx=args.qpx, results_root=args.results_root)
    except (FastPlasmaCouplingDiagnosticError, MooseInputError) as exc:
        prefix = "ISSUE43_JACOBIAN_DIAGNOSTIC" if args.jacobian_preflight or args.jacobian_run else "ISSUE43_COUPLING_DIAGNOSTIC"
        print(f"{prefix}_PRECLASS: HOLD")
        print(f"{prefix}_CLASS: HARNESS_OR_CONSTRUCTION_FAIL")
        print(f"{prefix}_REASON: {exc}")
        return 2


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv[1:]))
