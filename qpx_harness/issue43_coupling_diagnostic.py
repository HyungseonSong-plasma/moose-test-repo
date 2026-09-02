"""Compatibility facade for the Issue43 electron-Poisson coupling diagnostic."""
from __future__ import annotations

import argparse

from recipes import issue43_coupling_diagnostic as recipe

from .issue43_coupling.analysis import (
    _line_hits,
    _parse_jacobian_tests,
    _parse_pc_failure_reason,
    _parse_scaling_factors,
    _parse_variable_residuals,
    analyze_jacobian_log,
    analyze_jacobian_text,
    analyze_log,
    analyze_log_text,
    recipe_backing_status,
)
from .issue43_coupling.constants import (
    BASE_CASE_RELATIVE,
    DIAGNOSTIC_PETSC_OPTIONS,
    DT_CONTROL,
    DT_FAIL,
    JACOBIAN_PETSC_OPTIONS,
    JACOBIAN_REL_TOL,
    RUNTIME_PURGE_DIRECTORY_NAMES,
    RUNTIME_PURGE_PATTERNS,
    STEPS,
    FastPlasmaCouplingDiagnosticError,
)
from .issue43_coupling.orchestration import (
    _emit_preflight_markers,
    _preflight_result,
    _prepare_cases,
    _run_cases,
    _run_p2,
    _write_summary,
    run_jacobian_runtime,
    run_preflight,
    run_runtime,
)
from .issue43_coupling.structure import (
    _build_case,
    _contains_petsc_options,
    _p1_case,
    _parameter_value,
    _stage_case,
    instrument_input,
)
from .moose import blocks as mb
from .moose import parameters as mp
from .moose.input import MooseInputError
from .petsc import options as po

_RUNTIME_PURGE_DIRECTORY_NAMES = RUNTIME_PURGE_DIRECTORY_NAMES
_RUNTIME_PURGE_PATTERNS = RUNTIME_PURGE_PATTERNS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the bounded Issue43 electron-Poisson coupling failure diagnostic"
    )
    parser.add_argument("--qpx", help="path to user-local qpx-opt")
    parser.add_argument("--results-root")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--jacobian-preflight", action="store_true")
    mode.add_argument("--jacobian-run", action="store_true")
    args = parser.parse_args(argv)

    try:
        if args.jacobian_run:
            return run_jacobian_runtime(qpx=args.qpx, results_root=args.results_root)
        if args.jacobian_preflight:
            return run_preflight(
                qpx=args.qpx,
                results_root=args.results_root,
                jacobian_test=True,
            )
        if args.run:
            return run_runtime(qpx=args.qpx, results_root=args.results_root)
        return run_preflight(qpx=args.qpx, results_root=args.results_root)
    except (
        FastPlasmaCouplingDiagnosticError,
        mb.MooseBlockError,
        mp.MooseParameterError,
        po.PetscOptionsError,
        MooseInputError,
    ) as exc:
        prefix = (
            "ISSUE43_JACOBIAN_DIAGNOSTIC"
            if args.jacobian_preflight or args.jacobian_run
            else "ISSUE43_COUPLING_DIAGNOSTIC"
        )
        print(f"{prefix}_PRECLASS: HOLD")
        print(f"{prefix}_CLASS: HARNESS_OR_CONSTRUCTION_FAIL")
        print(f"{prefix}_REASON: {exc}")
        return 2


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv[1:]))
