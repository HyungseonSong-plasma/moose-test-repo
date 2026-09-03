"""Backward-compatible facade for the modular diagnosis package.

New code should import from :mod:`qpx_harness.evidence_engine.diagnosis` or from
the package-level :mod:`qpx_harness.evidence_engine` API. This module remains so
existing callers using ``evidence_engine.diagnose`` do not break.
"""
from .diagnosis import *  # noqa: F401,F403
from .diagnosis import __all__
