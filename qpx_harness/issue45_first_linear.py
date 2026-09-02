"""Compatibility facade for the canonical inventory first-linear diagnostic.

New consumers must import qpx_harness.inventory first-linear owners directly.
"""
from __future__ import annotations

from .inventory import first_linear_characterization as _characterization
from .inventory import first_linear_orchestration as _orchestration
from .inventory import first_linear_stats as _stats
from .inventory import first_linear_structure as _structure
from .inventory.cli import first_linear_main as main

for _module in (_structure, _stats, _orchestration, _characterization):
    for _name in dir(_module):
        if not _name.startswith("__"):
            globals()[_name] = getattr(_module, _name)


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv[1:]))
