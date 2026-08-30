#!/usr/bin/env python3
"""WP-3B test-only characterization of Issue46 framework-control provenance debt."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness import augmented_jacobian_localization as loc


REFERENCE_REVISION = "9f388366ccf"


def main() -> int:
    try:
        report = loc.audit_framework_control_structure(
            loc.build_framework_control_input()
        )
        if report.get("status") != "PASS":
            raise AssertionError("framework-control structure is not PASS")

        source = report.get("source_contract", {})
        if source.get("moose_commit") != REFERENCE_REVISION:
            raise AssertionError(
                "pre-refactor reference revision is not present under the expected ambiguous key"
            )
        if "reference_source" in source:
            raise AssertionError(
                "reference_source already exists; WP-3B baseline is no longer the pre-refactor state"
            )
        if "runtime_identity" in source:
            raise AssertionError(
                "runtime_identity already exists; WP-3B baseline is no longer the pre-refactor state"
            )
    except Exception as exc:
        print(f"ISSUE47_WP3B_PROVENANCE_CHARACTERIZATION: FAIL ({exc})")
        return 1

    print("ISSUE47_WP3B_PROVENANCE_CHECK: framework-control-structure=PASS")
    print(
        "ISSUE47_WP3B_PROVENANCE_CHECK: ambiguous-moose-commit-reference=CHARACTERIZED"
    )
    print("ISSUE47_WP3B_PROVENANCE_CHECK: runtime-identity-separate=MISSING_AS_EXPECTED")
    print("ISSUE47_WP3B_PROVENANCE_CHARACTERIZATION: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
