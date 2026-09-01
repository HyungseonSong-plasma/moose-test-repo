#!/usr/bin/env python3
"""WP-3B post-refactor characterization of Issue46 framework-control provenance."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness import issue46_jacobian_localization as loc


REFERENCE_REVISION = "9f388366ccf"


def main() -> int:
    try:
        report = loc.audit_framework_control_structure(
            loc.build_framework_control_input()
        )
        if report.get("status") != "PASS":
            raise AssertionError("framework-control structure is not PASS")

        source = report.get("source_contract", {})
        if "moose_commit" in source:
            raise AssertionError("ambiguous moose_commit provenance key still exists")

        reference = source.get("reference_source", {})
        if reference.get("project") != "MOOSE":
            raise AssertionError("reference-source project is not MOOSE")
        if reference.get("revision") != REFERENCE_REVISION:
            raise AssertionError("reference-source revision drifted")
        if reference.get("purpose") != "framework-control source contract":
            raise AssertionError("reference-source purpose is not explicit")

        if source.get("runtime_identity") != "OBSERVED_SEPARATELY":
            raise AssertionError("runtime identity is not explicitly separated from reference source")
    except Exception as exc:
        print(f"ISSUE47_WP3B_PROVENANCE_CHARACTERIZATION: FAIL ({exc})")
        return 1

    print("ISSUE47_WP3B_PROVENANCE_CHECK: framework-control-structure=PASS")
    print("ISSUE47_WP3B_PROVENANCE_CHECK: ambiguous-moose-commit-reference=REMOVED")
    print("ISSUE47_WP3B_PROVENANCE_CHECK: reference-source-explicit=PASS")
    print("ISSUE47_WP3B_PROVENANCE_CHECK: runtime-identity-separate=PASS")
    print("ISSUE47_WP3B_PROVENANCE_CHARACTERIZATION: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
