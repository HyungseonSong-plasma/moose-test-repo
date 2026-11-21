"""Guard MOOSE LinearInterpolation reuse in the canonical EI rate material.

Python value checks do not replace exact-revision MOOSE compilation or AD/Jacobian
and full solver parity; those remain independent scientific gates.
"""
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "physics_app"
SOURCE = APP / "src/materials/EIRateCoefMaterial.C"
HEADER = APP / "include/materials/EIRateCoefMaterial.h"
TABLES = ("o2_elastic.txt", "o_elastic.txt", "o_excitation_1s.txt")


def test_linear_interpolation_preserves_strict_ei_rate_contract():
    header = HEADER.read_text()
    source = SOURCE.read_text()
    assert '#include "LinearInterpolation.h"' in header
    assert "LinearInterpolation _rate_interpolation;" in header
    assert "_rate_interpolation(_table.coordinate(), _table.values(0))" in source
    assert "return _rate_interpolation.sample(coordinate);" in source
    assert "lowerBracket(raw)" not in source
    assert "if (!std::isfinite(raw))" in source
    assert "requires finite mean electron energy" in source
    assert "if (raw < x.front() || raw > x.back())" in source
    assert "strict Stage-4 policy forbids clamp/floor" in source
    assert "if (raw == x.front())\n    return y.front();" in source
    assert "if (raw == x.back())\n    return y.back();" in source
    assert source.index("if (!std::isfinite(raw))") < source.index(
        "return _rate_interpolation.sample(coordinate);"
    )
    assert source.index("if (raw == x.back())") < source.index(
        "return _rate_interpolation.sample(coordinate);"
    )
    assert 'registerMooseObject("PhysicsApp", EIRateCoefMaterial);' in source
    assert "return k_raw * (n_e / N_A) * c_target;" in source


@pytest.mark.parametrize("name", TABLES)
def test_frozen_100_point_ei_tables_piecewise_linear_value_equivalence(name):
    """Compare old/MOOSE linear expressions at interior values and near knots."""
    table = APP / "data/electron_impact" / name
    rows = [
        tuple(map(float, line.split()))
        for line in table.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert len(rows) == 100
    for (x0, y0), (x1, y1) in zip(rows, rows[1:]):
        assert x1 > x0
        for fraction in (0.0, 1e-9, 0.25, 0.5, 0.75, 1 - 1e-9):
            energy = x0 + (x1 - x0) * fraction
            old_value = y0 + (energy - x0) * (y1 - y0) / (x1 - x0)
            moose_linear_value = y0 + (y1 - y0) * (energy - x0) / (x1 - x0)
            assert moose_linear_value == pytest.approx(
                old_value, rel=1e-14, abs=0.0
            )
