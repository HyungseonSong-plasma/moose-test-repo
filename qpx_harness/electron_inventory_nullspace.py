"""Issue #45 electron-inventory nullspace / closure compatibility facade.

Focused Issue45 semantic owners live under ``qpx_harness.issue45``. This module
preserves the historical CLI and import surface while delegating structure,
schema, model construction, runtime evaluation, orchestration, and
characterization to their focused owners.
"""
from __future__ import annotations

import argparse

from .moose_input import MooseInputError
from .issue45.characterization import self_test
from .issue45.closure_model import (
    _build_constrained_quasisteady_input,
    _normalized_target_text,
    _remove_block,
    _replace_block,
    _synthetic_closed_input,
    _synthetic_constrained_input,
    _target_only_pair_audit,
)
from .issue45.closure_runtime import (
    _evaluate_runtime_case_data,
    _evaluate_runtime_pair,
    _find_runtime_csv,
    _read_final_runtime_row,
    _synthetic_runtime_row,
)
from .issue45.closure_schema import (
    _extract_moose_json,
    _schema_presence_analysis,
    analyze_constraint_schema_text,
    analyze_drift_schema_text,
)
from .issue45.constants import (
    BASE_CASE_RELATIVE,
    C0_TARGET,
    C1_TARGET,
    CLOSURE_DELTA_REL_TOL,
    CLOSURE_TARGET_REL_TOL,
    CONSTRAINT_TYPE,
    DEFAULT_MACRO_ELECTRON_AVG,
    DRIFT_TYPE,
    DT_REFERENCE,
    EXPECTED_CONSTRAINED_ELECTRON_KERNEL_TYPES,
    EXPECTED_DRIFT_BOUNDARIES,
    EXPECTED_POISSON_GROUNDS,
    EXPECTED_TRANSIENT_ELECTRON_KERNEL_TYPES,
    INVENTORY_CONSISTENCY_REL_TOL,
    ISSUE,
    LAMBDA_VARIABLE,
    MACRO_AVG_POSTPROCESSOR,
    REQUIRED_CONSTRAINT_SCHEMA_PARAMETERS,
    REQUIRED_FVFLUX_SCHEMA_PARAMETERS,
    RUNTIME_COLUMNS,
    RUNTIME_PURGE_DIRECTORY_NAMES,
    RUNTIME_PURGE_PATTERNS,
    STEPS,
)
from .issue45.errors import ElectronInventoryNullspaceError
from .issue45.inventory_structure import (
    _audit_poisson_grounding,
    _direct_children,
    _electron_fvbcs,
    _electron_kernel_records,
    _ensure_debug_block,
    _float_parameter,
    _flux_boundary_audit,
    _parameter_count,
    _parameter_value,
    _poisson_fvbcs,
    _set_or_insert_parameter,
    _truthy,
    _unquote,
    _words,
    audit_closed_electron_structure,
    audit_constrained_quasisteady_structure,
)
from .issue45.orchestration import (
    _base_case_context,
    _closure_runtime_preflight_result,
    _emit_closure_runtime_preflight_markers,
    _evidence_root,
    _prepare_case,
    _prepare_closure_case,
    _prepare_closure_runtime_cases,
    _run_p2_check_input,
    _run_schema_query,
    _runtime_case,
    _stage_case,
    _write_json,
    run_closure_preflight,
    run_closure_runtime,
    run_closure_runtime_preflight,
    run_preflight,
)

# Historical private constants retained as aliases for compatibility.
_RUNTIME_PURGE_DIRECTORY_NAMES = RUNTIME_PURGE_DIRECTORY_NAMES
_RUNTIME_PURGE_PATTERNS = RUNTIME_PURGE_PATTERNS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run Issue45 electron-inventory nullspace/closure validation"
    )
    parser.add_argument("--qpx", help="path to user-local qpx-opt")
    parser.add_argument("--results-root")
    parser.add_argument(
        "--macro-electron-average",
        type=float,
        default=DEFAULT_MACRO_ELECTRON_AVG,
        help="macrostate electron average used by --closure-preflight",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-test", action="store_true")
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--closure-preflight", action="store_true")
    mode.add_argument("--closure-runtime-preflight", action="store_true")
    mode.add_argument("--closure-run", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()
    if self_test() != 0:
        return 1
    try:
        if args.closure_run:
            return run_closure_runtime(qpx=args.qpx, results_root=args.results_root)
        if args.closure_runtime_preflight:
            return run_closure_runtime_preflight(
                qpx=args.qpx, results_root=args.results_root
            )
        if args.closure_preflight:
            return run_closure_preflight(
                qpx=args.qpx,
                results_root=args.results_root,
                macro_avg=args.macro_electron_average,
            )
        return run_preflight(qpx=args.qpx, results_root=args.results_root)
    except (ElectronInventoryNullspaceError, MooseInputError) as exc:
        if args.closure_run or args.closure_runtime_preflight:
            prefix = "ISSUE45_INVENTORY_CLOSURE_RUNTIME"
        elif args.closure_preflight:
            prefix = "ISSUE45_INVENTORY_CLOSURE"
        else:
            prefix = "ISSUE45_INVENTORY_NULLSPACE"
        print(f"{prefix}_PREFLIGHT: HOLD")
        print(f"{prefix}_CLASS: HARNESS_OR_CONSTRUCTION_FAIL")
        print(f"{prefix}_REASON: {exc}")
        return 2


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv[1:]))
