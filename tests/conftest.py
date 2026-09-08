"""Pytest import bootstrap for canonical and staged QPX workspaces.

The characterization suite may be collected either from the repository root or
from a staged ``temp/tests`` tree below the repository.  Resolve the nearest
ancestor that owns ``qpx_harness`` so repository modules remain importable in
both layouts without requiring an installed package.
"""
from __future__ import annotations

import sys
from pathlib import Path


def _repository_root() -> Path | None:
    test_file = Path(__file__).resolve()
    for candidate in test_file.parents:
        if (
            (candidate / "qpx_harness" / "__init__.py").is_file()
            and (candidate / "recipes").is_dir()
        ):
            return candidate
    return None


ROOT = _repository_root()
if ROOT is not None and str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
