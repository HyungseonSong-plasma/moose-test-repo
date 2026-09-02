#!/usr/bin/env python3
"""WP-2 characterization for generic DOF ownership and matrix localization facts."""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness import issue46_jacobian_localization as issue46
from qpx_harness.moose import dofmap as dm
from qpx_harness.petsc import matrix as pm


def _dofmap_text() -> str:
    return json.dumps(
        {
            "ndof": 7,
            "vars": [
                {"name": "u", "subdomains": [{"id": 1, "dofs": [0, 1, 2]}]},
                {"name": "v", "subdomains": [{"id": 1, "dofs": [3, 4, 5]}]},
                {"name": "lambda", "subdomains": [{"id": 1, "dofs": []}]},
            ],
        }
    )


def _difference_log(entries: list[tuple[int, int, float]]) -> str:
    rows: dict[int, list[tuple[int, float]]] = {}
    for row, col, value in entries:
        rows.setdefault(row, []).append((col, value))
    body = []
    for row in sorted(rows):
        payload = " ".join(f"({col}, {value:.12e})" for col, value in rows[row])
        body.append(f"row {row}: {payload}")
    return (
        "Hand-coded minus finite-difference Jacobian with tolerance 1.000000000000e-07 ----------\n"
        "Mat Object: 1 MPI process\n"
        "  type: seqaij\n"
        + "\n".join(body)
        + "\nLinear solve did not converge due to DIVERGED_BREAKDOWN iterations 30\n"
    )


def _expect_error(fn, label: str) -> None:
    try:
        fn()
    except (dm.DofMapError, pm.MatrixParseError):
        return
    raise AssertionError(f"negative control unexpectedly passed: {label}")


def _check_dofmap() -> None:
    text = _dofmap_text()
    generic = dm.parse_dof_map_text(
        text,
        expected_variables=("u", "v", "lambda"),
        scalar_variables=("lambda",),
    )
    assert generic["ndof"] == 7
    assert generic["variables"]["u"] == [0, 1, 2]
    assert generic["variables"]["v"] == [3, 4, 5]
    assert generic["variables"]["lambda"] == [6]
    assert generic["owner_by_dof"][6] == "lambda"

    issue_text = issue46._synthetic_dof_map()
    semantic = issue46.parse_dof_map_text(issue_text)
    generic_issue = dm.parse_dof_map_text(
        issue_text,
        expected_variables=issue46.MAIN_VARIABLES,
        scalar_variables=issue46.SCALAR_VARIABLES,
    )
    assert generic_issue == semantic

    overlap = json.dumps(
        {
            "ndof": 2,
            "vars": [
                {"name": "u", "subdomains": [{"dofs": [0]}]},
                {"name": "v", "subdomains": [{"dofs": [0, 1]}]},
            ],
        }
    )
    _expect_error(
        lambda: dm.parse_dof_map_text(overlap, expected_variables=("u", "v")),
        "overlapping ownership",
    )


def _check_threshold_matrix() -> None:
    log = _difference_log([(0, 3, 2.0e-4), (6, 1, -3.0e-4)])
    generic = pm.parse_threshold_difference_matrix(log)
    assert generic["threshold"] == 1.0e-7
    assert generic["entries"] == [
        {"row": 0, "col": 3, "value": 2.0e-4},
        {"row": 6, "col": 1, "value": -3.0e-4},
    ]
    assert generic["section_observed"] is True

    issue_log = issue46._synthetic_localization_log([(0, 4, 2.0e-4), (4, 1, -3.0e-4)])
    assert pm.parse_threshold_difference_matrix(issue_log) == issue46.parse_threshold_difference_matrix(issue_log)
    _expect_error(lambda: pm.parse_threshold_difference_matrix("no matrix section\n"), "missing threshold section")


def _check_block_localization() -> None:
    dofmap = dm.parse_dof_map_text(
        _dofmap_text(),
        expected_variables=("u", "v", "lambda"),
        scalar_variables=("lambda",),
    )
    difference = pm.parse_threshold_difference_matrix(
        _difference_log([(0, 3, 2.0e-4), (6, 1, -3.0e-4), (2, 4, 4.0e-4)])
    )
    facts = pm.summarize_by_owner(difference, dofmap["owner_by_dof"])
    assert facts["entry_count"] == 3
    assert facts["mapped_entry_count"] == 3
    assert facts["unmapped_entries"] == []
    assert facts["blocks"]["u->v"]["count"] == 2
    assert facts["blocks"]["lambda->u"]["count"] == 1
    expected_l2 = math.sqrt((2.0e-4) ** 2 + (-3.0e-4) ** 2 + (4.0e-4) ** 2)
    assert math.isclose(facts["thresholded_l2_difference"], expected_l2, rel_tol=1e-15)

    bad = {"threshold": 1.0e-7, "entries": [{"row": 99, "col": 0, "value": 1.0}]}
    unmapped = pm.summarize_by_owner(bad, dofmap["owner_by_dof"])
    assert unmapped["mapped_entry_count"] == 0
    assert len(unmapped["unmapped_entries"]) == 1


def _check_policy_boundary() -> None:
    for rel in (
        "qpx_harness/moose/dofmap.py",
        "qpx_harness/petsc/matrix.py",
    ):
        source = (ROOT / rel).read_text()
        forbidden = (
            "ISSUE =",
            "n_e",
            "potential_plasma",
            "r45_inventory_lambda",
            "constraint_lm",
            "electron_potential",
            "DOMINANT_ENERGY_FRACTION",
            "CONSTRAINT_LM_BLOCK_MISMATCH",
            "FD_SCALING_LIMIT_SUSPECTED",
        )
        for token in forbidden:
            if token in source:
                raise AssertionError(f"scientific policy leaked into {rel}: {token}")


def main() -> int:
    try:
        _check_dofmap()
        print("ISSUE48_WP2_MATRIX_CHECK: dof-ownership=PASS")
        _check_threshold_matrix()
        print("ISSUE48_WP2_MATRIX_CHECK: threshold-matrix-parser=PASS")
        _check_block_localization()
        print("ISSUE48_WP2_MATRIX_CHECK: owner-block-statistics=PASS")
        _check_policy_boundary()
        print("ISSUE48_WP2_MATRIX_CHECK: localization-policy-boundary=PASS")
    except Exception as exc:
        print(f"ISSUE48_WP2_MATRIX_CHARACTERIZATION: FAIL ({exc})")
        return 1
    print("ISSUE48_WP2_MATRIX_CHARACTERIZATION: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
