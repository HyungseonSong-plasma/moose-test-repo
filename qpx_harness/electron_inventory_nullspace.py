"""Compatibility facade for the canonical electron-inventory capability.

New consumers must import qpx_harness.inventory. This module preserves the
historical command/import surface only while remaining downstream consumers are
migrated.
"""
from __future__ import annotations

from .inventory import characterization as _characterization
from .inventory import closure_model as _closure_model
from .inventory import closure_runtime as _closure_runtime
from .inventory import closure_schema as _closure_schema
from .inventory import constants as _constants
from .inventory import errors as _errors
from .inventory import orchestration as _orchestration
from .inventory import structure as _structure
from .inventory.cli import inventory_main as main

for _module in (
    _constants,
    _errors,
    _closure_schema,
    _closure_model,
    _structure,
    _closure_runtime,
    _orchestration,
    _characterization,
):
    for _name in dir(_module):
        if not _name.startswith("__"):
            globals()[_name] = getattr(_module, _name)


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv[1:]))
