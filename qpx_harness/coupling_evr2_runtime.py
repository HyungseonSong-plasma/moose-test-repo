"""Compatibility CLI adapter for Issue31 EVR2 orchestration.

Reusable mechanics and Issue31 policy composition live outside this adapter.
Issue #79 owns final migration into qpx_harness.cli and retirement.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable

from recipes import issue31_coupling as recipe

from .coupling_evr2.orchestration import (
    CouplingEVR2RuntimeError,
    run,
    self_test,
)
from .execution.cases import CaseError
from .performance.runner import PerformanceContractError


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qpx coupling-evr2")
    parser.add_argument("--qpx")
    parser.add_argument("--asset-case", type=Path)
    parser.add_argument("--base-input", type=Path)
    parser.add_argument("--results-root", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.self_test:
        return self_test()
    try:
        return run(args)
    except (
        CouplingEVR2RuntimeError,
        recipe.Issue31CouplingError,
        PerformanceContractError,
        CaseError,
        SystemExit,
    ) as exc:
        print(f"ISSUE31_EVR2_FATAL: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

