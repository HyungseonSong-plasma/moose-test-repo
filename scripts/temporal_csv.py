#!/usr/bin/env python3
"""Compatibility CLI for qpx_harness.temporal."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from qpx_harness.temporal import (  # noqa: E402,F401
    VALID_INITIAL_POLICIES,
    normalize_from_manifest,
    normalize_temporal_csv,
    self_test,
)


def main() -> int:
    parser = argparse.ArgumentParser()
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
    args = parser.parse_args()

    if args.self_test:
        return self_test()

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


if __name__ == "__main__":
    raise SystemExit(main())
