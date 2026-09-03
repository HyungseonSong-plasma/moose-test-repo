"""Compatibility facade for :mod:`qpx_harness.evidence_engine.errors`.

The canonical attribution and dual-ledger implementation now lives in
``evidence_engine``. This module remains only for legacy campaign imports.
"""
from qpx_harness.evidence_engine.errors import *  # noqa: F401,F403
from qpx_harness.evidence_engine.errors import __all__
