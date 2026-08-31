"""Semantic runtime owner for the Issue45 bounded first-linear diagnostic.

Scientific construction and log-classification policy are owned by
``recipes.issue45_first_linear``. This module composes that policy with the
Issue45 case/evidence/runtime orchestration and preserves the stable diagnostic
surface without depending on the historical ``petsc_first_linear_diagnostic``
owner.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from recipes import issue45_first_linear as first_linear_recipe

from . import artifacts
from . import electron_inventory_nullspace as inv
from . import evidence
from .moose import parameters as mp
from .moose_input import MooseInput, MooseInputError
from .petsc import options as petsc_options
from .runtime import resolve_executable, run_qpx, validate_executable

ISSUE = first_linear_recipe.ISSUE
TARGET = first_linear_recipe.TARGET
DIAGNOSTIC_NL_MAX_ITS = first_linear_recipe.DIAGNOSTIC_NL_MAX_ITS
JACOBIAN_REL_TOL = first_linear_recipe.JACOBIAN_REL_TOL
FIRST_LINEAR_PETSC_OPTIONS = first_linear_recipe.FIRST_LINEAR_PETSC_OPTIONS
REQUIRED_EXISTING_OPTIONS = first_linear_recipe.REQUIRED_EXISTING_OPTIONS

Issue45FirstLinearRuntimeError = first_linear_recipe.Issue45FirstLinearError
PetscFirstLinearDiagnosticError = Issue45FirstLinearRuntimeError

# Policy aliases are intentional: this semantic owner orchestrates the recipe
# instead of re-implementing Issue45 construction/classification semantics.
instrument_first_linear = first_linear_recipe.instrument_first_linear
analyze_first_linear_text = first_linear_recipe.analyze_first_linear_text


def _normalized_diagnostic_text(text: str) -> str:
    out = mp.upsert_parameter(
        text,
        "Executioner",
        "nl_max_its",
        "<DIAGNOSTIC_NL_MAX_ITS>",
    )
    return mp.upsert_parameter(
        out,
        "Executioner",
        "petsc_options",
        "'<DIAGNOSTIC_PETSC_OPTIONS>'",
    )


def audit_first_linear_structure(
    base_text: str, diagnostic_text: str
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, observed: Any, required: Any) -> None:
        checks.append(
            {
                "id": name,
                "status": "PASS" if ok else "FAIL",
                "observed": observed,
                "required": required,
            }
        )

    closure = inv.audit_constrained_quasisteady_structure(
        diagnostic_text,
        expected_macro_avg=TARGET,
    )
    add(
        "canonical-c0-closure-structure",
        closure["status"] == "PASS",
        closure["status"],
        "PASS",
    )
    nl_max = mp.unquote(mp.get_parameter(diagnostic_text, "Executioner", "nl_max_its"))
    add("first-linear-nonlinear-horizon", nl_max == "1", nl_max, "1")

    options = petsc_options.get_flags(diagnostic_text)
    add(
        "existing-reason-options-preserved",
        all(option in options for option in REQUIRED_EXISTING_OPTIONS),
        options,
        list(REQUIRED_EXISTING_OPTIONS),
    )
    for option in FIRST_LINEAR_PETSC_OPTIONS:
        add(f"diagnostic-option:{option}", option in options, options, option)
    add(
        "no-full-jacobian-matrix-dump",
        "-snes_test_jacobian_view" not in options,
        options,
        "absent",
    )

    pairs = petsc_options.get_name_value_pairs(diagnostic_text)
    inames = [name for name, _ in pairs]
    values = [value for _, value in pairs]
    add(
        "lu-nonzero-shift-preserved",
        inames == ["-pc_type", "-pc_factor_shift_type"]
        and values == ["lu", "NONZERO"],
        {"iname": inames, "value": values},
        {
            "iname": ["-pc_type", "-pc_factor_shift_type"],
            "value": ["lu", "NONZERO"],
        },
    )

    same = _normalized_diagnostic_text(base_text) == _normalized_diagnostic_text(
        diagnostic_text
    )
    add("diagnostic-only-input-difference", same, same, True)
    blockers = [check for check in checks if check["status"] != "PASS"]
    return {
        "status": "PASS" if not blockers else "HOLD",
        "class": (
            "FIRST_LINEAR_STRUCTURE_PASS"
            if not blockers
            else "FIRST_LINEAR_STRUCTURE_FAIL"
        ),
        "checks": checks,
        "blockers": blockers,
        "closure": closure,
    }


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
        diagnostic, _ = instrument_first_linear(base)
        if audit_first_linear_structure(base, diagnostic)["status"] != "PASS":
            raise AssertionError("positive first-linear structure did not pass")

        mutated = diagnostic.replace("boundary = outlet", "boundary = plasma_cover", 1)
        if audit_first_linear_structure(base, mutated)["status"] == "PASS":
            raise AssertionError("non-diagnostic physics mutation was accepted")
        if (
            analyze_first_linear_text(_synthetic_log(), returncode=1)["class"]
            != "GMRES_RESTART_BREAKDOWN"
        ):
            raise AssertionError("GMRES restart breakdown did not classify")
        if (
            analyze_first_linear_text(_synthetic_log(1.0e-3), returncode=1)["class"]
            != "JACOBIAN_MISMATCH"
        ):
            raise AssertionError("Jacobian mismatch mutation was not detected")

        pc_fail = _synthetic_log().replace(
            "Linear solve did not converge due to DIVERGED_BREAKDOWN iterations 30",
            "Linear solve did not converge due to DIVERGED_PC_FAILED iterations 0\n"
            "PC failed due to FACTOR_NUMERIC_ZEROPIVOT",
            1,
        )
        if (
            analyze_first_linear_text(pc_fail, returncode=1)["class"]
            != "PC_OR_FACTORIZATION_FAIL"
        ):
            raise AssertionError("PC/factorization mutation was not detected")

        nonfinite = _synthetic_log().replace(
            "n_e:                  5.0e-16",
            "n_e:                  nan",
            1,
        )
        if (
            analyze_first_linear_text(nonfinite, returncode=1)["class"]
            != "NONFINITE_FAIL"
        ):
            raise AssertionError("non-finite mutation was not detected")

        missing_view = _synthetic_log().split("KSP Object:", 1)[0]
        if (
            analyze_first_linear_text(missing_view, returncode=1)["class"]
            != "DIAGNOSTIC_INSUFFICIENT"
        ):
            raise AssertionError("missing KSP identity was over-classified")
    except Exception as exc:
        print(f"ISSUE45_FIRST_LINEAR_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE45_FIRST_LINEAR_SELFTEST: PASS")
    return 0


def _prepare_case(exe: Path, results_root: str | None) -> dict[str, Any]:
    base_case, base_text, radial_span = inv._base_case_context()
    base_c0 = inv._build_constrained_quasisteady_input(
        base_text,
        radial_span=radial_span,
        macro_avg=TARGET,
        runtime_observability=True,
    )
    text, instrumentation = instrument_first_linear(base_c0)
    p1 = audit_first_linear_structure(base_c0, text)
    root = inv._evidence_root(
        exe=exe,
        results_root=results_root,
        stem="issue45_first_linear_diagnostic",
    )
    case_dir = root / "case"
    inv._stage_case(base_case, case_dir, text)
    return {
        "root": root,
        "case_dir": case_dir,
        "input_path": case_dir / "input.i",
        "p1": p1,
        "instrumentation": instrumentation,
    }


def _run_p2(exe: Path, prepared: dict[str, Any]) -> dict[str, Any]:
    log = prepared["root"] / "p2_check_input.log"
    run = run_qpx(
        exe,
        cwd=prepared["case_dir"],
        input_name="input.i",
        log_path=log,
        extra_args=("--check-input", "--color", "off"),
        stream=False,
    )
    return {
        "status": "PASS" if run.returncode == 0 else "HOLD",
        "returncode": run.returncode,
        "wall_seconds": run.wall_seconds,
        "log": str(log),
        "identity": {
            **evidence.identity_record(
                executable=exe,
                input_path=prepared["input_path"],
            ),
            "qpx_sha256": evidence.sha256_file(exe),
        },
    }


def _preflight(
    qpx: str | None,
    results_root: str | None,
) -> tuple[Path, dict[str, Any], dict[str, Any], str]:
    exe = resolve_executable(qpx)
    validate_executable(exe)
    prepared = _prepare_case(exe, results_root)
    p1_pass = prepared["p1"]["status"] == "PASS"
    p2 = _run_p2(exe, prepared) if p1_pass else {}
    status = "PASS" if p1_pass and p2.get("status") == "PASS" else "HOLD"
    return exe, prepared, p2, status


def _write_summary(
    prepared: dict[str, Any],
    p2: dict[str, Any],
    status: str,
    *,
    p3: dict[str, Any] | None = None,
) -> Path:
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
            "class": (
                "FIRST_LINEAR_DIAGNOSTIC_READY"
                if status == "PASS"
                else "HARNESS_OR_CONSTRUCTION_FAIL"
            ),
            "reason": (
                "C0 physics/closure is preserved and user-local QPX accepts the bounded Jacobian/KSP/true-residual diagnostic"
                if status == "PASS"
                else "the first-linear diagnostic did not pass all P0/P1/P2 gates"
            ),
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
    print(
        "ISSUE45_FIRST_LINEAR_CLASS: "
        + (
            "FIRST_LINEAR_DIAGNOSTIC_READY"
            if status == "PASS"
            else "HARNESS_OR_CONSTRUCTION_FAIL"
        )
    )
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
    run = run_qpx(
        exe,
        cwd=prepared["case_dir"],
        input_name="input.i",
        log_path=log,
        extra_args=("--color", "off"),
        stream=True,
    )
    print(f"ISSUE45_FIRST_LINEAR_CASE_END: rc={run.returncode}")
    decision = analyze_first_linear_text(
        log.read_text(errors="replace") if log.is_file() else "",
        returncode=run.returncode,
    )
    p3 = {
        "evr_count_for_this_batch": 1,
        "scope": "one bounded C0 initial-state first-linear discriminator",
        "runtime": {
            "returncode": run.returncode,
            "wall_seconds": run.wall_seconds,
            "log": str(log),
            "identity": {
                **evidence.identity_record(
                    executable=exe,
                    input_path=prepared["input_path"],
                ),
                "qpx_sha256": evidence.sha256_file(exe),
            },
        },
        "decision": decision,
    }
    path = _write_summary(prepared, p2, status, p3=p3)
    jacobian = decision.get("jacobian", {}).get("status", "HOLD")
    identity = decision.get("ksp_identity", {})
    true_rows = decision.get("true_residuals") or []
    print(f"ISSUE45_FIRST_LINEAR_JACOBIAN: {jacobian}")
    print(
        "ISSUE45_FIRST_LINEAR_KSP_IDENTITY: "
        + (
            "PASS"
            if identity.get("ksp_type") and identity.get("pc_type")
            else "HOLD"
        )
    )
    if identity:
        print(
            "ISSUE45_FIRST_LINEAR_KSP: "
            f"type={identity.get('ksp_type')} "
            f"restart={identity.get('restart')} "
            f"pc={identity.get('pc_type')}"
        )
    print("ISSUE45_FIRST_LINEAR_TRUE_RESIDUAL: " + ("PASS" if true_rows else "HOLD"))
    print(f"ISSUE45_FIRST_LINEAR_PRECLASS: {decision['status']}")
    print(f"ISSUE45_FIRST_LINEAR_CLASS: {decision['class']}")
    print(f"ISSUE45_FIRST_LINEAR_REASON: {decision['reason']}")
    print(f"ISSUE45_FIRST_LINEAR_LOG: {log}")
    print(f"ISSUE45_FIRST_LINEAR_SUMMARY: {path}")
    return 0 if decision["status"] == "PASS" else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run Issue45 bounded C0 PETSc first-linear diagnostic"
    )
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
        return (
            run_diagnostic(args.qpx, args.results_root)
            if args.run
            else run_preflight(args.qpx, args.results_root)
        )
    except (
        Issue45FirstLinearRuntimeError,
        inv.ElectronInventoryNullspaceError,
        MooseInputError,
    ) as exc:
        print("ISSUE45_FIRST_LINEAR_PREFLIGHT: HOLD")
        print("ISSUE45_FIRST_LINEAR_CLASS: HARNESS_OR_CONSTRUCTION_FAIL")
        print(f"ISSUE45_FIRST_LINEAR_REASON: {exc}")
        return 2


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv[1:]))
