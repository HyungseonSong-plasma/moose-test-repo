#!/usr/bin/env python3
"""Canonical process entrypoint for the QPX harness CLI."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
