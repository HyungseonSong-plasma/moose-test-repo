"""Compatibility import for the canonical Issue46 FD-reference runtime owner.

Stable callers may continue importing this module during Issue48 convergence,
but all behavior is owned by ``qpx_harness.issue46_fd_reference``.
"""
from __future__ import annotations

from qpx_harness.issue46_fd_reference import main, recipe_backing_status, self_test

__all__ = ["main", "recipe_backing_status", "self_test"]
