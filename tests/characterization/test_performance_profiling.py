from __future__ import annotations

import pytest

from qpx_harness.performance.profiling import build_bounded_executioner_overlay


def test_bounded_profile_overlay_defaults_to_no_numerical_change() -> None:
    assert build_bounded_executioner_overlay() == ""


def test_bounded_profile_overlay_is_explicit_and_minimal() -> None:
    assert build_bounded_executioner_overlay(
        nl_max_its=3,
        abort_on_solve_fail=True,
    ) == (
        "[Executioner]\n"
        "  nl_max_its = 3\n"
        "  abort_on_solve_fail = true\n"
        "[]\n"
    )


def test_bounded_profile_overlay_can_limit_iterations_without_abort() -> None:
    assert build_bounded_executioner_overlay(nl_max_its=2) == (
        "[Executioner]\n"
        "  nl_max_its = 2\n"
        "[]\n"
    )


def test_bounded_profile_rejects_nonpositive_iteration_cap() -> None:
    with pytest.raises(ValueError, match="positive integer"):
        build_bounded_executioner_overlay(nl_max_its=0)
