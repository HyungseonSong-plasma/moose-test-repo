"""Historical compatibility proxy for the canonical Issue46 FD-reference owner.

All runtime, preflight, evidence, and scientific-policy composition now lives in
``qpx_harness.issue46_fd_reference``.  This module remains temporarily so the
last characterization consumers can migrate without changing their accepted
attribute surface in the same cut.
"""
from __future__ import annotations

from . import issue46_fd_reference as _owner


def __getattr__(name: str):
    return getattr(_owner, name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(dir(_owner)))


if __name__ == "__main__":
    raise SystemExit(_owner.main())
