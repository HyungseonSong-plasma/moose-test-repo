#!/usr/bin/env python3
"""Gate the Issue-236 A/B/C transferred-mirror boundary discriminator."""
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


def _greater(a: Any, b: Any, *, tol: float = 1.0e-15) -> bool:
    try:
        return float(a) > float(b) + tol
    except (TypeError, ValueError):
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("two_term_summary", type=Path)
    parser.add_argument("parent_one_term_summary", type=Path)
    parser.add_argument("mirrors_one_term_summary", type=Path)
    args = parser.parse_args()

    a = _disc(_load(args.two_term_summary))
    b = _disc(_load(args.parent_one_term_summary))
    c = _disc(_load(args.mirrors_one_term_summary))

    checks = {
        # A: baseline fails in the parent because the transferred parent mirror
        # reconstructs a negative full-boundary FaceArg from positive cell DOFs.
        "a_mode_two_term": a.get("mode") == "two_term",
        "a_parent_cell_positive": a.get("parent_cell_positive") is True,
        "a_parent_face_negative": a.get("parent_face_negative") is True,
        "a_snapshot_face_negative": a.get("snapshot_face_negative") is True,
        "a_negative_signature_present": (
            a.get("negative_heavy_transport_signature_present") is True
        ),
        # B: parent one-term removes the parent failure, but the same two-term
        # reconstruction reappears after n_e is copied to child frozen mirror.
        "b_mode_parent_one_term": b.get("mode") == "one_term",
        "b_parent_cell_positive": b.get("parent_cell_positive") is True,
        "b_parent_face_nonnegative": b.get("parent_face_nonnegative") is True,
        "b_snapshot_face_negative_control_retained": (
            b.get("snapshot_face_negative") is True
        ),
        "b_child_frozen_face_negative_observed": (
            b.get("child_frozen_face_negative_observed") is True
        ),
        "b_negative_signature_present": (
            b.get("negative_heavy_transport_signature_present") is True
        ),
        "b_progresses_beyond_a_child_time": _greater(
            b.get("child_max_accepted_time_s"), a.get("child_max_accepted_time_s")
        ),
        # C: only transfer/frozen mirrors use one-term; live solved n_e remains
        # two-term.  The old heavy_transport negativity must disappear and the
        # run must progress beyond B's prior child failure point.
        "c_mode_mirrors_one_term": c.get("mode") == "mirrors_one_term",
        "c_parent_cell_positive": c.get("parent_cell_positive") is True,
        "c_parent_face_nonnegative": c.get("parent_face_nonnegative") is True,
        "c_snapshot_face_negative_control_retained": (
            c.get("snapshot_face_negative") is True
        ),
        "c_child_frozen_face_nonnegative_observed": (
            c.get("child_frozen_face_nonnegative_observed") is True
        ),
        "c_negative_signature_removed": (
            c.get("negative_heavy_transport_signature_present") is False
        ),
        "c_progresses_beyond_b_child_time": _greater(
            c.get("child_max_accepted_time_s"), b.get("child_max_accepted_time_s")
        ),
        # Same first parent transfer state and immutable two-term snapshot
        # prove A/B/C differ by representation policy, not transfer payload.
        "same_first_transferred_cell_state_a_b": _close(
            a.get("cell_ne_min"), b.get("cell_ne_min")
        ),
        "same_first_transferred_cell_state_a_c": _close(
            a.get("cell_ne_min"), c.get("cell_ne_min")
        ),
        "same_two_term_snapshot_a_b": _close(
            a.get("snapshot_face_ne_min"), b.get("snapshot_face_ne_min")
        ),
        "same_two_term_snapshot_a_c": _close(
            a.get("snapshot_face_ne_min"), c.get("snapshot_face_ne_min")
        ),
    }

    failed = sorted(name for name, ok in checks.items() if not ok)
    result = {
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "failed_checks": failed,
        "two_term": a,
        "parent_one_term": b,
        "mirrors_one_term": c,
        "conclusion": (
            "positive transferred cell state is unchanged across A/B/C; two-term boundary "
            "reconstruction first fails on the parent mirror, then migrates to the child "
            "frozen mirror when only the parent is one-term, and disappears when both transfer "
            "mirrors are one-term while live solved n_e remains unchanged"
            if not failed
            else "A/B/C boundary discriminator is incomplete or inconsistent"
        ),
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
