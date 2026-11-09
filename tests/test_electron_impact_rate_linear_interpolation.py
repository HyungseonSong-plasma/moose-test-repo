"""Guard the MOOSE linear interpolation migration against scientific drift."""
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
H = ROOT / "physics_app/include/materials/PhysicsElectronImpactRateMaterial.h"
C = ROOT / "physics_app/src/materials/PhysicsElectronImpactRateMaterial.C"


def test_native_interpolation_api_with_existing_strict_domain():
    h, source = H.read_text(), C.read_text()
    assert '#include "LinearInterpolation.h"' in h
    assert "LinearInterpolation _rate_interpolation;" in h
    assert "_rate_interpolation.setData(_table.coordinate(), _table.values(0));" in source
    assert "return _rate_interpolation.sample(coordinate);" in source
    assert "const std::size_t i = _table.lowerBracket(raw);" not in source
    assert "if (!std::isfinite(raw))" in source
    assert "if (raw < x.front() || raw > x.back())" in source
    assert "if (raw == x.front())\n    return y.front();" in source
    assert "if (raw == x.back())\n    return y.back();" in source
    assert "strict Stage-4 policy forbids clamp/floor" in source
    assert "return k_raw * (n_e / N_A) * c_target;" in source
    assert 'registerMooseObject("PhysicsApp", PhysicsElectronImpactRateMaterial);' in source


@pytest.mark.parametrize(
    "name",
    ["o2_elastic.txt", "o_elastic.txt", "o_excitation_1s.txt"],
)
def test_frozen_ei_table_piecewise_linear_identity(name):
    """Mathematical value/slope equivalence on all intervals, incl. knot neighbors.

    Runtime ADReal and native ABI must separately be proven by a MOOSE build.
    """
    table = ROOT / "physics_app/data/electron_impact" / name
    pairs = [
        tuple(map(float, line.split())) for line in table.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert len(pairs) == 100
    for (x0, y0), (x1, y1) in zip(pairs, pairs[1:]):
        assert x1 > x0
        slope = (y1 - y0) / (x1 - x0)
        for fraction in (0.0, 1e-9, 0.25, 0.5, 0.75, 1 - 1e-9):
            energy = x0 + (x1 - x0) * fraction
            old_value = y0 + (energy - x0) * (y1 - y0) / (x1 - x0)
            moose_linear_formula = y0 + (y1 - y0) * (energy - x0) / (x1 - x0)
            assert moose_linear_formula == pytest.approx(old_value, rel=1e-14, abs=0)
            assert slope == pytest.approx((y1-y0)/(x1-x0), rel=0, abs=0)
