"""Accuracy metric mappings for simulation evaluation."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from .._coerce import optional_float, optional_int
from ...models.stats import (
    AccuracyStats,
    ErrorStats,
    InvariantErrorStats,
    MatrixBlockErrorStats,
    MatrixEntryErrorStats,
    MatrixErrorStats,
    ReferenceErrorStats,
)


def _error_from_mapping(
    row: Mapping[str, Any],
    *,
    relative_keys: tuple[str, ...] = ("relative_error",),
    absolute_keys: tuple[str, ...] = ("absolute_error",),
    norm_type: str | None = None,
    reference_id: str | None = None,
) -> ErrorStats:
    relative = next(
        (
            value
            for key in relative_keys
            if (value := optional_float(row.get(key))) is not None
        ),
        None,
    )
    absolute = next(
        (
            value
            for key in absolute_keys
            if (value := optional_float(row.get(key))) is not None
        ),
        None,
    )
    return ErrorStats(
        absolute_error=absolute,
        relative_error=relative,
        norm_type=norm_type,
        reference_id=reference_id,
    )


def _matrix_blocks(value: Any) -> tuple[MatrixBlockErrorStats, ...]:
    if isinstance(value, Mapping):
        rows = value.values()
    elif isinstance(value, list):
        rows = value
    else:
        return ()
    out: list[MatrixBlockErrorStats] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        row_var = row.get("row_variable")
        col_var = row.get("col_variable")
        count = optional_int(
            row.get("count")
            if row.get("count") is not None
            else row.get("entry_count")
        )
        if not isinstance(row_var, str) or not isinstance(col_var, str) or count is None:
            continue
        out.append(
            MatrixBlockErrorStats(
                row_variable=row_var,
                col_variable=col_var,
                entry_count=count,
                l2_difference=optional_float(row.get("l2_difference")),
                max_abs_difference=optional_float(row.get("max_abs_difference")),
                energy_fraction=optional_float(row.get("energy_fraction")),
                sum_squared_difference=optional_float(
                    row.get("sum_squared_difference")
                ),
            )
        )
    return tuple(out)


def _matrix_entries(value: Any) -> tuple[MatrixEntryErrorStats, ...]:
    if not isinstance(value, list):
        return ()
    out: list[MatrixEntryErrorStats] = []
    for row in value:
        if not isinstance(row, Mapping):
            continue
        r = optional_int(row.get("row"))
        c = optional_int(row.get("col"))
        difference = optional_float(
            row.get("value")
            if row.get("value") is not None
            else row.get("difference")
        )
        if r is None or c is None or difference is None:
            continue
        out.append(
            MatrixEntryErrorStats(
                row=r,
                col=c,
                difference=difference,
                row_variable=row.get("row_variable")
                if isinstance(row.get("row_variable"), str)
                else None,
                col_variable=row.get("col_variable")
                if isinstance(row.get("col_variable"), str)
                else None,
            )
        )
    return tuple(out)


def build_accuracy_stats(
    *,
    jacobian_comparisons: Iterable[Mapping[str, Any]] = (),
    reference_comparisons: Iterable[Mapping[str, Any]] = (),
    invariants: Iterable[Mapping[str, Any]] = (),
    matrix_comparisons: Iterable[Mapping[str, Any]] = (),
) -> AccuracyStats | None:
    """Map existing reference/invariant/Jacobian facts without acceptance policy."""

    matrix_errors: list[MatrixErrorStats] = []
    for index, row in enumerate(jacobian_comparisons):
        if not isinstance(row, Mapping):
            continue
        matrix_errors.append(
            MatrixErrorStats(
                name="jacobian_fd",
                error=_error_from_mapping(
                    row,
                    relative_keys=("relative_frobenius_error",),
                    absolute_keys=("absolute_frobenius_error",),
                    norm_type="Frobenius",
                    reference_id="finite_difference_jacobian",
                ),
                comparison_index=index,
            )
        )

    reference_errors: list[ReferenceErrorStats] = []
    for row in reference_comparisons:
        if not isinstance(row, Mapping):
            continue
        name = row.get("name") if isinstance(row.get("name"), str) else row.get("key")
        if not isinstance(name, str):
            continue
        observed = optional_float(
            row.get("observed_value")
            if row.get("observed_value") is not None
            else row.get("candidate")
        )
        reference = optional_float(
            row.get("reference_value")
            if row.get("reference_value") is not None
            else row.get("legacy")
        )
        reference_errors.append(
            ReferenceErrorStats(
                name=name,
                error=_error_from_mapping(
                    row,
                    reference_id=row.get("reference_id")
                    if isinstance(row.get("reference_id"), str)
                    else None,
                ),
                observed_value=observed,
                reference_value=reference,
            )
        )

    invariant_errors: list[InvariantErrorStats] = []
    for row in invariants:
        if not isinstance(row, Mapping) or not isinstance(row.get("name"), str):
            continue
        invariant_errors.append(
            InvariantErrorStats(
                name=row["name"],
                error=_error_from_mapping(
                    row,
                    reference_id=row.get("reference_id")
                    if isinstance(row.get("reference_id"), str)
                    else None,
                ),
                observed_value=optional_float(row.get("observed_value")),
                reference_value=optional_float(row.get("reference_value")),
            )
        )

    for index, row in enumerate(matrix_comparisons):
        if not isinstance(row, Mapping):
            continue
        name = (
            row.get("name")
            if isinstance(row.get("name"), str)
            else "matrix_difference"
        )
        matrix_errors.append(
            MatrixErrorStats(
                name=name,
                error=_error_from_mapping(
                    row,
                    relative_keys=("relative_error", "relative_frobenius_error"),
                    absolute_keys=("absolute_error", "absolute_frobenius_error"),
                    norm_type=row.get("norm_type")
                    if isinstance(row.get("norm_type"), str)
                    else None,
                    reference_id=row.get("reference_id")
                    if isinstance(row.get("reference_id"), str)
                    else None,
                ),
                threshold=optional_float(row.get("threshold")),
                structural_entry_count=optional_int(row.get("structural_entry_count")),
                nonzero_thresholded_entry_count=optional_int(
                    row.get("nonzero_thresholded_entry_count")
                ),
                thresholded_l2_difference=optional_float(
                    row.get("thresholded_l2_difference")
                ),
                blocks=_matrix_blocks(row.get("blocks")),
                comparison_index=optional_int(row.get("comparison_index"))
                if row.get("comparison_index") is not None
                else index,
                entries=_matrix_entries(row.get("entries")),
                section_observed=row.get("section_observed")
                if isinstance(row.get("section_observed"), bool)
                else None,
                mapped_entry_count=optional_int(row.get("mapped_entry_count")),
            )
        )

    if not matrix_errors and not reference_errors and not invariant_errors:
        return None
    return AccuracyStats(
        invariant_errors=tuple(invariant_errors),
        matrix_errors=tuple(matrix_errors),
        reference_errors=tuple(reference_errors),
    )


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
        accuracy = build_accuracy_stats(
            jacobian_comparisons=(
                {
                    "relative_frobenius_error": 2.0e-9,
                    "absolute_frobenius_error": 2.0e-8,
                },
            ),
            reference_comparisons=(
                {
                    "key": "Dmix_A_O2",
                    "candidate": 1.01,
                    "legacy": 1.00,
                    "relative_error": 0.01,
                },
            ),
            invariants=(
                {
                    "name": "electron_inventory",
                    "observed_value": 10.0,
                    "reference_value": 10.0,
                    "relative_error": 0.0,
                },
            ),
            matrix_comparisons=(
                {
                    "name": "thresholded_jacobian_difference",
                    "threshold": 1.0e-6,
                    "structural_entry_count": 2,
                    "nonzero_thresholded_entry_count": 1,
                    "thresholded_l2_difference": 0.25,
                    "entries": [
                        {
                            "row": 1,
                            "col": 2,
                            "value": 0.25,
                            "row_variable": "u",
                            "col_variable": "v",
                        }
                    ],
                    "blocks": {
                        "u->v": {
                            "row_variable": "u",
                            "col_variable": "v",
                            "count": 1,
                            "sum_squared_difference": 0.0625,
                            "max_abs_difference": 0.25,
                            "l2_difference": 0.25,
                        }
                    },
                },
            ),
        )
        if accuracy is None:
            raise AssertionError("Accuracy mapping returned None")
        if len(accuracy.matrix_errors) != 2:
            raise AssertionError("Accuracy mapping lost matrix comparison surfaces")
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
            or matrix_error.thresholded_l2_difference != 0.25
            or matrix_error.blocks[0].sum_squared_difference != 0.0625
            or matrix_error.entries[0].difference != 0.25
        ):
            raise AssertionError("Accuracy matrix semantics drifted")
        if accuracy.reference_errors[0].observed_value != 1.01:
            raise AssertionError("Accuracy reference semantics drifted")
        if accuracy.invariant_errors[0].observed_value != 10.0:
            raise AssertionError("Accuracy invariant semantics drifted")

        jacobian_only = build_jacobian_accuracy_stats(
            {
                "tests": [
                    {
                        "relative_frobenius_error": 2.0e-9,
                        "absolute_frobenius_error": 2.0e-8,
                    }
                ]
            }
        )
        if jacobian_only is None or len(jacobian_only.matrix_errors) != 1:
            raise AssertionError("Jacobian Accuracy helper semantics drifted")
        if build_jacobian_accuracy_stats(None) is not None:
            raise AssertionError("empty Jacobian facts invented AccuracyStats")
        if build_accuracy_stats() is not None:
            raise AssertionError("empty Accuracy facts invented AccuracyStats")
    except Exception as exc:
        print(f"QPX_ACCURACY_STATS_MAPPING_SELFTEST: FAIL ({exc})")
        return 1

    print("QPX_ACCURACY_STATS_MAPPING_SELFTEST: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(self_test())
