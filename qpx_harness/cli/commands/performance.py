"""CLI-only presentation for performance measurement and analysis commands."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Iterable

from ...analysis.performance import cache, investigation, profile
from ...evidence import (
    create_collision_safe_directory,
    utc_timestamp,
    write_json_bundle,
)
from ...execution.performance import runner, smoke
from ...execution.performance.probes import runtime as probe_runtime
from ...execution.performance.probes import transport

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CACHE_CASE = Path("tests/Issue22_qvt_transient_species_accumulation/input.i")


def measure_main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qpx measure")
    parser.add_argument("manifest", nargs="?")
    parser.add_argument("--qpx")
    parser.add_argument("--out-dir")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.self_test:
        return runner.self_test()
    if not args.manifest:
        parser.error("manifest is required unless --self-test is used")
    try:
        return runner.run_measurement(
            Path(args.manifest),
            executable=args.qpx,
            out_dir=Path(args.out_dir) if args.out_dir else None,
        )
    except runner.PerformanceContractError as exc:
        print(f"PERFORMANCE_CONTRACT_FAIL: {exc}", file=sys.stderr)
        return 2


def measure_smoke_main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qpx measure-smoke")
    parser.add_argument("case_dir", nargs="?")
    parser.add_argument("--input", default="input.i")
    parser.add_argument("--qpx")
    parser.add_argument("--results-root")
    parser.add_argument("--case-id")
    parser.add_argument("--experiment-id", default="pf1-runtime-smoke")
    parser.add_argument("--num-steps", type=int, default=1)
    parser.add_argument("--species", nargs="*")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.self_test:
        return smoke.self_test()
    if not args.case_dir:
        parser.error("case_dir is required unless --self-test is used")
    try:
        return smoke.run_smoke_pair(
            case_dir=Path(args.case_dir),
            input_name=args.input,
            executable=args.qpx,
            results_root=Path(args.results_root) if args.results_root else None,
            case_id=args.case_id,
            experiment_id=args.experiment_id,
            num_steps=args.num_steps,
            species=args.species or None,
        )
    except runner.PerformanceContractError as exc:
        print(f"PERFORMANCE_CONTRACT_FAIL: {exc}", file=sys.stderr)
        return 2


def investigate_main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qpx investigate")
    parser.add_argument("--run-root")
    parser.add_argument("--qpx")
    parser.add_argument("--results-root")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.self_test:
        return investigation.self_test()
    if not args.run_root and not args.qpx:
        parser.error("provide --qpx for automatic discovery or --run-root for an explicit smoke run")
    try:
        return investigation.run_investigation(
            run_root=Path(args.run_root) if args.run_root else None,
            executable=args.qpx,
            results_root=Path(args.results_root) if args.results_root else None,
        )
    except (runner.PerformanceContractError, json.JSONDecodeError) as exc:
        print(f"PF3_INVESTIGATION_FAIL: {exc}", file=sys.stderr)
        return 2


def transport_probe_main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qpx transport-probe")
    parser.add_argument("--qpx")
    parser.add_argument("--smoke-root")
    parser.add_argument("--source")
    parser.add_argument("--build-command")
    parser.add_argument("--jobs", type=int)
    parser.add_argument("--allow-source-sha-mismatch", action="store_true")
    parser.add_argument("--restore-run")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.self_test:
        if probe_runtime.self_test() != 0:
            return 1
        return transport.self_test()
    try:
        if args.restore_run:
            executable = Path(args.qpx).expanduser().resolve() if args.qpx else None
            return probe_runtime.restore_probe(Path(args.restore_run), executable)
        return probe_runtime.run_managed_probe(
            executable_arg=args.qpx,
            instrument_source=transport.instrument_source,
            analyze_probe=transport.analyze_probe,
            smoke_root_arg=Path(args.smoke_root) if args.smoke_root else None,
            source_arg=Path(args.source) if args.source else None,
            build_command_arg=args.build_command,
            jobs=args.jobs,
            allow_source_sha_mismatch=args.allow_source_sha_mismatch,
        )
    except (
        probe_runtime.ProbeRuntimeError,
        transport.ProbeError,
        OSError,
        json.JSONDecodeError,
    ) as exc:
        print(f"PF3_TRANSPORT_PROBE_FAIL: {exc}", file=sys.stderr)
        return 2


def _cache_run_root(results: Path, *, timestamp: str | None = None) -> Path:
    stamp = timestamp or utc_timestamp()
    return create_collision_safe_directory(results, f"cache_audit_{stamp}")


def _cache_cli_self_test() -> int:
    try:
        with tempfile.TemporaryDirectory() as tmp_name:
            results = Path(tmp_name)
            first = _cache_run_root(results, timestamp="20260831T103000Z")
            second = _cache_run_root(results, timestamp="20260831T103000Z")
            if first.name != "cache_audit_20260831T103000Z":
                raise AssertionError(f"cache-audit first root naming drift: {first.name}")
            if second.name != "cache_audit_20260831T103000Z_01":
                raise AssertionError(f"cache-audit collision naming drift: {second.name}")
    except Exception as exc:
        print(f"QPX_CACHE_AUDIT_CLI_SELFTEST: FAIL: {exc}")
        return 1
    print("QPX_CACHE_AUDIT_CLI_SELFTEST: PASS")
    return 0


def cache_audit_self_test() -> int:
    analysis_rc = cache.self_test()
    cli_rc = _cache_cli_self_test()
    return 0 if analysis_rc == cli_rc == 0 else 1


def cache_audit_main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qpx cache-audit")
    parser.add_argument("--qpx")
    parser.add_argument("--input")
    parser.add_argument("--results-root")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.self_test:
        return cache_audit_self_test()
    if not args.qpx:
        parser.error("--qpx is required unless --self-test is used")
    qpx = Path(args.qpx).expanduser().resolve()
    if not qpx.is_file():
        print(f"QPX_CACHE_AUDIT_ERROR: qpx executable not found: {qpx}", file=sys.stderr)
        return 2
    input_path = (
        Path(args.input).expanduser().resolve()
        if args.input
        else REPOSITORY_ROOT / DEFAULT_CACHE_CASE
    )
    try:
        result = cache.audit_qpx_tree(qpx.parent, input_path)
        results = (
            Path(args.results_root).expanduser().resolve()
            if args.results_root
            else qpx.parent / "temp" / "results"
        )
        root = _cache_run_root(results)
        result["qpx_executable"] = str(qpx)
        summary = Path(
            write_json_bundle(root, {"summary": ("cache_audit.json", result)})[
                "summary"
            ]
        )
    except Exception as exc:
        print(f"QPX_CACHE_AUDIT_ERROR: {exc}", file=sys.stderr)
        return 2

    type_counts: dict[str, int] = {}
    for row in result["input_consumers"]:
        type_counts[row["type"]] = type_counts.get(row["type"], 0) + 1
    print(f"QPX_CACHE_AUDIT_ROOT: {root}")
    print(f"QPX_CACHE_AUDIT_STATUS: {result['analysis_status']}")
    print(f"QPX_CACHE_INPUT: {result['input_path']}")
    print("QPX_CACHE_INPUT_CONSUMERS:", json.dumps(type_counts, sort_keys=True))
    print(f"QPX_CACHE_MATERIAL_SHA256: {result['material_sha256']}")
    print(f"QPX_CACHE_DMIX_DECLARATION: {result['dmix_declaration']['schedule_kind']}")
    print(
        "QPX_CACHE_DMIX_CALLS_FULL_EVALUATE:",
        result["dmix_declaration"]["calls_full_evaluate"],
    )
    print("QPX_CACHE_SPACE_ARGS:", json.dumps(result["space_arg_counts"], sort_keys=True))
    print(f"QPX_CACHE_NATIVE_ELIGIBLE: {result['native_cache_eligible']}")
    print(f"QPX_CACHE_RECOMMENDATION: {result['recommendation']}")
    print(f"QPX_CACHE_REASON: {result['reason']}")
    print(f"QPX_CACHE_SUMMARY: {summary}")
    return 0 if result["analysis_status"] == "PASS" else 2


def analyze_main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qpx analyze")
    parser.add_argument("--summary", required=True)
    parser.add_argument("--petsc-log", required=True)
    parser.add_argument("--perf-log")
    parser.add_argument("--json-out")
    parser.add_argument("--metric-prefix")
    args = parser.parse_args(list(argv) if argv is not None else None)
    result = profile.analyze(
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


__all__ = [
    "analyze_main",
    "cache_audit_main",
    "cache_audit_self_test",
    "investigate_main",
    "measure_main",
    "measure_smoke_main",
    "transport_probe_main",
]
