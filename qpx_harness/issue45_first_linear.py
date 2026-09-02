"""Compatibility facade for the Issue45 bounded first-linear diagnostic."""
from __future__ import annotations

import argparse

from recipes import issue45_first_linear as first_linear_recipe

from . import electron_inventory_nullspace as inv
from .issue45.first_linear_characterization import _synthetic_log, self_test
from .issue45.first_linear_orchestration import (
    _prepare_case,
    _preflight,
    _run_p2,
    _write_summary,
    run_diagnostic,
    run_preflight,
)
from .issue45.first_linear_stats import build_first_linear_stats
from .issue45.first_linear_structure import (
    _normalized_diagnostic_text,
    audit_first_linear_structure,
)
from .moose.input import MooseInputError

ISSUE = first_linear_recipe.ISSUE
TARGET = first_linear_recipe.TARGET
DIAGNOSTIC_NL_MAX_ITS = first_linear_recipe.DIAGNOSTIC_NL_MAX_ITS
JACOBIAN_REL_TOL = first_linear_recipe.JACOBIAN_REL_TOL
FIRST_LINEAR_PETSC_OPTIONS = first_linear_recipe.FIRST_LINEAR_PETSC_OPTIONS
REQUIRED_EXISTING_OPTIONS = first_linear_recipe.REQUIRED_EXISTING_OPTIONS

Issue45FirstLinearRuntimeError = first_linear_recipe.Issue45FirstLinearError
PetscFirstLinearDiagnosticError = Issue45FirstLinearRuntimeError

instrument_first_linear = first_linear_recipe.instrument_first_linear
analyze_first_linear_text = first_linear_recipe.analyze_first_linear_text


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
