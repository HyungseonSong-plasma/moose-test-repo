"""Unified thin command routing for the reusable Physics harness."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from importlib import import_module
import json
from pathlib import Path
import subprocess
import sys

from physics_harness.application import normalize_temporal_run_csv
from physics_harness.adapters.moose.preflight import validate_input_preflight
from physics_harness.application.gateway import compile_experiment, plan_experiment
from physics_harness.analysis.temporal import VALID_INITIAL_POLICIES
from physics_harness.specification import ExperimentSpecError

ROOT = Path(__file__).resolve().parents[2]

CANONICAL_COMMANDS = {
    "compile": "compile semantic experiment JSON into ExperimentIntent",
    "plan": "compile semantic intent and synthesize ScientificPolicy/ExecutionPlan",
    "lower": "retired: local target lowering is not a canonical Physics operation",
    "run": "prepare Physics semantics for the canonical SOL request/runtime boundary",
    "preflight": "run static parser-symbol preflight on one MOOSE input",
    "temporal-csv": "normalize transient CSV rows under an explicit temporal policy",
}

COMMANDS = {
    "test": "run one test.json case",
    "test-all": "discover and run a canonical/diagnostic suite",
    "contract": "validate/evaluate a scientific execution contract",
    "measure": "run one schema-driven performance measurement (including PROFILE mode)",
    "analyze": "classify decoded performance profiling evidence",
    "inventory": "inspect or compare workspace trees",
}

INTERNAL_TARGETS = {
    "regression": "run the Physics Python regression/unit suite",
}

_LEGACY_TARGETS = {
    "test": "physics_harness.adapters.moose.regression:cli_run_test",
    "test-all": "physics_harness.adapters.moose.regression:cli_run_all",
    "contract": "physics_harness.execution.contract:main",
    "measure": "physics_harness.cli.commands.performance:measure_main",
    "analyze": "physics_harness.cli.commands.performance:analyze_main",
    "inventory": "physics_harness.execution.workspace:inventory_cli",
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
    print("  physics compile <experiment.json>")
    print("  physics plan <experiment.json>")
    print("  physics lower <experiment.json>")
    print("  physics run <experiment.json>")
    print("  physics -i <internal-target>          # compatibility/internal")
    print("\ncanonical commands:")
    width = max(len(name) for name in CANONICAL_COMMANDS)
    for name, description in CANONICAL_COMMANDS.items():
        print(f"  {name:<{width}}  {description}")
    print("\ninternal targets:")
    for name, description in INTERNAL_TARGETS.items():
        print(f"  {name:<12} {description}")
    print("\nlegacy compatibility commands:")
    width = max(len(name) for name in COMMANDS)
    for name, description in COMMANDS.items():
        print(f"  {name:<{width}}  {description}")


def _json_print(value) -> None:
    print(json.dumps(asdict(value) if hasattr(value, "__dataclass_fields__") else value, indent=2, sort_keys=True, default=str))


def semantic_compile_cli(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="physics compile")
    parser.add_argument("experiment")
    args = parser.parse_args(argv)
    try:
        result = compile_experiment(args.experiment)
    except (OSError, ExperimentSpecError, ValueError, TypeError) as exc:
        print(f"semantic compilation error: {exc}", file=sys.stderr)
        return 2
    _json_print(result)
    return 0


def semantic_plan_cli(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="physics plan")
    parser.add_argument("experiment")
    args = parser.parse_args(argv)
    try:
        result = plan_experiment(args.experiment)
    except (OSError, ExperimentSpecError, ValueError, TypeError) as exc:
        print(f"planning error: {exc}", file=sys.stderr)
        return 2
    _json_print(result)
    return 0


def semantic_lower_cli(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="physics lower")
    parser.add_argument("experiment")
    parser.parse_args(argv)
    print(
        "LOWER_RETIRED: local MOOSE lowering is not a canonical Physics operation; "
        "use the reviewed SOL realization/request boundary",
        file=sys.stderr,
    )
    return 3


def semantic_run_cli(argv: list[str]) -> int:
    """Prepare Physics semantics only; never infer missing SOL realization owners."""
    parser = argparse.ArgumentParser(prog="physics run")
    parser.add_argument("experiment")
    args = parser.parse_args(argv)
    try:
        planned = plan_experiment(args.experiment)
    except (OSError, ExperimentSpecError, ValueError, TypeError) as exc:
        print(f"semantic run preparation error: {exc}", file=sys.stderr)
        return 2
    print("PHYSICS_RUN_PREPARED: PASS")
    print(f"EXPERIMENT={planned.semantic.intent.experiment_id}")
    print(f"POLICY={planned.policy.policy_id}")
    print(f"EXECUTION_PLAN={planned.execution_plan.plan_id}")
    print(
        "SOL_REQUEST: BLOCKED (canonical realization model, reviewed capability mapping, "
        "and runtime/adapter paths must be supplied explicitly; local MOOSE fallback is forbidden)",
        file=sys.stderr,
    )
    return 3


def preflight_cli(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="physics preflight")
    parser.add_argument("input", help="MOOSE input file to inspect")
    args = parser.parse_args(argv)
    validate_input_preflight(Path(args.input).expanduser().resolve())
    return 0


def temporal_csv_cli(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="physics temporal-csv")
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


def _run_internal(target: str, args: list[str]) -> int:
    if target == "regression":
        return subprocess.call([sys.executable, "-m", "pytest", "-q", *args], cwd=ROOT)
    print(f"unknown internal target: {target}", file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in {"-h", "--help"}:
        print_help()
        return 0
    if argv[0] == "-i":
        if len(argv) < 2:
            print("physics -i requires an internal target", file=sys.stderr)
            return 2
        return _run_internal(argv[1], argv[2:])
    command, args = argv[0], argv[1:]
    canonical = {
        "compile": semantic_compile_cli,
        "plan": semantic_plan_cli,
        "lower": semantic_lower_cli,
        "run": semantic_run_cli,
        "preflight": preflight_cli,
        "temporal-csv": temporal_csv_cli,
    }
    handler = canonical.get(command)
    if handler is not None:
        return handler(args)
    legacy = _resolve_legacy_handler(command)
    if legacy is not None:
        return legacy(args)
    print(f"unknown physics command: {command}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
