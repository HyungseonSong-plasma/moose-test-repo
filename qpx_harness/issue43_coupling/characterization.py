"""Characterization owner for Issue43 coupling diagnostic surfaces."""
from __future__ import annotations

import tempfile
from pathlib import Path

from .. import cases as case_ops
from ..petsc import options as po
from .analysis import analyze_jacobian_text, analyze_log_text
from .constants import DIAGNOSTIC_PETSC_OPTIONS, JACOBIAN_PETSC_OPTIONS
from .structure import (
    _contains_petsc_options,
    _parameter_value,
    _stage_case,
    instrument_input,
)


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
        if "-snes_test_jacobian_view" in po.get_flags(jacobian_tuned):
            raise AssertionError("Jacobian mode unexpectedly enabled full matrix dump")

        already = base.replace(
            "  petsc_options_iname = '-pc_type'\n",
            "  petsc_options = '-snes_view'\n  petsc_options_iname = '-pc_type'\n",
        )
        merged, _ = instrument_input(already, jacobian_test=True)
        if "-snes_view" not in po.get_flags(merged):
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
