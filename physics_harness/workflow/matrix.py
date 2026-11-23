"""Deterministic and bounded GitHub Actions case matrices."""
from __future__ import annotations

import json


def build_matrix(spec) -> dict[str, list[dict[str, str]]]:
    # No Cartesian product: every case maps to exactly one independent runner.
    return {"include": [{"case": case.id} for case in spec.cases]}


def matrix_json(spec) -> str:
    return json.dumps(build_matrix(spec), separators=(",", ":"), sort_keys=True)


def case_ids(spec) -> tuple[str, ...]:
    return tuple(case.id for case in spec.cases)
