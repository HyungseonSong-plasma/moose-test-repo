"""Compatibility facade for Issue31 EVR1 runtime orchestration."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable

from recipes import issue31_coupling as recipe

from .cases import CaseError
from .coupling_evr1.characterization import self_test
from .coupling_evr1.classification import (
    _status,
    _wall,
    preliminary_classification,
)
from .coupling_evr1.orchestration import (
    EXPERIMENT_ID,
    PURGE_DIRECTORY_NAMES,
    PURGE_PATTERNS,
    CouplingEVR1RuntimeError,
    _create_root,
    _load_json,
    _manifest,
    _run_pair,
    run,
)
from .dmix_equivalence import legacy_source_transform
from .performance_core import PerformanceContractError


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qpx coupling-evr1")
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
        CouplingEVR1RuntimeError,
        CaseError,
        PerformanceContractError,
        SystemExit,
    ) as exc:
        print(f"ISSUE31_EVR1_FATAL: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
