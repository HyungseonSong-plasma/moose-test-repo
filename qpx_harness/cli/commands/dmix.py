"""CLI presentation for optimized-versus-legacy D_mix validation."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ...dmix.analysis import REL_TOL
from ...dmix.characterization import self_test
from ...dmix.runtime import validate
from ...dmix.source_transform import EquivalenceError


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
