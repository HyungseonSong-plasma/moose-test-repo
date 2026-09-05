"""CLI adapters for the canonical electron-inventory capability."""
from __future__ import annotations

import argparse

from qpx_harness.adapters.moose.electron_inventory import first_linear as first_linear_recipe

from qpx_harness.moose.input import MooseInputError
from qpx_harness.domains.plasma.electron_inventory import DEFAULT_MACRO_ELECTRON_AVG
from qpx_harness.domains.plasma.electron_inventory import ElectronInventoryNullspaceError
from qpx_harness.execution.electron_inventory.first_linear_orchestration import run_diagnostic, run_preflight as run_first_linear_preflight
from qpx_harness.execution.electron_inventory.orchestration import (
    run_closure_preflight,
    run_closure_runtime,
    run_closure_runtime_preflight,
    run_preflight,
)


def inventory_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run electron-inventory nullspace/closure validation"
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
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--closure-preflight", action="store_true")
    mode.add_argument("--closure-runtime-preflight", action="store_true")
    mode.add_argument("--closure-run", action="store_true")
    args = parser.parse_args(argv)

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


def first_linear_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run bounded inventory C0 PETSc first-linear diagnostic"
    )
    parser.add_argument("--qpx", help="path to user-local qpx-opt")
    parser.add_argument("--results-root")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--run", action="store_true")
    args = parser.parse_args(argv)
    try:
        return (
            run_diagnostic(args.qpx, args.results_root)
            if args.run
            else run_first_linear_preflight(args.qpx, args.results_root)
        )
    except (
        first_linear_recipe.Issue45FirstLinearError,
        ElectronInventoryNullspaceError,
        MooseInputError,
    ) as exc:
        print("ISSUE45_FIRST_LINEAR_PREFLIGHT: HOLD")
        print("ISSUE45_FIRST_LINEAR_CLASS: HARNESS_OR_CONSTRUCTION_FAIL")
        print(f"ISSUE45_FIRST_LINEAR_REASON: {exc}")
        return 2
