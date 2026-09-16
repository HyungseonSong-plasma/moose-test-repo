#!/usr/bin/env python3
"""Gate the Issue-236 two-term vs one-term boundary-face discriminator."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


def _load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _disc(summary: dict[str, Any]) -> dict[str, Any]:
    return summary.get("analysis", {}).get("boundary_face_discriminator", {})


def _close(a: Any, b: Any, *, rel: float = 1.0e-12, abs_tol: float = 1.0e-14) -> bool:
    try:
        return math.isclose(float(a), float(b), rel_tol=rel, abs_tol=abs_tol)
    except (TypeError, ValueError):
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("two_term_summary", type=Path)
    parser.add_argument("one_term_summary", type=Path)
    args = parser.parse_args()

    a = _disc(_load(args.two_term_summary))
    b = _disc(_load(args.one_term_summary))

    checks = {
        "a_mode_two_term": a.get("mode") == "two_term",
        "a_cell_positive": a.get("cell_positive") is True,
        "a_face_negative": a.get("face_negative") is True,
        "a_snapshot_cell_positive": a.get("snapshot_cell_positive") is True,
        "a_snapshot_face_negative": a.get("snapshot_face_negative") is True,
        "a_negative_heavy_transport_signature_present": (
            a.get("negative_heavy_transport_signature_present") is True
        ),
        "b_mode_one_term": b.get("mode") == "one_term",
        "b_cell_positive": b.get("cell_positive") is True,
        "b_face_nonnegative": b.get("face_nonnegative") is True,
        "b_snapshot_cell_positive": b.get("snapshot_cell_positive") is True,
        "b_snapshot_face_negative_control_retained": (
            b.get("snapshot_face_negative") is True
        ),
        "b_negative_heavy_transport_signature_removed": (
            b.get("negative_heavy_transport_signature_present") is False
        ),
        "same_transferred_cell_state": _close(a.get("cell_ne_min"), b.get("cell_ne_min")),
        "same_two_term_snapshot_control": _close(
            a.get("snapshot_face_ne_min"), b.get("snapshot_face_ne_min")
        ),
    }

    failed = sorted(name for name, ok in checks.items() if not ok)
    result = {
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "failed_checks": failed,
        "two_term": a,
        "one_term": b,
        "conclusion": (
            "transferred cell state is positive and unchanged; two-term FV boundary reconstruction "
            "creates the negative operational face value, while one-term evaluation removes that "
            "face negativity and the matching heavy-transport failure signature"
            if not failed
            else "boundary A/B discriminator is incomplete or inconsistent"
        ),
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
