"""Unified thin command routing for the reusable Physics harness."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from importlib import import_module
import json
from pathlib import Path
import subprocess
import sys

# Import optional scientific/data dependencies only inside their owning command.\n# C0 source inventory must run before any heavy analysis dependencies are installed.\n\nROOT = Path(__file__).resolve().parents[2]


def compile_experiment(source):
    """Preserve the public CLI patch point while avoiding eager gateway imports."""
    from physics_harness.application.gateway import compile_experiment as _compile_experiment
    return _compile_experiment(source)


def plan_experiment(source):
    """Preserve Issue #280's monkeypatch boundary without importing polars at startup."""
    from physics_harness.application.gateway import plan_experiment as _plan_experiment
    return _plan_experiment(source)


CANONICAL_COMMANDS = {
    "compile": "compile semantic experiment JSON into ExperimentIntent",
    "plan": "compile semantic intent and synthesize ScientificPolicy/ExecutionPlan",
    "lower": "retired: direct local MOOSE lowering is forbidden",
    "run": "prepare one canonical semantic experiment for target execution",
    "preflight": "run static parser-symbol preflight on one MOOSE input",
    "native-build": "build pinned MOOSE PhysicsApp within trusted OCI using a scoped adaptive profile",
    "native-p1-record": "verify successful P1 report and record exact executable identity",
    "validate-input": "run Native P2 only with verified P1 evidence",
    "temporal-csv": "normalize transient CSV rows under an explicit temporal policy",
    "oxygen-c0": "audit a 400 W Oxygen14 chemistry-off candidate without executing MOOSE",
    "oxygen-profile": "extract plasma-region electron density/energy profiles from native Exodus",
    "default-plot": "auto-plot Exodus nodal fields with flexible layouts and optional input-variable filter",
    "research": "opt-in human research objective and evaluation-scope clarification before analysis",
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
    "architecture": "run SOL architecture guard and architecture tests",
    "regression": "run Physics Python regression/unit tests",
    "all": "run architecture checks and full Python regression",
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
    print("  physics native-build --source-root <checkout> --expected-sha <sha> --log-dir <dir> --report <file>")
    print("  physics research start <data> --session <session.json>")
    print("  physics research <goal|scope|confirm|status|check|execute> ...")
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
    from physics_harness.specification import ExperimentSpecError

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
    from physics_harness.specification import ExperimentSpecError

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
    args = parser.parse_args(argv)
    print("LOWER_RETIRED: use the explicit SOL realization/request boundary; no local MOOSE lowering", file=sys.stderr)
    return 3


def semantic_run_cli(argv: list[str]) -> int:
    """Prepare only the canonical semantic pipeline; never dispatch a protocol runner."""
    from physics_harness.specification import ExperimentSpecError

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
        "SOL_REQUEST: BLOCKED (reviewed realization model, capabilities, and pinned runtime/adapter "
        "must be supplied; local MOOSE fallback is forbidden)",
        file=sys.stderr,
    )
    return 3


def preflight_cli(argv: list[str]) -> int:
    from physics_harness.adapters.moose.preflight import validate_input_preflight

    parser = argparse.ArgumentParser(prog="physics preflight")
    parser.add_argument("input", help="MOOSE input file to inspect")
    args = parser.parse_args(argv)
    validate_input_preflight(Path(args.input).expanduser().resolve())
    return 0


def temporal_csv_cli(argv: list[str]) -> int:
    from physics_harness.application import normalize_temporal_run_csv
    from physics_harness.analysis.temporal import VALID_INITIAL_POLICIES

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
    architecture = [[sys.executable, "-m", "pytest", "-q", "tests/architecture"]]
    regression = [[sys.executable, "-m", "pytest", "-q"]]
    if target == "architecture":
        return _run_commands(architecture)
    if target == "all":
        return _run_commands(architecture + regression)
    return _run_commands(regression)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in {"-h", "--help", "help"}:
        print_help()
        return 0
    if args[0] == "-i":
        if len(args) != 2:
            print("usage: physics -i <architecture|regression|all>", file=sys.stderr)
            return 2
        return internal_cli(args[1])
    canonical_handlers = {
        "compile": semantic_compile_cli,
        "plan": semantic_plan_cli,
        "lower": semantic_lower_cli,
        "run": semantic_run_cli,
        "preflight": preflight_cli,
        "native-build": lambda argv: import_module("physics_harness.execution.native_build").main(argv),
        "native-p1-record": lambda argv: import_module("physics_harness.cli.commands.native_validation").native_p1_record_cli(argv),
        "validate-input": lambda argv: import_module("physics_harness.cli.commands.native_validation").validate_input_cli(argv),
        "temporal-csv": temporal_csv_cli,
        "oxygen-c0": lambda argv: import_module("experiments.Issue395_powered_chemistry_ladder.chemistry_off_c0").main(argv),
        "oxygen-profile": lambda argv: import_module("experiments.Issue395_powered_chemistry_ladder.electron_profile_exodus").main(argv),
        "default-plot": lambda argv: import_module("physics_harness.adapters.moose.default_plot").main(argv),
        "research": lambda argv: import_module("physics_harness.cli.commands.research").main(argv),
    }
    canonical = canonical_handlers.get(args[0])
    if canonical is not None:
        return canonical(args[1:])
    handler = _resolve_legacy_handler(args[0])
    if handler is not None:
        return handler(args[1:])
    print(f"unknown command: {args[0]}", file=sys.stderr)
    print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
