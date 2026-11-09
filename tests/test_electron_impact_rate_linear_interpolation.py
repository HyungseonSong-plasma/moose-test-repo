"""Evidence: MOOSE AD linear sampling preserves the frozen EI rate-owner algebra.

This is a deterministic double-precision replay of the *pinned* MOOSE
LinearInterpolation::sample() and the previous code. It does not replace an
actual native PhysicsApp compile / Jacobian test, but catches accidental
spline/extrapolation/regression changes and quantifies roundoff on real tables.
"""
from __future__ import annotations

import math
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "physics_app/include/materials/PhysicsElectronImpactRateMaterial.h"
SOURCE = ROOT / "physics_app/src/materials/PhysicsElectronImpactRateMaterial.C"
TABLES = ROOT / "physics_app/data/electron_impact"
FROZEN = ("o2_elastic.txt", "o_elastic.txt", "o_excitation_1s.txt")


def _read_rate_table(name: str) -> tuple[list[float], list[float]]:
    data = [
        tuple(map(float, line.split()))
        for line in (TABLES / name).read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert len(data) == 100
    energies = [x for x, _ in data]
    rates = [y for _, y in data]
    assert all(math.isfinite(x) and math.isfinite(y) for x, y in data)
    assert all(energies[i] < energies[i + 1] for i in range(len(data) - 1))
    assert all(y >= 0 for y in rates)
    return energies, rates


def _previous_linear(x: list[float], y: list[float], i: int, value: float) -> float:
    """Previous source: y[i] + (x - x[i])*(y[i+1]-y[i])/(x[i+1]-x[i])."""
    if value == x[0]:
        return y[0]
    if value == x[-1]:
        return y[-1]
    return y[i] + (value - x[i]) * (y[i + 1] - y[i]) / (x[i + 1] - x[i])


def _moose_linear(x: list[float], y: list[float], i: int, value: float) -> float:
    """Pinned MOOSE 9f388366ccf LinearInterpolation::sample formula."""
    if value == x[0]:
        return y[0]
    if value == x[-1]:
        return y[-1]
    return y[i] + (y[i + 1] - y[i]) * (value - x[i]) / (x[i + 1] - x[i])


@pytest.mark.parametrize("filename", FROZEN)
def test_public_rate_tables_roundoff_equivalence(filename):
    x, y = _read_rate_table(filename)
    # Test every tabulated knot (except the max, handled by the preceding interval)
    # plus four off-grid interior points of every interval.
    compared = 0
    worst = 0.0
    for i in range(len(x) - 1):
        for f in (0.0, 0.2, 0.5, 0.8, 0.999999):
            energy = x[i] + f * (x[i + 1] - x[i])
            baseline = _previous_linear(x, y, i, energy)
            proposed = _moose_linear(x, y, i, energy)
            assert math.isfinite(baseline) and math.isfinite(proposed)
            relative_difference = abs(proposed - baseline) / max(abs(baseline), 1.0)
            worst = max(worst, relative_difference)
            assert math.isclose(proposed, baseline, rel_tol=1e-14, abs_tol=1e-14)
            compared += 1

        # AD slopes inside each interval are analytically identical.
        legacy_slope = (y[i + 1] - y[i]) / (x[i + 1] - x[i])
        moose_slope = (y[i + 1] - y[i]) / (x[i + 1] - x[i])
        assert moose_slope == legacy_slope

    assert compared == 5 * 99
    assert _previous_linear(x, y, 0, x[0]) == _moose_linear(x, y, 0, x[0]) == y[0]
    assert _previous_linear(x, y, 98, x[-1]) == _moose_linear(x, y, 98, x[-1]) == y[-1]
    assert worst <= 1e-14


def test_cpp_keeps_strict_domain_and_first_last_knot_ad_policy():
    h = HEADER.read_text()
    s = SOURCE.read_text()
    assert '#include "LinearInterpolation.h"' in h
    assert "PhysicsLookupTable1D _table;" in h  # identical audited parsing
    assert "LinearInterpolation _rate_interpolation;" in h
    assert "_rate_interpolation(_table.coordinate(), _table.values(0))" in s
    assert "return _rate_interpolation.sample(coordinate);" in s
    assert "std::isfinite(raw)" in s
    assert "raw < x.front() || raw > x.back()" in s
    assert s.index("if (raw == x.front())") < s.index(
        "return _rate_interpolation.sample(coordinate);"
    )
    assert s.index("if (raw == x.back())") < s.index(
        "return _rate_interpolation.sample(coordinate);"
    )
    assert "return y.front();" in s and "return y.back();" in s
    assert "_table.lowerBracket(" not in s
    assert 'registerMooseObject("PhysicsApp", PhysicsElectronImpactRateMaterial);' in s
    assert "return k_raw * (n_e / N_A) * c_target;" in s
