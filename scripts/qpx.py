#!/usr/bin/env python3
"""Unified CLI for the reusable QPX test/diagnostic harness."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness.analysis import analyze
from qpx_harness.augmented_jacobian_localization import main as jac_localization_main, self_test as jac_localization_self_test
from qpx_harness.bundle import main as bundle_main
from qpx_harness.compat.issue46_fd_reference import main as fd_reference_main, self_test as fd_reference_self_test
from qpx_harness.coupling_evr1_runtime import main as coupling_evr1_main, self_test as coupling_evr1_self_test
from qpx_harness.coupling_evr2_runtime import main as coupling_evr2_main, self_test as coupling_evr2_self_test
from qpx_harness.dmix_equivalence import main as dmix_equivalence_main, self_test as dmix_equivalence_self_test
from qpx_harness.electron_inventory_nullspace import main as inventory_nullspace_main, self_test as inventory_nullspace_self_test
from qpx_harness.execution_contract import main as execution_contract_main, self_test as execution_contract_self_test
from qpx_harness.fast_plasma_coupling_diagnostic import main as fast_coupling_diagnostic_main, self_test as fast_coupling_diagnostic_self_test
from qpx_harness.issue43_fast_relaxation import main as fast_relaxation_main, self_test as fast_relaxation_self_test
from qpx_harness.performance_cache_audit import main as performance_cache_audit_main, self_test as performance_cache_audit_self_test
from qpx_harness.performance_core import main as performance_main, self_test as performance_self_test
from qpx_harness.performance_investigation import main as performance_investigation_main, self_test as performance_investigation_self_test
from qpx_harness.performance_smoke import main as performance_smoke_main, self_test as performance_smoke_self_test
from qpx_harness.performance_transport_probe_direct import main as performance_transport_probe_main, self_test as performance_transport_probe_self_test
from qpx_harness.petsc_first_linear_diagnostic import main as first_linear_main, self_test as first_linear_self_test
from qpx_harness.preflight import parser_symbol_self_test, validate_input_preflight
from qpx_harness.profiling import main as profile_main
from qpx_harness.regression import cli_run_all, cli_run_test
from qpx_harness.scale_audit import main as scale_audit_main, self_test as scale_audit_self_test
from qpx_harness.temporal import (
    VALID_INITIAL_POLICIES,
    normalize_temporal_csv,
    self_test as temporal_self_test,
)
from qpx_harness.workspace import inventory_cli, self_test as workspace_self_test


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
    print("usage: python3 scripts/qpx.py <command> [args]")
    print()
    print("commands:")
    width = max(len(name) for name in COMMANDS)
    for name, description in COMMANDS.items():
        print(f"  {name:<{width}}  {description}")
    print()
    print("Use '<command> --help' for command-specific arguments.")


def analyze_cli(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="qpx analyze")
    parser.add_argument("--summary", required=True)
    parser.add_argument("--petsc-log", required=True)
    parser.add_argument("--perf-log")
    parser.add_argument("--json-out")
    parser.add_argument("--metric-prefix")
    args = parser.parse_args(argv)

    result = analyze(
        Path(args.summary),
        Path(args.petsc_log) if False else Path(args.petsc_log),
        Path(args.perf_log) if args.perf_log else None,
        metric_prefix=args.metric_prefix,
    )
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    print(text, end="")
    if args.json_out:
        Path(args.json_out).write_text(text)
    return 0 if result.get("interpretable_performance") else 2


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
    parser.add_argument(
        "--initial-row-policy",
        choices=sorted(VALID_INITIAL_POLICIES),
    )
    parser.add_argument("--initial-time", type=float, default=0.0)
    parser.add_argument("--time-tol", type=float, default=1.0e-15)
    parser.add_argument("--allow-no-physical-rows", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return temporal_self_test()
    if not args.source or not args.output or not args.initial_row_policy:
        parser.error(
            "source, --output, and --initial-row-policy are required unless --self-test"
        )

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
        "source_rows",
        "initialization_rows",
        "physical_rows",
        "initial_row_policy",
        "output",
    ):
        print(f"{key.upper()}={summary[key]}")
    return 0


def self_test_cli(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="qpx self-test")
    parser.parse_args(argv)
    parser_rc = parser_symbol_self_test()
    temporal_rc = temporal_self_test()
    workspace_rc = workspace_self_test()
    coupling_evr1_rc = coupling_evr1_self_test()
    coupling_evr2_rc = coupling_evr2_self_test()
    scale_audit_rc = scale_audit_self_test()
    fast_relaxation_rc = fast_relaxation_self_test()
    fast_coupling_diagnostic_rc = fast_coupling_diagnostic_self_test()
    inventory_nullspace_rc = inventory_nullspace_self_test()
    first_linear_rc = first_linear_self_test()
    jac_localization_rc = jac_localization_self_test()
    fd_reference_rc = fd_reference_self_test()
    execution_contract_rc = execution_contract_self_test()
    dmix_equivalence_rc = dmix_equivalence_self_test()
    performance_rc = performance_self_test()
    performance_smoke_rc = performance_smoke_self_test()
    performance_investigation_rc = performance_investigation_self_test()
    performance_transport_probe_rc = performance_transport_probe_self_test()
    performance_cache_audit_rc = performance_cache_audit_self_test()
    ok = (
        parser_rc == 0
        and temporal_rc == 0
        and workspace_rc == 0
        and coupling_evr1_rc == 0
        and coupling_evr2_rc == 0
        and scale_audit_rc == 0
        and fast_relaxation_rc == 0
        and fast_coupling_diagnostic_rc == 0
        and inventory_nullspace_rc == 0
        and first_linear_rc == 0
        and jac_localization_rc == 0
        and fd_reference_rc == 0
        and execution_contract_rc == 0
        and dmix_equivalence_rc == 0
        and performance_rc == 0
        and performance_smoke_rc == 0
        and performance_investigation_rc == 0
        and performance_transport_probe_rc == 0
        and performance_cache_audit_rc == 0
    )
    print("QPX_HARNESS_SELFTEST:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in {"-h", "--help", "help"}:
        print_help()
        return 0

    command, rest = args[0], args[1:]
    if command == "test":
        return cli_run_test(rest)
    if command == "test-all":
        return cli_run_all(rest)
    if command == "coupling-evr1":
        return coupling_evr1_main(rest)
    if command == "coupling-evr2":
        return coupling_evr2_main(rest)
    if command == "scale-audit":
        return scale_audit_main(rest)
    if command == "fast-relaxation":
        return fast_relaxation_main(rest)
    if command == "fast-coupling-diagnostic":
        return fast_coupling_diagnostic_main(rest)
    if command == "inventory-nullspace":
        return inventory_nullspace_main(rest)
    if command == "inventory-first-linear":
        return first_linear_main(rest)
    if command == "inventory-jacobian-localization":
        return jac_localization_main(rest)
    if command == "inventory-fd-reference":
        return fd_reference_main(rest)
    if command == "contract":
        return execution_contract_main(rest)
    if command == "dmix-equivalence":
        return dmix_equivalence_main(rest)
    if command == "measure":
        return performance_main(rest)
    if command == "measure-smoke":
        return performance_smoke_main(rest)
    if command == "investigate":
        return performance_investigation_main(rest)
    if command == "transport-probe":
        return performance_transport_probe_main(rest)
    if command == "cache-audit":
        return performance_cache_audit_main(rest)
    if command == "profile":
        return profile_main(rest)
    if command == "analyze":
        return analyze_cli(rest)
    if command == "bundle":
        return bundle_main(rest)
    if command == "inventory":
        return inventory_cli(rest)
    if command == "preflight":
        return preflight_cli(rest)
    if command == "temporal-csv":
        return temporal_csv_cli(rest)
    if command == "self-test":
        return self_test_cli(rest)

    print(f"unknown command: {command}", file=sys.stderr)
    print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
