"""Compatibility facade for :mod:`qpx_harness.evidence_engine.identity`.

The canonical implementation now lives in ``evidence_engine``. This module is
kept only so existing campaign imports continue to work during migration.
"""
from qpx_harness.evidence_engine.identity import *  # noqa: F401,F403
from qpx_harness.evidence_engine.identity import __all__
