"""Unified command routing for the reusable QPX test/diagnostic harness."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from qpx_harness.analysis.stats_builder import self_test as stats_builder_self_test
from qpx_harness.analysis.performance.investigation import self_test as performance_investigation_self_test
from qpx_harness.analysis.performance.profile import self_test as performance_profile_self_test
from qpx_harness.bundle import main as bundle_main
from qpx_harness.cli.commands.performance import (
    analyze_main,
    cache_audit_main,
    cache_audit_self_test,
    investigate_main,
    measure_main,
    measure_smoke_main,
    transport_probe_main,
)
from qpx_harness.coupling_evr1_runtime import main as coupling_evr1_main, self_test as coupling_evr1_self_test
from qpx_harness.coupling_evr2_runtime import main as coupling_evr2_main, self_test as coupling_evr2_self_test
from qpx_harness.dmix_equivalence import main as dmix_equivalence_main, self_test as dmix_equivalence_self_test
from qpx_harness.electron_inventory_nullspace import main as inventory_nullspace_main, self_test as inventory_nullspace_self_test
from qpx_harness.execution.workspace import inventory_cli, self_test as workspace_self_test
from qpx_harness.execution_contract import main as execution_contract_main, self_test as execution_contract_self_test
from qpx_harness.issue43_coupling_diagnostic import main as fast_coupling_diagnostic_main, self_test as fast_coupling_diagnostic_self_test
from qpx_harness.issue43_fast_relaxation import main as fast_relaxation_main, self_test as fast_relaxation_self_test
from qpx_harness.issue45_first_linear import main as first_linear_main, self_test as first_linear_self_test
from qpx_harness.issue46_fd_reference import main as fd_reference_main, self_test as fd_reference_self_test
from qpx_harness.issue46_jacobian_localization import main as jac_localization_main, self_test as jac_localization_self_test
from qpx_harness.performance.runner import self_test as performance_self_test
from qpx_harness.performance.smoke import self_test as performance_smoke_self_test
from qpx_harness.performance.probes.transport import self_test as performance_transport_probe_self_test
from qpx_harness.preflight import parser_symbol_self_test, validate_input_preflight
from qpx_harness.profiling import main as profile_main
from qpx_harness.regression import cli_run_all, cli_run_test
from qpx_harness.scale_audit import main as scale_audit_main, self_test as scale_audit_self_test
from qpx_harness.temporal import (
    VALID_INITIAL_POLICIES,
    normalize_temporal_csv,
    self_test as temporal_self_test,
)

COMMANDS = {
    "test": "run one test.json case",
    "test-all": "discover and run a canonical/diagnostic suite",
    "coupling-evr1": "run Issue31 optimized monolithic coupling discriminator",
    "coupling-evr2": "run Issue31 transport timestep/scaling discriminator",
    "scale-audit": "build Issue43 QVT multiphysics space-time scale map",
    "fast-relaxation": "run Issue43 electron-Poisson discriminator with Issue44 output contract",
    "fast-coupling-diagnostic": "localize the Issue43 1e-13 electron-Poisson coupling failure",
    "inventory-nullspace": "run Issue45 electron-inventory nullspace structural/framework preflight",
    "inventory-first-linear": "diagnose the Issue45 constrained C0 first-linear breakdown",
    "inventory-jacobian-localization": "prepare the Issue46 augmented Jacobian block-localization audit",
    "inventory-fd-reference": "audit Issue46 PETSc finite-difference Jacobian reference quantization",
    "contract": "validate/evaluate a CORE-16 scientific execution contract",
    "dmix-equivalence": "compare optimized D_mix against legacy full evaluation",
    "measure": "run one schema-driven QPX performance measurement",
    "measure-smoke": "auto-manage one PF-1 BENCHMARK/PROFILE smoke pair",
    "investigate": "analyze the latest passing PF-1 smoke evidence",
    "transport-probe": "run managed QPXThermalDiffusionMaterial timing probe",
    "cache-audit": "audit D_mix consumer arguments and native cache feasibility",
    "profile": "capture one-step legacy P2/P3 performance evidence",
    "analyze": "classify PETSc/PerfGraph profiling evidence",
    "bundle": "build a declarative local profiling bundle",
    "inventory": "inspect or compare QPX workspace trees",
    "preflight": "run static parser-symbol preflight on one MOOSE input",
    "temporal-csv": "normalize transient CSV rows under an explicit temporal policy",
    "self-test": "run all harness static/self-tests",
}


def print_help() -> None:
    print("usage: python3 bin/qpx.py <command> [args]")
    print()
    print("commands:")
    width = max(len(name) for name in COMMANDS)
    for name, description in COMMANDS.items():
        print(f"  {name:<{width}}  {description}")
    print()
    print("Use '<command> --help' for command-specific arguments.")


def preflight_cli(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="qpx preflight")
    parser.add_argument("input", nargs="?", help="MOOSE input file to inspect")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return parser_symbol_self_test()
    if not args.input:
        parser.error("input is required unless --self-test")
    validate_input_preflight(Path(args.input).expanduser().resolve())
    return 0


def temporal_csv_cli(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="qpx temporal-csv")
    parser.add_argument("source", nargs="?")
    parser.add_argument("--output")
    parser.add_argument("--time-column", default="time")
    parser.add_argument("--initial-row-policy", choices=sorted(VALID_INITIAL_POLICIES))
    parser.add_argument("--initial-time", type=float, default=0.0)
    parser.add_argument("--time-tol", type=float, default=1.0e-15)
    parser.add_argument("--allow-no-physical-rows", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return temporal_self_test()
    if not args.source or not args.output or not args.initial_row_policy:
        parser.error("source, --output, and --initial-row-policy are required unless --self-test")
    summary = normalize_temporal_csv(
        Path(args.source),
        Path(args.output),
        time_column=args.time_column,
        initial_row_policy=args.initial_row_policy,
        initial_time=args.initial_time,
        time_tol=args.time_tol,
        require_physical_rows=not args.allow_no_physical_rows,
    )
    print("TEMPORAL_CSV_NORMALIZE: PASS")
    for key in (
        "source_rows", "initialization_rows", "physical_rows",
        "initial_row_policy", "output",
    ):
        print(f"{key.upper()}={summary[key]}")
    return 0


def self_test_cli(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="qpx self-test")
    parser.parse_args(argv)
    results = (
        stats_builder_self_test(),
        parser_symbol_self_test(),
        temporal_self_test(),
        workspace_self_test(),
        coupling_evr1_self_test(),
        coupling_evr2_self_test(),
        scale_audit_self_test(),
        fast_relaxation_self_test(),
        fast_coupling_diagnostic_self_test(),
        inventory_nullspace_self_test(),
        first_linear_self_test(),
        jac_localization_self_test(),
        fd_reference_self_test(),
        execution_contract_self_test(),
        dmix_equivalence_self_test(),
        performance_self_test(),
        performance_smoke_self_test(),
        performance_investigation_self_test(),
        performance_profile_self_test(),
        performance_transport_probe_self_test(),
        cache_audit_self_test(),
    )
    ok = all(result == 0 for result in results)
    print("QPX_HARNESS_SELFTEST:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in {"-h", "--help", "help"}:
        print_help()
        return 0
    command, rest = args[0], args[1:]
    handlers = {
        "test": cli_run_test,
        "test-all": cli_run_all,
        "coupling-evr1": coupling_evr1_main,
        "coupling-evr2": coupling_evr2_main,
        "scale-audit": scale_audit_main,
        "fast-relaxation": fast_relaxation_main,
        "fast-coupling-diagnostic": fast_coupling_diagnostic_main,
        "inventory-nullspace": inventory_nullspace_main,
        "inventory-first-linear": first_linear_main,
        "inventory-jacobian-localization": jac_localization_main,
        "inventory-fd-reference": fd_reference_main,
        "contract": execution_contract_main,
        "dmix-equivalence": dmix_equivalence_main,
        "measure": measure_main,
        "measure-smoke": measure_smoke_main,
        "investigate": investigate_main,
        "transport-probe": transport_probe_main,
        "cache-audit": cache_audit_main,
        "profile": profile_main,
        "analyze": analyze_main,
        "bundle": bundle_main,
        "inventory": inventory_cli,
        "preflight": preflight_cli,
        "temporal-csv": temporal_csv_cli,
        "self-test": self_test_cli,
    }
    handler = handlers.get(command)
    if handler is None:
        print(f"unknown command: {command}", file=sys.stderr)
        print_help()
        return 2
    return handler(rest)
