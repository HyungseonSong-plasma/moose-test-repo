"""CLI presentation for optimized-versus-legacy D_mix validation."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from qpx_harness.analysis.dmix_equivalence import REL_TOL
from qpx_harness.validation.dmix_equivalence import self_test
from qpx_harness.execution.dmix_equivalence import validate
from qpx_harness.adapters.moose.dmix_equivalence import EquivalenceError


def dmix_equivalence_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qpx dmix-equivalence")
    parser.add_argument("--qpx")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--base-case", type=Path)
    parser.add_argument("--build-command")
    parser.add_argument("--jobs", type=int)
    parser.add_argument("--rel-tol", type=float, default=REL_TOL)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    try:
        return validate(args)
    except (EquivalenceError, SystemExit) as exc:
        print("DMIX_EQ_FATAL:", exc, file=sys.stderr)
        return 2
