#!/usr/bin/env python3
"""Canonical process entrypoint for the Physics harness CLI."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _preflight_fast_path(argv: list[str]) -> int | None:
    """Run parser-symbol preflight without importing the full harness dependency graph."""
    if not argv or argv[0] != "preflight":
        return None

    from physics_harness.adapters.moose.preflight import (
        parser_symbol_self_test,
        validate_input_preflight,
    )

    args = argv[1:]
    if args == ["--self-test"]:
        return parser_symbol_self_test()
    if len(args) != 1:
        print(
            "usage: physics preflight <input.i> | physics preflight --self-test",
            file=sys.stderr,
        )
        return 2

    validate_input_preflight(Path(args[0]).expanduser().resolve())
    return 0


def _main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    preflight_result = _preflight_fast_path(args)
    if preflight_result is not None:
        return preflight_result

    from physics_harness.cli import main

    return main(args)


if __name__ == "__main__":
    raise SystemExit(_main())
