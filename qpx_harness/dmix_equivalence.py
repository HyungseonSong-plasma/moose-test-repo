"""Compatibility facade for optimized-vs-legacy D_mix equivalence validation."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .dmix.analysis import (
    REL_TOL,
    SPECIES,
    TAGS,
    TRACE,
    compare,
    quoted_values,
    read_dmix,
    trace_input,
)
from .dmix.characterization import self_test
from .dmix.runtime import (
    BASE_CASE_RELATIVE,
    SOURCE_RELATIVE,
    _create_result_root,
    prepare_case,
    run_case,
    sha256,
    stream,
    validate,
    write_json,
)
from .dmix.source_transform import EquivalenceError, legacy_source, legacy_source_transform


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="qpx dmix-equivalence")
    p.add_argument("--qpx")
    p.add_argument("--source", type=Path)
    p.add_argument("--base-case", type=Path)
    p.add_argument("--build-command")
    p.add_argument("--jobs", type=int)
    p.add_argument("--rel-tol", type=float, default=REL_TOL)
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args(argv)
    if args.self_test:
        return self_test()
    try:
        return validate(args)
    except (EquivalenceError, SystemExit) as exc:
        print("DMIX_EQ_FATAL:", exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
