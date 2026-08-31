"""Semantic runtime owner for the Issue43 coupling diagnostic.

Scientific input-construction policy is owned by
``recipes.issue43_coupling_diagnostic``. Issue-agnostic MOOSE/PETSc parsing is
owned by reusable primitives. The historical
``fast_plasma_coupling_diagnostic`` module remains a bounded runtime-shell
migration dependency while Issue48 converges orchestration into this owner.
"""
from __future__ import annotations

from recipes import issue43_coupling_diagnostic as recipe

from . import fast_plasma_coupling_diagnostic as runtime_shell
from .moose import blocks as mb
from .moose import log as moose_log
from .moose import parameters as mp
from .moose_input import MooseInputError
from .petsc import jacobian as petsc_jacobian
from .petsc import log as petsc_log
from .petsc import options as po


FastPlasmaCouplingDiagnosticError = runtime_shell.FastPlasmaCouplingDiagnosticError
BASE_CASE_RELATIVE = runtime_shell.BASE_CASE_RELATIVE
DT_CONTROL = runtime_shell.DT_CONTROL
DT_FAIL = runtime_shell.DT_FAIL
STEPS = runtime_shell.STEPS
JACOBIAN_REL_TOL = runtime_shell.JACOBIAN_REL_TOL
DIAGNOSTIC_PETSC_OPTIONS = recipe.DIAGNOSTIC_PETSC_OPTIONS
JACOBIAN_PETSC_OPTIONS = recipe.JACOBIAN_PETSC_OPTIONS


def instrument_input(
    input_text: str, *, jacobian_test: bool = False
):
    """Apply the canonical recipe while preserving the historical error surface."""
    try:
        return recipe.instrument_input(input_text, jacobian_test=jacobian_test)
    except (
        mb.MooseBlockError,
        mp.MooseParameterError,
        po.PetscOptionsError,
        MooseInputError,
    ) as exc:
        raise FastPlasmaCouplingDiagnosticError(str(exc)) from exc


# Compatibility aliases expose the accepted parser surface while binding the
# implementation to issue-agnostic primitives rather than the legacy shell.
_parse_variable_residuals = moose_log.parse_variable_residual_norms
_parse_scaling_factors = moose_log.parse_automatic_scaling_factors
_parse_pc_failure_reason = petsc_log.parse_pc_failure_reason
_parse_jacobian_tests = petsc_jacobian.parse_comparisons


# Install canonical recipe/primitive operations into the bounded historical
# orchestration shell. This keeps accepted runtime behavior stable during the
# owner cutover while making ownership explicit and testable.
runtime_shell.DIAGNOSTIC_PETSC_OPTIONS = DIAGNOSTIC_PETSC_OPTIONS
runtime_shell.JACOBIAN_PETSC_OPTIONS = JACOBIAN_PETSC_OPTIONS
runtime_shell.instrument_input = instrument_input
runtime_shell._parse_variable_residuals = _parse_variable_residuals
runtime_shell._parse_scaling_factors = _parse_scaling_factors
runtime_shell._parse_pc_failure_reason = _parse_pc_failure_reason
runtime_shell._parse_jacobian_tests = _parse_jacobian_tests


analyze_log_text = runtime_shell.analyze_log_text
analyze_log = runtime_shell.analyze_log
analyze_jacobian_text = runtime_shell.analyze_jacobian_text
analyze_jacobian_log = runtime_shell.analyze_jacobian_log
run_preflight = runtime_shell.run_preflight
run_runtime = runtime_shell.run_runtime
run_jacobian_runtime = runtime_shell.run_jacobian_runtime
main = runtime_shell.main
self_test = runtime_shell.self_test


def recipe_backing_status() -> dict[str, bool]:
    return {
        "instrument-input": runtime_shell.instrument_input is instrument_input,
        "diagnostic-options": runtime_shell.DIAGNOSTIC_PETSC_OPTIONS
        is DIAGNOSTIC_PETSC_OPTIONS,
        "jacobian-options": runtime_shell.JACOBIAN_PETSC_OPTIONS
        is JACOBIAN_PETSC_OPTIONS,
        "variable-residual-parser": runtime_shell._parse_variable_residuals
        is moose_log.parse_variable_residual_norms,
        "scaling-parser": runtime_shell._parse_scaling_factors
        is moose_log.parse_automatic_scaling_factors,
        "pc-failure-parser": runtime_shell._parse_pc_failure_reason
        is petsc_log.parse_pc_failure_reason,
        "jacobian-parser": runtime_shell._parse_jacobian_tests
        is petsc_jacobian.parse_comparisons,
    }


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv[1:]))
