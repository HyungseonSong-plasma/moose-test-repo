"""Compatibility facade for the canonical electron-inventory capability.

New consumers must import qpx_harness.inventory. This module preserves the
historical command/import surface only while remaining downstream consumers are
migrated.
"""
from __future__ import annotations

from .inventory.characterization import *
from .inventory.closure_model import *
from .inventory.closure_runtime import *
from .inventory.closure_schema import *
from .inventory.constants import *
from .inventory.errors import *
from .inventory.orchestration import *
from .inventory.structure import *
from .inventory.cli import inventory_main as main


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv[1:]))
