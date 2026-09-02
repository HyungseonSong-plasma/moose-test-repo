"""Compatibility adapter; canonical owner is qpx_harness.inventory.first_linear_structure."""
from __future__ import annotations

from ..inventory import first_linear_structure as _owner

for _name in dir(_owner):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_owner, _name)
