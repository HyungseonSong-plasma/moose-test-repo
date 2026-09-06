"""CLI presentation for reusable performance measurement and analysis."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable

from ...application import performance


def measure_main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qpx measure")
    parser.add_argument("manifest", nargs="?")
    parser.add_argument("--qpx")
    parser.add_argument("--out-dir")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.self_test:
        return performance.self_test()
    if not args.manifest:
        parser.error("manifest is required unless --self-test is used")
    try:
        return performance.run_measurement(
            Path(args.manifest),
            executable=args.qpx,
            out_dir=Path(args.out_dir) if args.out_dir else None,
        )
    except performance.PerformanceContractError as exc:
        print(f"PERFORMANCE_CONTRACT_FAIL: {exc}", file=sys.stderr)
        return 2


def analyze_main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qpx analyze")
    parser.add_argument("--summary", required=True)
    parser.add_argument("--petsc-log", required=True)
    parser.add_argument("--perf-log")
    parser.add_argument("--json-out")
    parser.add_argument("--metric-prefix")
    args = parser.parse_args(list(argv) if argv is not None else None)
    result = performance.analyze_profile(
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


__all__ = ["analyze_main", "measure_main"]
