"""Compatibility adapter; canonical owner is qpx_harness.inventory.closure_model."""
from __future__ import annotations

from ..inventory import closure_model as _owner

for _name in dir(_owner):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_owner, _name)
