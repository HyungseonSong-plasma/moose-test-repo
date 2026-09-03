"""Compatibility entrypoint for the canonical Evidence -> Diagnose local smoke."""
from qpx_harness.evidence_diagnose_smoke import *  # noqa: F401,F403
from qpx_harness.evidence_diagnose_smoke import __all__

if __name__ == "__main__":
    raise SystemExit(main())
