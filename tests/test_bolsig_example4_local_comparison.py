"""Synthetic metric/contract controls for the private Example4 comparison runner."""
from pathlib import Path

import pytest

from physics_app.ci.bolsig_example4_local_comparison import (
    NativeProcessAuditHold,
    compare_printed_eepf,
)


def test_identical_printed_eepf_has_zero_weighted_l1() -> None:
    edges = [0.0, 1.0, 2.0, 3.0]
    cell_f0 = [1.0, 2.0, 3.0]
    native = [(0.2, 1.0), (0.8, 1.0), (1.2, 2.0),
              (1.8, 2.0), (2.2, 3.0), (2.8, 3.0)]
    result = compare_printed_eepf(native, edges, cell_f0)
    assert result["printed_eepf_weighted_l1"] == 0.0
    assert result["reference_sample_count"] == len(native)


def test_printed_eepf_comparison_detects_shape_mismatch() -> None:
    original = [(0.1, 1.0), (1.1, 2.0), (2.1, 3.0)]
    result = compare_printed_eepf(original, [0, 1, 2, 3], [1, 1, 1])
    assert result["printed_eepf_weighted_l1"] > 0.0
    with pytest.raises(NativeProcessAuditHold, match="does not cover"):
        compare_printed_eepf(original, [0, 1, 2], [1, 2])
    with pytest.raises(NativeProcessAuditHold, match="invalid candidate"):
        compare_printed_eepf(original, [0, 2, 1, 3], [1, 2, 3])
    with pytest.raises(NativeProcessAuditHold, match="invalid candidate"):
        compare_printed_eepf(original, [0, 1, 2, 3], [1, -1, 3])
