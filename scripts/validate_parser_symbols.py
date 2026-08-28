#!/usr/bin/env python3
"""Compatibility CLI for qpx_harness.preflight parser-symbol checks."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from qpx_harness.preflight import (  # noqa: E402,F401
    IDENTIFIER_RE,
    PARSED_FUNCTOR_TYPES,
    RESERVED_SYMBOLS,
    parser_symbol_self_test,
    validate_file,
    validate_text,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reject ParsedFunctorMaterial parser-symbol collisions before qpx-opt."
    )
    parser.add_argument("paths", nargs="*", help="MOOSE input files to scan")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return parser_symbol_self_test()

    if not args.paths:
        parser.error("provide at least one input path or --self-test")

    errors: list[str] = []
    for raw in args.paths:
        path = Path(raw)
        if not path.is_file():
            errors.append(f"{path}: file not found")
            continue
        errors.extend(validate_file(path))

    if errors:
        print("PARSER_SYMBOL_PREFLIGHT: FAIL")
        for error in errors:
            print("  -", error)
        return 2

    print("PARSER_SYMBOL_PREFLIGHT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
