"""Accuracy metric computations for simulation evaluation."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from ..stats_builder import build_accuracy_stats
from ...models.stats import AccuracyStats


def build_jacobian_accuracy_stats(
    jacobian: Mapping[str, Any] | None,
    *,
    matrix_comparisons: Iterable[Mapping[str, Any]] = (),
) -> AccuracyStats | None:
    """Map shared assembled-vs-FD Jacobian facts without producer policy."""

    tests = jacobian.get("tests", ()) if isinstance(jacobian, Mapping) else ()
    return build_accuracy_stats(
        jacobian_comparisons=tests,
        matrix_comparisons=matrix_comparisons,
    )


def self_test() -> int:
    try:
        accuracy = build_jacobian_accuracy_stats(
            {
                "tests": [
                    {
                        "relative_frobenius_error": 2.0e-9,
                        "absolute_frobenius_error": 2.0e-8,
                    }
                ]
            },
            matrix_comparisons=(
                {
                    "name": "thresholded_jacobian_difference",
                    "threshold": 1.0e-6,
                    "structural_entry_count": 2,
                    "nonzero_thresholded_entry_count": 1,
                },
            ),
        )
        if accuracy is None or len(accuracy.matrix_errors) != 2:
            raise AssertionError("Jacobian Accuracy mapping did not preserve both surfaces")
        jacobian_error, matrix_error = accuracy.matrix_errors
        if (
            jacobian_error.name != "jacobian_fd"
            or jacobian_error.error.relative_error != 2.0e-9
            or jacobian_error.error.absolute_error != 2.0e-8
            or jacobian_error.error.norm_type != "Frobenius"
            or jacobian_error.error.reference_id != "finite_difference_jacobian"
            or matrix_error.name != "thresholded_jacobian_difference"
            or matrix_error.threshold != 1.0e-6
            or matrix_error.structural_entry_count != 2
            or matrix_error.nonzero_thresholded_entry_count != 1
        ):
            raise AssertionError("Jacobian Accuracy semantics drifted")
        if build_jacobian_accuracy_stats(None) is not None:
            raise AssertionError("empty Jacobian facts invented AccuracyStats")
    except Exception as exc:
        print(f"QPX_JACOBIAN_ACCURACY_MAPPING_SELFTEST: FAIL ({exc})")
        return 1

    print("QPX_JACOBIAN_ACCURACY_MAPPING_SELFTEST: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(self_test())
