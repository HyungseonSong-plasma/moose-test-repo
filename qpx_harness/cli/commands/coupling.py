"""CLI presentation for the Issue31 coupling discriminators."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable

from recipes import issue31_coupling as recipe

from ...coupling_evr1.characterization import self_test as evr1_self_test
from ...coupling_evr1.orchestration import CouplingEVR1RuntimeError, run as run_evr1
from ...coupling_evr2.orchestration import (
    CouplingEVR2RuntimeError,
    run as run_evr2,
    self_test as evr2_self_test,
)
from ...execution.cases import CaseError
from ...performance.runner import PerformanceContractError


def _parser(command: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=f"qpx {command}")
    parser.add_argument("--qpx")
    parser.add_argument("--asset-case", type=Path)
    parser.add_argument("--base-input", type=Path)
    parser.add_argument("--results-root", type=Path)
    parser.add_argument("--self-test", action="store_true")
    return parser


def coupling_evr1_main(argv: Iterable[str] | None = None) -> int:
    args = _parser("coupling-evr1").parse_args(list(argv) if argv is not None else None)
    if args.self_test:
        return evr1_self_test()
    try:
        return run_evr1(args)
    except (CouplingEVR1RuntimeError, CaseError, PerformanceContractError, SystemExit) as exc:
        print(f"ISSUE31_EVR1_FATAL: {exc}", file=sys.stderr)
        return 2


def coupling_evr2_main(argv: Iterable[str] | None = None) -> int:
    args = _parser("coupling-evr2").parse_args(list(argv) if argv is not None else None)
    if args.self_test:
        return evr2_self_test()
    try:
        return run_evr2(args)
    except (
        CouplingEVR2RuntimeError,
        recipe.Issue31CouplingError,
        PerformanceContractError,
        CaseError,
        SystemExit,
    ) as exc:
        print(f"ISSUE31_EVR2_FATAL: {exc}", file=sys.stderr)
        return 2
