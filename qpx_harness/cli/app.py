"""Unified thin command routing for the reusable QPX harness."""
from __future__ import annotations

import argparse
from importlib import import_module
from pathlib import Path
import subprocess
import sys

from qpx_harness.application import normalize_temporal_run_csv, preflight_input, run_experiment
from qpx_harness.analysis.temporal import VALID_INITIAL_POLICIES

ROOT = Path(__file__).resolve().parents[2]

COMMANDS = {
    "test": "run one test.json case",
    "test-all": "discover and run a canonical/diagnostic suite",
    "scale-audit": "build QVT multiphysics space-time scale map",
    "inventory-nullspace": "run electron-inventory nullspace structural/framework preflight",
    "inventory-first-linear": "diagnose the constrained C0 first-linear breakdown",
    "contract": "validate/evaluate a CORE-16 scientific execution contract",
    "dmix-equivalence": "compare optimized D_mix against legacy full evaluation",
    "measure": "run one schema-driven QPX performance measurement",
    "measure-smoke": "auto-manage one PF-1 BENCHMARK/PROFILE smoke pair",
    "investigate": "analyze the latest passing PF-1 smoke evidence",
    "transport-probe": "run managed QPXThermalDiffusionMaterial timing probe",
    "cache-audit": "audit D_mix consumer arguments and native cache feasibility",
    "profile": "capture one-step legacy P2/P3 performance evidence",
    "analyze": "classify PETSc/PerfGraph profiling evidence",
    "inventory": "inspect or compare QPX workspace trees",
    "preflight": "run static parser-symbol preflight on one MOOSE input",
    "temporal-csv": "normalize transient CSV rows under an explicit temporal policy",
}

INTERNAL_TARGETS = {
    "architecture": "run dependency, experiment-gateway, and architecture guards",
    "regression": "run the qpx-free Python regression/unit suite",
    "all": "run architecture guards then regression/unit suite",
}

_LEGACY_TARGETS = {
    "test": "qpx_harness.execution.regression:cli_run_test",
    "test-all": "qpx_harness.execution.regression:cli_run_all",
    "scale-audit": "qpx_harness.analysis.scale_audit:main",
    "inventory-nullspace": "qpx_harness.inventory.cli:inventory_main",
    "inventory-first-linear": "qpx_harness.inventory.cli:first_linear_main",
    "contract": "qpx_harness.execution.contract:main",
    "dmix-equivalence": "qpx_harness.cli.commands.dmix:dmix_equivalence_main",
    "measure": "qpx_harness.cli.commands.performance:measure_main",
    "measure-smoke": "qpx_harness.cli.commands.performance:measure_smoke_main",
    "investigate": "qpx_harness.cli.commands.performance:investigate_main",
    "transport-probe": "qpx_harness.cli.commands.performance:transport_probe_main",
    "cache-audit": "qpx_harness.cli.commands.performance:cache_audit_main",
    "profile": "qpx_harness.performance.profiling:main",
    "analyze": "qpx_harness.cli.commands.performance:analyze_main",
    "inventory": "qpx_harness.execution.workspace:inventory_cli",
}


def _resolve_legacy_handler(command: str):
    target = _LEGACY_TARGETS.get(command)
    if target is None:
        return None
    module_name, function_name = target.split(":", 1)
    module = import_module(module_name)
    handler = getattr(module, function_name)
    if not callable(handler):
        raise TypeError(f"legacy command target is not callable: {target}")
    return handler


def print_help() -> None:
    print("usage:")
    print("  python3 bin/qpx.py -e <experiment.json>")
    print("  python3 bin/qpx.py -i <internal-target>")
    print("  python3 bin/qpx.py <legacy-command> [args]")
    print("  python qpx -i <internal-target>")
    print("\ncanonical gateways:")
    print("  -e, --experiment   execute one declarative scientific experiment")
    print("  -i, --internal     run internal architecture/validation tooling")
    print("\ninternal targets:")
    for name, description in INTERNAL_TARGETS.items():
        print(f"  {name:<12} {description}")
    print("\nlegacy commands (migration compatibility):")
    width = max(len(name) for name in COMMANDS)
    for name, description in COMMANDS.items():
        print(f"  {name:<{width}}  {description}")


def preflight_cli(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="qpx preflight")
    parser.add_argument("input", help="MOOSE input file to inspect")
    args = parser.parse_args(argv)
    preflight_input(args.input)
    return 0


def temporal_csv_cli(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="qpx temporal-csv")
    parser.add_argument("source")
    parser.add_argument("--output", required=True)
    parser.add_argument("--time-column", default="time")
    parser.add_argument("--initial-row-policy", choices=sorted(VALID_INITIAL_POLICIES), required=True)
    parser.add_argument("--initial-time", type=float, default=0.0)
    parser.add_argument("--time-tol", type=float, default=1.0e-15)
    parser.add_argument("--allow-no-physical-rows", action="store_true")
    args = parser.parse_args(argv)
    summary = normalize_temporal_run_csv(
        args.source,
        args.output,
        time_column=args.time_column,
        initial_row_policy=args.initial_row_policy,
        initial_time=args.initial_time,
        time_tol=args.time_tol,
        require_physical_rows=not args.allow_no_physical_rows,
    )
    print("TEMPORAL_CSV_NORMALIZE: PASS")
    for key in ("source_rows", "initialization_rows", "physical_rows", "initial_row_policy", "output"):
        print(f"{key.upper()}={summary[key]}")
    return 0


def _run_commands(commands: list[list[str]]) -> int:
    for command in commands:
        result = subprocess.run(command, cwd=ROOT, check=False)
        if result.returncode != 0:
            return int(result.returncode)
    return 0


def internal_cli(target: str) -> int:
    if target not in INTERNAL_TARGETS:
        known = ", ".join(INTERNAL_TARGETS)
        print(f"unknown internal target: {target}; choose from {known}", file=sys.stderr)
        return 2
    commands: list[list[str]] = []
    if target in {"architecture", "all"}:
        commands.extend([
            [sys.executable, str(ROOT / "tools" / "qpx_dependency_guard.py")],
            [sys.executable, str(ROOT / "tools" / "qpx_experiment_gateway_guard.py")],
            [sys.executable, str(ROOT / "tools" / "qpx_architecture_census.py")],
        ])
    if target in {"regression", "all"}:
        commands.append([sys.executable, "-m", "pytest", "-q"])
    return _run_commands(commands)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in {"-h", "--help", "help"}:
        print_help()
        return 0

    if args[0] in {"-e", "--experiment"}:
        if len(args) != 2:
            print("usage: python3 bin/qpx.py -e <experiment.json>", file=sys.stderr)
            return 2
        try:
            return run_experiment(args[1])
        except (OSError, ValueError, TypeError) as exc:
            print(f"experiment configuration error: {exc}", file=sys.stderr)
            return 2

    if args[0] in {"-i", "--internal"}:
        if len(args) != 2:
            print("usage: python3 bin/qpx.py -i <internal-target>", file=sys.stderr)
            return 2
        return internal_cli(args[1])

    command, rest = args[0], args[1:]
    if command == "preflight":
        return preflight_cli(rest)
    if command == "temporal-csv":
        return temporal_csv_cli(rest)

    handler = _resolve_legacy_handler(command)
    if handler is None:
        print(f"unknown command: {command}", file=sys.stderr)
        print_help()
        return 2
    return handler(rest)
