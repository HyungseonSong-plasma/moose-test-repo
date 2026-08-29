"""Bounded Issue #43 electron-Poisson coupling failure localization harness.

This harness does not tune the timestep or change the accepted electron/Poisson
physics.  It instruments the already-established discriminator boundary:

  T1: full feedback, dt=1e-14, one step (known-good advancement control)
  T2: full feedback, dt=1e-13, one step (historical first-step failure)

P0/P1/P2 may be run without entering physics P3.  Runtime mode reruns those
preconditions and then executes only T1 and T2 with diagnostic-only MOOSE/PETSc
observability enabled.
"""

from __future__ import annotations

import argparse
import math
import re
from pathlib import Path
from typing import Any

from . import evidence
from . import execution_contract as ec
from . import fast_plasma_relaxation_v2 as v2
from . import fast_plasma_relaxation_v5 as v5
from . import output_observation_contract as ooc
from .moose_input import MooseInput, MooseInputError
from .preflight import validate_parser_symbols_text
from .runtime import run_qpx


DT_CONTROL = 1.0e-14
DT_FAIL = 1.0e-13
STEPS = 1
DIAGNOSTIC_PETSC_OPTIONS = (
    "-snes_converged_reason",
    "-ksp_converged_reason",
    "-snes_monitor",
    "-ksp_monitor",
)


class FastPlasmaCouplingDiagnosticError(RuntimeError):
    pass


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
    doc = MooseInput(text)
    matches = doc.find("Debug")
    if len(matches) > 1:
        raise FastPlasmaCouplingDiagnosticError("multiple top-level [Debug] blocks")
    if not matches:
        suffix = "" if text.endswith("\n") else "\n"
        text = text + suffix + "\n[Debug]\n  show_var_residual_norms = true\n[]\n"
        MooseInput(text)
        return text
    return _set_or_insert_parameter(text, "Debug", "show_var_residual_norms", "true")


def _merge_petsc_options(text: str) -> str:
    raw = _parameter_value(text, "Executioner", "petsc_options")
    existing: list[str] = []
    if raw:
        value = raw.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        existing = value.split()
    merged = list(existing)
    for option in DIAGNOSTIC_PETSC_OPTIONS:
        if option not in merged:
            merged.append(option)
    return _set_or_insert_parameter(
        text,
        "Executioner",
        "petsc_options",
        "'" + " ".join(merged) + "'",
    )


def instrument_input(input_text: str) -> tuple[str, dict[str, Any]]:
    """Add diagnostics without changing the physical residual or solver mathematics."""
    text = _ensure_debug_block(input_text)
    text = _set_or_insert_parameter(text, "Executioner", "verbose", "true")
    text = _merge_petsc_options(text)
    text = _set_or_insert_parameter(text, "Outputs/console", "all_variable_norms", "true")
    return text, {
        "debug_show_var_residual_norms": True,
        "executioner_verbose": True,
        "console_all_variable_norms": True,
        "petsc_options_added": list(DIAGNOSTIC_PETSC_OPTIONS),
        "physics_or_numerics_changed": False,
    }


def _build_case(base_text: str, *, dt: float, radial_span: float) -> tuple[str, dict[str, Any]]:
    uninstrumented = v5._build_feedback_v5(
        base_text,
        dt=dt,
        steps=STEPS,
        radial_span=radial_span,
    )
    instrumented, instrumentation = instrument_input(uninstrumented)
    return instrumented, {
        "dt": dt,
        "steps": STEPS,
        "instrumentation": instrumentation,
    }


def _contains_required_petsc_options(text: str) -> bool:
    raw = _parameter_value(text, "Executioner", "petsc_options") or ""
    return all(option in raw.split() or option in raw for option in DIAGNOSTIC_PETSC_OPTIONS)


def _p1_case(case_id: str, text: str, *, dt: float) -> dict[str, Any]:
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
        _contains_required_petsc_options(text),
        _parameter_value(text, "Executioner", "petsc_options"),
        list(DIAGNOSTIC_PETSC_OPTIONS),
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
        match = re.match(rf"^\s*([A-Za-z_][A-Za-z0-9_]*):\s*({_FLOAT})\s*$", line, re.IGNORECASE)
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
        match = re.match(rf"^\s*([A-Za-z_][A-Za-z0-9_]*):\s*({_FLOAT})(?:\s+.*)?$", line, re.IGNORECASE)
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
    hits: list[str] = []
    for line in text.splitlines():
        if any(re.search(pattern, line, re.IGNORECASE) for pattern in patterns):
            hits.append(line.strip())
    return hits


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

    pc_hits = _line_hits(
        text,
        (
            r"DIVERGED_PC_FAILED",
            r"DIVERGED_PCSETUP_FAILED",
            r"zero pivot",
            r"factor(?:ization|ization failed| numeric)",
            r"PCSetUp.*fail",
        ),
    )
    factorization_hits = _line_hits(
        text,
        (
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

    scaling_ratio = None
    selected_scaling = [
        abs(scaling[name])
        for name in ("n_e", "potential_plasma")
        if name in scaling and math.isfinite(scaling[name]) and scaling[name] != 0.0
    ]
    if len(selected_scaling) == 2:
        scaling_ratio = max(selected_scaling) / min(selected_scaling)

    finite_residual_blocks = bool(residual_blocks) and not nonfinite_residuals
    if pc_hits or linear_reason in {"DIVERGED_PC_FAILED", "DIVERGED_PCSETUP_FAILED"}:
        decision_class = "PC_OR_FACTORIZATION_FAIL"
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
        if not meta["physics_or_numerics_changed"] is False:
            raise AssertionError("diagnostic instrumentation changed physics/numerics metadata")
        if _parameter_value(tuned, "Debug", "show_var_residual_norms") != "true":
            raise AssertionError("Debug residual instrumentation missing")
        if _parameter_value(tuned, "Executioner", "verbose") != "true":
            raise AssertionError("Executioner verbose instrumentation missing")
        if _parameter_value(tuned, "Outputs/console", "all_variable_norms") != "true":
            raise AssertionError("Console variable-norm instrumentation missing")
        if not _contains_required_petsc_options(tuned):
            raise AssertionError("PETSc diagnostic options missing")

        already = base.replace(
            "  petsc_options_iname = '-pc_type'\n",
            "  petsc_options = '-snes_view'\n  petsc_options_iname = '-pc_type'\n",
        )
        merged, _ = instrument_input(already)
        raw = _parameter_value(merged, "Executioner", "petsc_options") or ""
        if "-snes_view" not in raw:
            raise AssertionError("existing PETSc option was not preserved")

        pc_log = """Automatic scaling factors:
 n_e: 1e-16
 potential_plasma: 1

 0 Nonlinear |R| = 1e+00
 |residual|_2 of individual variables:
 n_e: 8e-01
 potential_plasma: 6e-01
Linear solve did not converge due to DIVERGED_PC_FAILED iterations 0
Nonlinear solve did not converge due to DIVERGED_FUNCTION_NANORINF iterations 0
"""
        pc = analyze_log_text(pc_log, returncode=1)
        if pc["class"] != "PC_OR_FACTORIZATION_FAIL":
            raise AssertionError("PC failure was not given first-failure priority")

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
    except Exception as exc:
        print(f"ISSUE43_COUPLING_DIAGNOSTIC_SELFTEST: FAIL ({exc})")
        return 1

    print("ISSUE43_COUPLING_DIAGNOSTIC_SELFTEST: PASS")
    return 0


def _prepare_cases(*, exe: Path, results_root: str | None) -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[1]
    base_case = repo_root / v2.v1.BASE_CASE_RELATIVE
    if not base_case.is_dir():
        raise FastPlasmaCouplingDiagnosticError(
            f"missing accepted qvt electron control: {base_case}"
        )

    mesh = v2.mesh_stats(base_case / "qvt.msh")
    radial_span = float(mesh["bbox_span_m"]["x"])
    base_text = (base_case / "input.i").read_text()
    variants = {
        "T1_dt1e14": _build_case(base_text, dt=DT_CONTROL, radial_span=radial_span),
        "T2_dt1e13": _build_case(base_text, dt=DT_FAIL, radial_span=radial_span),
    }

    p1 = {
        label: _p1_case(label, text, dt=float(meta["dt"]))
        for label, (text, meta) in variants.items()
    }
    p1_status = "PASS" if all(item["status"] == "PASS" for item in p1.values()) else "HOLD"

    evidence_root = (
        Path(results_root).expanduser().resolve()
        if results_root
        else exe.parent / "temp" / "results"
    )
    root = evidence.ensure_fresh_directory(
        evidence_root / f"issue43_coupling_diagnostic_{evidence.utc_timestamp()}"
    )
    cases_root = root / "cases"
    cases_root.mkdir()

    cases: dict[str, Any] = {}
    for label, (text, meta) in variants.items():
        case_dir = cases_root / label
        v2.v1._copy_case(base_case, case_dir, text)
        v2.v1._validate_assets(case_dir)
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


def _emit_preflight_markers(*, prepared: dict[str, Any], p2: dict[str, Any], status: str, summary_path: Path) -> None:
    print(f"ISSUE43_COUPLING_DIAGNOSTIC_P1: {prepared['p1_status']}")
    for label in ("T1_dt1e14", "T2_dt1e13"):
        print(
            f"ISSUE43_COUPLING_DIAGNOSTIC_P2_{label}: "
            + ("PASS" if p2[label]["returncode"] == 0 else "FAIL")
        )
        if p2[label]["returncode"] != 0:
            failure = p2[label]["failure"]
            print(
                f"ISSUE43_COUPLING_DIAGNOSTIC_P2_{label}_CLASS: "
                f"{failure.get('class')}"
            )
            print(
                f"ISSUE43_COUPLING_DIAGNOSTIC_P2_{label}_REASON: "
                f"{failure.get('reason')}"
            )
            if failure.get("detail"):
                print(
                    f"ISSUE43_COUPLING_DIAGNOSTIC_P2_{label}_DETAIL: "
                    f"{failure['detail']}"
                )
    print(f"ISSUE43_COUPLING_DIAGNOSTIC_PREFLIGHT: {status}")
    print(f"ISSUE43_COUPLING_DIAGNOSTIC_SUMMARY: {summary_path}")


def run_preflight(*, qpx: str | None, results_root: str | None) -> int:
    exe = v2.resolve_executable(qpx)
    v2.validate_executable(exe)
    prepared = _prepare_cases(exe=exe, results_root=results_root)
    p2 = _run_p2(exe=exe, prepared=prepared) if prepared["p1_status"] == "PASS" else {}
    p2_pass = bool(p2) and all(item["returncode"] == 0 for item in p2.values())
    status = "PASS" if prepared["p1_status"] == "PASS" and p2_pass else "HOLD"
    summary_path = prepared["root"] / "summary.json"
    v2._write_json(
        summary_path,
        {
            "issue": 43,
            "mode": "coupling-diagnostic-preflight",
            "status": status,
            "p3_executed": False,
            "claim": "construction and observability readiness for the dt=1e-14 control vs dt=1e-13 failing coupling discriminator",
            "p1": prepared["p1"],
            "p2": p2,
        },
    )
    _emit_preflight_markers(
        prepared=prepared,
        p2=p2,
        status=status,
        summary_path=summary_path,
    )
    return 0 if status == "PASS" else 2


def run_runtime(*, qpx: str | None, results_root: str | None) -> int:
    exe = v2.resolve_executable(qpx)
    v2.validate_executable(exe)
    prepared = _prepare_cases(exe=exe, results_root=results_root)
    p2 = _run_p2(exe=exe, prepared=prepared) if prepared["p1_status"] == "PASS" else {}
    p2_pass = bool(p2) and all(item["returncode"] == 0 for item in p2.values())
    if prepared["p1_status"] != "PASS" or not p2_pass:
        summary_path = prepared["root"] / "summary.json"
        v2._write_json(
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
    runtime: dict[str, Any] = {}
    for label in ("T1_dt1e14", "T2_dt1e13"):
        case = prepared["cases"][label]
        log_path = prepared["root"] / f"p3_{label}.log"
        print(f"ISSUE43_COUPLING_DIAGNOSTIC_CASE_START: {label}")
        run = run_qpx(
            exe,
            cwd=case["case_dir"],
            input_name="input.i",
            log_path=log_path,
            extra_args=("--color", "off"),
            stream=True,
        )
        print(f"ISSUE43_COUPLING_DIAGNOSTIC_CASE_END: {label} rc={run.returncode}")
        runtime[label] = {
            "returncode": run.returncode,
            "wall_seconds": run.wall_seconds,
            "log": str(log_path),
            "trajectory": v5._solver_trajectory(log_path),
            "diagnostic": analyze_log(log_path, returncode=run.returncode),
        }

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
        }

    summary_path = prepared["root"] / "summary.json"
    v2._write_json(
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

    print(
        "ISSUE43_COUPLING_DIAGNOSTIC_T1_CONTROL: "
        + ("PASS" if t1_pass else "HOLD")
    )
    print(
        "ISSUE43_COUPLING_DIAGNOSTIC_T2_REPRODUCED: "
        + ("PASS" if t2["returncode"] != 0 else "HOLD")
    )
    print(f"ISSUE43_COUPLING_DIAGNOSTIC_PRECLASS: {decision['status']}")
    print(f"ISSUE43_COUPLING_DIAGNOSTIC_CLASS: {decision['class']}")
    print(f"ISSUE43_COUPLING_DIAGNOSTIC_REASON: {decision['reason']}")
    print(f"ISSUE43_COUPLING_DIAGNOSTIC_T1_LOG: {t1['log']}")
    print(f"ISSUE43_COUPLING_DIAGNOSTIC_T2_LOG: {t2['log']}")
    print(f"ISSUE43_COUPLING_DIAGNOSTIC_SUMMARY: {summary_path}")
    return 0 if decision["status"] == "PASS" else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the bounded Issue43 electron-Poisson coupling failure diagnostic"
    )
    parser.add_argument("--qpx", help="path to user-local qpx-opt")
    parser.add_argument("--results-root")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()
    if self_test() != 0:
        return 1
    if args.run:
        return run_runtime(qpx=args.qpx, results_root=args.results_root)
    if args.preflight:
        return run_preflight(qpx=args.qpx, results_root=args.results_root)
    parser.error("select --preflight or --run")
    return 2


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv[1:]))
