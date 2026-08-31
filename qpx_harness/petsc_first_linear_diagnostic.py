"""Issue45 bounded C0 augmented-Jacobian / PETSc first-linear diagnostic.

Construction is owned by electron_inventory_nullspace. Preflight stops at P2;
only --run enters the single first-linear P3 discriminator.
"""
from __future__ import annotations

import argparse
import math
import re
from pathlib import Path
from typing import Any

from . import artifacts
from . import electron_inventory_nullspace as inv
from . import evidence
from . import fast_plasma_coupling_diagnostic as coupling_diag
from .moose_input import MooseInput, MooseInputError
from .runtime import resolve_executable, run_qpx, validate_executable

ISSUE = 45
TARGET = inv.C0_TARGET
DIAGNOSTIC_NL_MAX_ITS = 1
JACOBIAN_REL_TOL = coupling_diag.JACOBIAN_REL_TOL
FIRST_LINEAR_PETSC_OPTIONS = (
    "-snes_test_jacobian",
    "-ksp_view",
    "-ksp_monitor_true_residual",
)
REQUIRED_EXISTING_OPTIONS = ("-snes_converged_reason", "-ksp_converged_reason")
_FLOAT = r"[+\-]?(?:(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+\-]?\d+)?|nan|inf(?:inity)?)"


class PetscFirstLinearDiagnosticError(RuntimeError):
    pass


def _petsc_options(text: str) -> list[str]:
    raw = inv._unquote(inv._parameter_value(text, "Executioner", "petsc_options"))
    return raw.split() if raw else []


def _merge_options(text: str, required: tuple[str, ...]) -> str:
    options = _petsc_options(text)
    for option in required:
        if option not in options:
            options.append(option)
    return inv._set_or_insert_parameter(
        text, "Executioner", "petsc_options", "'" + " ".join(options) + "'"
    )


def instrument_first_linear(text: str) -> tuple[str, dict[str, Any]]:
    out = inv._set_or_insert_parameter(
        text, "Executioner", "nl_max_its", str(DIAGNOSTIC_NL_MAX_ITS)
    )
    out = _merge_options(out, REQUIRED_EXISTING_OPTIONS + FIRST_LINEAR_PETSC_OPTIONS)
    MooseInput(out)
    return out, {
        "target": TARGET,
        "diagnostic_nl_max_its": DIAGNOSTIC_NL_MAX_ITS,
        "petsc_options_added": list(FIRST_LINEAR_PETSC_OPTIONS),
        "physics_changed": False,
        "closure_changed": False,
        "solver_realization_changed": False,
        "diagnostic_horizon_changed": True,
    }


def _normalized_diagnostic_text(text: str) -> str:
    out = inv._set_or_insert_parameter(
        text, "Executioner", "nl_max_its", "<DIAGNOSTIC_NL_MAX_ITS>"
    )
    return inv._set_or_insert_parameter(
        out, "Executioner", "petsc_options", "'<DIAGNOSTIC_PETSC_OPTIONS>'"
    )


def audit_first_linear_structure(base_text: str, diagnostic_text: str) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, observed: Any, required: Any) -> None:
        checks.append({"id": name, "status": "PASS" if ok else "FAIL", "observed": observed, "required": required})

    closure = inv.audit_constrained_quasisteady_structure(
        diagnostic_text, expected_macro_avg=TARGET
    )
    add("canonical-c0-closure-structure", closure["status"] == "PASS", closure["status"], "PASS")
    nl_max = inv._unquote(inv._parameter_value(diagnostic_text, "Executioner", "nl_max_its"))
    add("first-linear-nonlinear-horizon", nl_max == "1", nl_max, "1")
    options = _petsc_options(diagnostic_text)
    add("existing-reason-options-preserved", all(x in options for x in REQUIRED_EXISTING_OPTIONS), options, list(REQUIRED_EXISTING_OPTIONS))
    for option in FIRST_LINEAR_PETSC_OPTIONS:
        add(f"diagnostic-option:{option}", option in options, options, option)
    add("no-full-jacobian-matrix-dump", "-snes_test_jacobian_view" not in options, options, "absent")
    inames = inv._words(inv._parameter_value(diagnostic_text, "Executioner", "petsc_options_iname"))
    values = inv._words(inv._parameter_value(diagnostic_text, "Executioner", "petsc_options_value"))
    add(
        "lu-nonzero-shift-preserved",
        inames == ["-pc_type", "-pc_factor_shift_type"] and values == ["lu", "NONZERO"],
        {"iname": inames, "value": values},
        {"iname": ["-pc_type", "-pc_factor_shift_type"], "value": ["lu", "NONZERO"]},
    )
    same = _normalized_diagnostic_text(base_text) == _normalized_diagnostic_text(diagnostic_text)
    add("diagnostic-only-input-difference", same, same, True)
    blockers = [x for x in checks if x["status"] != "PASS"]
    return {
        "status": "PASS" if not blockers else "HOLD",
        "class": "FIRST_LINEAR_STRUCTURE_PASS" if not blockers else "FIRST_LINEAR_STRUCTURE_FAIL",
        "checks": checks,
        "blockers": blockers,
        "closure": closure,
    }


def _parse_true_residuals(text: str) -> list[dict[str, float]]:
    pattern = re.compile(
        rf"(?m)^\s*(\d+)\s+KSP\s+.*?resid norm\s+({_FLOAT})\s+true resid norm\s+({_FLOAT})\s+\|\|r\(i\)\|\|/\|\|b\|\|\s+({_FLOAT})\s*$",
        re.IGNORECASE,
    )
    rows: list[dict[str, float]] = []
    for m in pattern.finditer(text):
        try:
            rows.append({
                "iteration": int(m.group(1)),
                "reported_residual": float(m.group(2)),
                "true_residual": float(m.group(3)),
                "relative_true_residual": float(m.group(4)),
            })
        except ValueError:
            pass
    return rows


def _parse_first_linear(text: str) -> dict[str, Any] | None:
    m = re.search(
        r"Linear solve\s+(converged|did not converge)\s+due to\s+([A-Z0-9_]+)\s+iterations\s+(\d+)",
        text,
    )
    if not m:
        return None
    return {"converged": m.group(1) == "converged", "reason": m.group(2), "iterations": int(m.group(3))}


def _parse_first_ksp_view(text: str) -> dict[str, Any]:
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip().startswith("KSP Object:")), None)
    if start is None:
        return {}
    base_indent = len(lines[start]) - len(lines[start].lstrip())
    ksp_type = restart = pc_type = None
    in_pc = False
    for line in lines[start + 1 :]:
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())
        if stripped.startswith("KSP Object:") and indent <= base_indent:
            break
        if stripped.startswith("PC Object:") and indent <= base_indent + 2:
            in_pc = True
            continue
        mtype = re.match(r"type:\s+(\S+)", stripped)
        if mtype:
            if in_pc and pc_type is None:
                pc_type = mtype.group(1).lower()
            elif not in_pc and ksp_type is None:
                ksp_type = mtype.group(1).lower()
        if not in_pc and restart is None:
            mr = re.search(r"\brestart\s*=\s*(\d+)", stripped)
            if mr:
                restart = int(mr.group(1))
        if in_pc and pc_type is not None and ksp_type is not None:
            break
    return {"ksp_type": ksp_type, "restart": restart, "pc_type": pc_type}


def analyze_first_linear_text(text: str, *, returncode: int) -> dict[str, Any]:
    jac = coupling_diag.analyze_jacobian_text(text, relative_tolerance=JACOBIAN_REL_TOL)
    core = coupling_diag.analyze_log_text(text, returncode=returncode)
    identity = _parse_first_ksp_view(text)
    true_rows = _parse_true_residuals(text)
    linear = _parse_first_linear(text)

    def result(status: str, klass: str, reason: str, **extra: Any) -> dict[str, Any]:
        return {
            "status": status,
            "class": klass,
            "reason": reason,
            "jacobian": jac,
            "ksp_identity": identity,
            "true_residuals": true_rows,
            "first_linear": linear,
            "core": core,
            **extra,
        }

    if jac.get("class") == "JACOBIAN_MISMATCH":
        return result("HOLD", "JACOBIAN_MISMATCH", "the augmented constrained Jacobian exceeds the declared assembled-vs-FD tolerance")
    pc_failure = (
        core.get("pc_failure_reason")
        or (linear is not None and linear.get("reason") in {"DIVERGED_PC_FAILED", "DIVERGED_PCSETUP_FAILED"})
        or re.search(r"FACTOR_(?:NUMERIC|STRUCT)_ZEROPIVOT|PC failed due to|zero pivot", text, re.IGNORECASE)
    )
    if pc_failure:
        return result("HOLD", "PC_OR_FACTORIZATION_FAIL", "the first-linear diagnostic exposes a PETSc PC/factorization failure signature")
    if core.get("nonfinite_residuals") or core.get("nonlinear_reason") == "DIVERGED_FUNCTION_NANORINF":
        return result("HOLD", "NONFINITE_FAIL", "the first-linear diagnostic contains non-finite residual/function evidence")
    complete = (
        jac.get("status") == "PASS"
        and identity.get("ksp_type") is not None
        and identity.get("pc_type") is not None
        and bool(true_rows)
        and linear is not None
    )
    if not complete:
        return result("HOLD", "DIAGNOSTIC_INSUFFICIENT", "Jacobian, KSP identity, true-residual, and first-linear evidence are not all observable")

    restart = identity.get("restart")
    iterations = int(linear["iterations"])
    aligned = (
        identity["ksp_type"] == "gmres"
        and isinstance(restart, int)
        and restart > 0
        and iterations > 0
        and iterations % restart == 0
    )
    finite_true = all(
        math.isfinite(row["true_residual"]) and math.isfinite(row["relative_true_residual"])
        for row in true_rows
    )
    if linear["reason"] == "DIVERGED_BREAKDOWN" and aligned and finite_true:
        return result(
            "PASS",
            "GMRES_RESTART_BREAKDOWN",
            "the augmented Jacobian passes the assembled-vs-FD gate and the effective GMRES solve reaches DIVERGED_BREAKDOWN at a restart boundary with finite true-residual evidence",
            restart_aligned=True,
        )
    if linear["converged"]:
        return result("HOLD", "FIRST_LINEAR_BEHAVIOR_CHANGED", "the bounded C0 first linear solve converged instead of reproducing the historical breakdown", restart_aligned=aligned)
    return result("HOLD", "DIAGNOSTIC_INSUFFICIENT", "the observed linear failure does not satisfy the predeclared GMRES-restart discriminator", restart_aligned=aligned)


def _synthetic_log(jac_rel: float = 2.0e-9) -> str:
    return f"""---------- Testing Jacobian -------------
||J - Jfd||_F/||J||_F = {jac_rel:.12e}, ||J - Jfd||_F = 2.0e-08
    |residual|_2 of individual variables:
       n_e:                  5.0e-16
       potential_plasma:     8.0e-03
       r45_inventory_lambda: 0
  0 KSP preconditioned resid norm 8.0e-03 true resid norm 8.0e-03 ||r(i)||/||b|| 1.0e+00
 30 KSP preconditioned resid norm 1.0e-12 true resid norm 2.0e-03 ||r(i)||/||b|| 2.5e-01
Linear solve did not converge due to DIVERGED_BREAKDOWN iterations 30
KSP Object: 1 MPI process
  type: gmres
    restart=30, using modified Gram-Schmidt orthogonalization
  maximum iterations=10000, initial guess is zero
  left preconditioning
  using PRECONDITIONED norm type for convergence test
PC Object: 1 MPI process
  type: lu
    out-of-place factorization
Nonlinear solve did not converge due to DIVERGED_MAX_IT iterations 1
"""


def self_test() -> int:
    try:
        base = inv._synthetic_constrained_input(TARGET)
        diag, _ = instrument_first_linear(base)
        if audit_first_linear_structure(base, diag)["status"] != "PASS":
            raise AssertionError("positive first-linear structure did not pass")
        mutated = diag.replace("boundary = outlet", "boundary = plasma_cover", 1)
        if audit_first_linear_structure(base, mutated)["status"] == "PASS":
            raise AssertionError("non-diagnostic physics mutation was accepted")
        if analyze_first_linear_text(_synthetic_log(), returncode=1)["class"] != "GMRES_RESTART_BREAKDOWN":
            raise AssertionError("GMRES restart breakdown did not classify")
        if analyze_first_linear_text(_synthetic_log(1.0e-3), returncode=1)["class"] != "JACOBIAN_MISMATCH":
            raise AssertionError("Jacobian mismatch mutation was not detected")
        pc_fail = _synthetic_log().replace(
            "Linear solve did not converge due to DIVERGED_BREAKDOWN iterations 30",
            "Linear solve did not converge due to DIVERGED_PC_FAILED iterations 0\nPC failed due to FACTOR_NUMERIC_ZEROPIVOT",
            1,
        )
        if analyze_first_linear_text(pc_fail, returncode=1)["class"] != "PC_OR_FACTORIZATION_FAIL":
            raise AssertionError("PC/factorization mutation was not detected")
        nonfinite = _synthetic_log().replace("n_e:                  5.0e-16", "n_e:                  nan", 1)
        if analyze_first_linear_text(nonfinite, returncode=1)["class"] != "NONFINITE_FAIL":
            raise AssertionError("non-finite mutation was not detected")
        missing_view = _synthetic_log().split("KSP Object:", 1)[0]
        if analyze_first_linear_text(missing_view, returncode=1)["class"] != "DIAGNOSTIC_INSUFFICIENT":
            raise AssertionError("missing KSP identity was over-classified")
    except Exception as exc:
        print(f"ISSUE45_FIRST_LINEAR_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE45_FIRST_LINEAR_SELFTEST: PASS")
    return 0


def _prepare_case(exe: Path, results_root: str | None) -> dict[str, Any]:
    base_case, base_text, radial_span = inv._base_case_context()
    base_c0 = inv._build_constrained_quasisteady_input(
        base_text, radial_span=radial_span, macro_avg=TARGET, runtime_observability=True
    )
    text, instrumentation = instrument_first_linear(base_c0)
    p1 = audit_first_linear_structure(base_c0, text)
    root = inv._evidence_root(exe=exe, results_root=results_root, stem="issue45_first_linear_diagnostic")
    case_dir = root / "case"
    inv._stage_case(base_case, case_dir, text)
    return {"root": root, "case_dir": case_dir, "input_path": case_dir / "input.i", "p1": p1, "instrumentation": instrumentation}


def _run_p2(exe: Path, prepared: dict[str, Any]) -> dict[str, Any]:
    log = prepared["root"] / "p2_check_input.log"
    run = run_qpx(exe, cwd=prepared["case_dir"], input_name="input.i", log_path=log, extra_args=("--check-input", "--color", "off"), stream=False)
    return {
        "status": "PASS" if run.returncode == 0 else "HOLD",
        "returncode": run.returncode,
        "wall_seconds": run.wall_seconds,
        "log": str(log),
        "identity": {**evidence.identity_record(executable=exe, input_path=prepared["input_path"]), "qpx_sha256": evidence.sha256_file(exe)},
    }


def _preflight(qpx: str | None, results_root: str | None) -> tuple[Path, dict[str, Any], dict[str, Any], str]:
    exe = resolve_executable(qpx)
    validate_executable(exe)
    prepared = _prepare_case(exe, results_root)
    p1_pass = prepared["p1"]["status"] == "PASS"
    p2 = _run_p2(exe, prepared) if p1_pass else {}
    status = "PASS" if p1_pass and p2.get("status") == "PASS" else "HOLD"
    return exe, prepared, p2, status


def _write_summary(prepared: dict[str, Any], p2: dict[str, Any], status: str, *, p3: dict[str, Any] | None = None) -> Path:
    path = prepared["root"] / "summary.json"
    payload: dict[str, Any] = {
        "issue": ISSUE,
        "mode": "first-linear-diagnostic" if p3 is not None else "first-linear-preflight",
        "status": p3["decision"]["status"] if p3 is not None else status,
        "p3_executed": p3 is not None,
        "p3_authorized_by_harness": False,
        "target": TARGET,
        "instrumentation": prepared["instrumentation"],
        "p1": prepared["p1"],
        "p2": p2,
    }
    if p3 is None:
        payload["decision"] = {
            "status": status,
            "class": "FIRST_LINEAR_DIAGNOSTIC_READY" if status == "PASS" else "HARNESS_OR_CONSTRUCTION_FAIL",
            "reason": "C0 physics/closure is preserved and user-local QPX accepts the bounded Jacobian/KSP/true-residual diagnostic" if status == "PASS" else "the first-linear diagnostic did not pass all P0/P1/P2 gates",
        }
    else:
        payload.update(p3)
    artifacts.write_json_bundle(path.parent, {"summary": (path.name, payload)})
    return path


def run_preflight(qpx: str | None, results_root: str | None) -> int:
    _, prepared, p2, status = _preflight(qpx, results_root)
    path = _write_summary(prepared, p2, status)
    print(f"ISSUE45_FIRST_LINEAR_P1: {prepared['p1']['status']}")
    print(f"ISSUE45_FIRST_LINEAR_P2: {p2.get('status', 'HOLD')}")
    print(f"ISSUE45_FIRST_LINEAR_PREFLIGHT: {status}")
    print("ISSUE45_FIRST_LINEAR_CLASS: " + ("FIRST_LINEAR_DIAGNOSTIC_READY" if status == "PASS" else "HARNESS_OR_CONSTRUCTION_FAIL"))
    print(f"ISSUE45_FIRST_LINEAR_SUMMARY: {path}")
    return 0 if status == "PASS" else 2


def run_diagnostic(qpx: str | None, results_root: str | None) -> int:
    exe, prepared, p2, status = _preflight(qpx, results_root)
    if status != "PASS":
        path = _write_summary(prepared, p2, status)
        print("ISSUE45_FIRST_LINEAR_PREFLIGHT: HOLD")
        print("ISSUE45_FIRST_LINEAR_CLASS: HARNESS_OR_CONSTRUCTION_FAIL")
        print(f"ISSUE45_FIRST_LINEAR_SUMMARY: {path}")
        return 2
    print("ISSUE45_FIRST_LINEAR_PREFLIGHT: PASS")
    log = prepared["root"] / "p3_first_linear.log"
    run = run_qpx(exe, cwd=prepared["case_dir"], input_name="input.i", log_path=log, extra_args=("--color", "off"), stream=True)
    print(f"ISSUE45_FIRST_LINEAR_CASE_END: rc={run.returncode}")
    decision = analyze_first_linear_text(log.read_text(errors="replace") if log.is_file() else "", returncode=run.returncode)
    p3 = {
        "evr_count_for_this_batch": 1,
        "scope": "one bounded C0 initial-state first-linear discriminator",
        "runtime": {
            "returncode": run.returncode,
            "wall_seconds": run.wall_seconds,
            "log": str(log),
            "identity": {**evidence.identity_record(executable=exe, input_path=prepared["input_path"]), "qpx_sha256": evidence.sha256_file(exe)},
        },
        "decision": decision,
    }
    path = _write_summary(prepared, p2, status, p3=p3)
    jac = decision.get("jacobian", {}).get("status", "HOLD")
    identity = decision.get("ksp_identity", {})
    true_rows = decision.get("true_residuals") or []
    print(f"ISSUE45_FIRST_LINEAR_JACOBIAN: {jac}")
    print("ISSUE45_FIRST_LINEAR_KSP_IDENTITY: " + ("PASS" if identity.get("ksp_type") and identity.get("pc_type") else "HOLD"))
    if identity:
        print(f"ISSUE45_FIRST_LINEAR_KSP: type={identity.get('ksp_type')} restart={identity.get('restart')} pc={identity.get('pc_type')}")
    print("ISSUE45_FIRST_LINEAR_TRUE_RESIDUAL: " + ("PASS" if true_rows else "HOLD"))
    print(f"ISSUE45_FIRST_LINEAR_PRECLASS: {decision['status']}")
    print(f"ISSUE45_FIRST_LINEAR_CLASS: {decision['class']}")
    print(f"ISSUE45_FIRST_LINEAR_REASON: {decision['reason']}")
    print(f"ISSUE45_FIRST_LINEAR_LOG: {log}")
    print(f"ISSUE45_FIRST_LINEAR_SUMMARY: {path}")
    return 0 if decision["status"] == "PASS" else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Issue45 bounded C0 PETSc first-linear diagnostic")
    parser.add_argument("--qpx", help="path to user-local qpx-opt")
    parser.add_argument("--results-root")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-test", action="store_true")
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--run", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    if self_test() != 0:
        return 1
    try:
        return run_diagnostic(args.qpx, args.results_root) if args.run else run_preflight(args.qpx, args.results_root)
    except (PetscFirstLinearDiagnosticError, inv.ElectronInventoryNullspaceError, MooseInputError) as exc:
        print("ISSUE45_FIRST_LINEAR_PREFLIGHT: HOLD")
        print("ISSUE45_FIRST_LINEAR_CLASS: HARNESS_OR_CONSTRUCTION_FAIL")
        print(f"ISSUE45_FIRST_LINEAR_REASON: {exc}")
        return 2


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))