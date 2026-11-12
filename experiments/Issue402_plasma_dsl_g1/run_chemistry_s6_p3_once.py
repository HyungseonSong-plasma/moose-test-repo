#!/usr/bin/env python3
"""Operator-authorized Chemistry-specific S6 D P3 runner.

This CLI is intentionally NOT wired to any GitHub workflow. Without an
explicit --authorize-p3 flag it cannot execute a Native timestep.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from run_canonical_s6_p3_once import run
from p3_chemistry_preflight import audit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=("417", "941"), required=True)
    parser.add_argument("--historical", type=Path, required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=19800)
    parser.add_argument("--authorize-p3", action="store_true",
                        help="Explicitly authorize this single expensive Native P3 run.")
    args = parser.parse_args()
    if not args.authorize_p3:
        parser.error("P3_NOT_AUTHORIZED: --authorize-p3 must be explicit")
    readiness = audit()
    if readiness["status"] != "STATIC_INPUTS_READY_P3_NOT_AUTHORIZED":
        parser.error("P3_STATIC_READINESS_NOT_PASSED")
    result = run(args.case, args.historical.resolve(), args.expected_head,
                 args.output.resolve(), args.timeout_seconds, chemistry_mode=True)
    return 0 if result["P3"] == "PASS" else 3


if __name__ == "__main__":
    sys.exit(main())
