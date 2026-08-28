#!/usr/bin/env python3
"""Legacy issue-#32 CLI backed by qpx_harness.analysis."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness.analysis import analyze


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", required=True)
    parser.add_argument("--petsc-log", required=True)
    parser.add_argument("--perf-log")
    parser.add_argument("--json-out")
    args = parser.parse_args()

    result = analyze(
        Path(args.summary),
        Path(args.petsc_log),
        Path(args.perf_log) if args.perf_log else None,
        metric_prefix="r32",
    )
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    print(text, end="")
    if args.json_out:
        Path(args.json_out).write_text(text)
    return 0 if result.get("interpretable_performance") else 2


if __name__ == "__main__":
    raise SystemExit(main())
