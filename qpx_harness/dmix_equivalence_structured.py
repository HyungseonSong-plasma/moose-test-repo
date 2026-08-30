"""Compatibility shim for the canonical D_mix equivalence harness.

The structured C++ call-parsing implementation now lives in
``qpx_harness.dmix_equivalence``. This module remains temporarily so existing
Issue31 and CLI consumers keep their import path until their own migration.
"""

from __future__ import annotations

from typing import Iterable

from . import dmix_equivalence as canonical

EquivalenceError = canonical.EquivalenceError
legacy_source_transform = canonical.legacy_source_transform
legacy_source = canonical.legacy_source


def self_test() -> int:
    return canonical.self_test()


def main(argv: Iterable[str] | None = None) -> int:
    return canonical.main(list(argv) if argv is not None else None)


if __name__ == "__main__":
    raise SystemExit(main())
