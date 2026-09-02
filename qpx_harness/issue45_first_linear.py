"""Compatibility facade for the canonical inventory first-linear diagnostic.

New consumers must import qpx_harness.inventory first-linear owners directly.
"""
from __future__ import annotations

from .inventory.first_linear_characterization import *
from .inventory.first_linear_orchestration import *
from .inventory.first_linear_stats import *
from .inventory.first_linear_structure import *
from .inventory.cli import first_linear_main as main


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv[1:]))
