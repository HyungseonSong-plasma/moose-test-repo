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
from qpx_harness.bundle import main as bundle_main
from qpx_harness.performance_core import main as performance_main, self_test as performance_self_test
from qpx_harness.preflight import parser_symbol_self_test, validate_input_preflight
from qpx_harness.profiling import main as profile_main
from qpx_harness.regression import cli_run_all, cli_run_test
from qpx_harness.temporal import self_test as temporal_self_test
from qpx_harness.workspace import inventory_cli, self_test as workspace_self_test


COMMANDS = {
    "test": "run one test.json case",
    "test-all": "discover and run a canonical/diagnostic suite",
    "measure": "run one schema-driven QPX performance measurement",
    "profile": "capture one-step legacy P2/P3 performance evidence",
    "analyze": "classify PETSc/PerfGraph profiling evidence",
    "bundle": "build a declarative local profiling bundle",
    "inventory": "inspect or compare QPX workspace trees",
    "preflight": "run static parser-symbol preflight on one MOOSE input",
    "self-test": "run harness parser/temporal/workspace/performance self-tests",
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
        Path(args.petsc_log),
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
    parser.add_argument("input", help="MOOSE input file to inspect")
    args = parser.parse_args(argv)
    validate_input_preflight(Path(args.input).expanduser().resolve())
    return 0


def self_test_cli(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="qpx self-test")
    parser.parse_args(argv)
    parser_rc = parser_symbol_self_test()
    temporal_rc = temporal_self_test()
    workspace_rc = workspace_self_test()
    performance_rc = performance_self_test()
    ok = (
        parser_rc == 0
        and temporal_rc == 0
        and workspace_rc == 0
        and performance_rc == 0
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
    if command == "measure":
        return performance_main(rest)
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
    if command == "self-test":
        return self_test_cli(rest)

    print(f"unknown command: {command}", file=sys.stderr)
    print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
