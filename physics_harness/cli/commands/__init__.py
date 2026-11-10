"""Bounded command adapters; optional performance dependencies load lazily."""
from __future__ import annotations

from importlib import import_module

__all__ = ["performance"]


def __getattr__(name: str):
    if name == "performance":
        module = import_module(".performance", __name__)
        globals()[name] = module
        return module
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
