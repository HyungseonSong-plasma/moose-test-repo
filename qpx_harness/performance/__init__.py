"""Deprecated performance compatibility namespace.

Performance measurement/runtime mechanics belong to execution/analysis; reusable
scientific interpretation belongs to an approved domain/reasoning owner. This
namespace remains only for bounded caller compatibility.
"""

from . import runner, smoke

COMPATIBILITY_ONLY = True

__all__ = ["runner", "smoke", "COMPATIBILITY_ONLY"]
