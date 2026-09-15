#!/usr/bin/env python3
"""Second harness-corrected W2 rerun for Issue #228."""
from __future__ import annotations

import argparse
from pathlib import Path

from experiments.Issue228_p2_e1_w2_pg import run as base

_ORIGINAL_BUILD_W2_INPUT = base.build_w2_input


def corrected_w2_input() -> str:
    return """[Problem]
  kernel_coverage_check = false
[]

""" + _ORIGINAL_BUILD_W2_INPUT()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--suppression-fraction", type=float, required=True)
    p.add_argument("--snapshot-root", type=Path, required=True)
    p.add_argument("--physics-opt", type=Path, required=True)
    p.add_argument("--results-root", type=Path, required=True)
    a = p.parse_args()
    base.build_w2_input = corrected_w2_input
    return base.run_w2(a)


if __name__ == "__main__":
    raise SystemExit(main())
