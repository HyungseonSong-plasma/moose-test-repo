#!/usr/bin/env python3
"""Compatibility CLI for qpx_harness.regression.run_suite."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness.regression import cli_run_all

if __name__ == "__main__":
    raise SystemExit(cli_run_all())
