"""Transitional compatibility facade over canonical Evidence and Diagnose."""

from qpx_harness.evidence import *  # noqa: F401,F403
from qpx_harness.evidence import __all__ as _evidence_all
from qpx_harness.diagnose import *  # noqa: F401,F403
from qpx_harness.diagnose import __all__ as _diagnose_all

__all__ = list(dict.fromkeys((*_evidence_all, *_diagnose_all)))
