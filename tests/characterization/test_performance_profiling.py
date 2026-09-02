from __future__ import annotations

import pytest

from qpx_harness.performance.profiling import build_bounded_runtime_overrides


def test_bounded_profile_overrides_default_to_no_numerical_change() -> None:
    assert build_bounded_runtime_overrides() == []


def test_bounded_profile_overrides_are_explicit_and_minimal() -> None:
    assert build_bounded_runtime_overrides(
        nl_max_its=3,
        abort_on_solve_fail=True,
    ) == [
        "Executioner/nl_max_its=3",
        "Executioner/abort_on_solve_fail=true",
    ]


def test_bounded_profile_rejects_nonpositive_iteration_cap() -> None:
    with pytest.raises(ValueError, match="positive integer"):
        build_bounded_runtime_overrides(nl_max_its=0)
