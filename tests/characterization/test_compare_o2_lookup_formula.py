"""Rate-benchmark validation uses synthetic rate values, never actual Phelps data."""
from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import pytest

MODULE = Path(__file__).resolve().parents[2] / (
    "experiments/Issue395_powered_chemistry_ladder/compare_o2_lookup_formula.py"
)
spec = importlib.util.spec_from_file_location("o2_formula_benchmark", MODULE)
assert spec and spec.loader
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_reference_formula_pins_407_and_412_only() -> None:
    assert set(m.FORMULAS) == {407, 412}
    assert math.isclose(m.reference_k(407, 3.), 1.37e-15 * math.exp(-2.14/3.))
    assert math.isclose(m.reference_k(412, 3.), 1.41e-15 * 3.**(-.22) * math.exp(-2.98/3.))
    for forbidden in (401, 411, 413):
        with pytest.raises(ValueError, match="only for 407 and 412"):
            m.reference_k(forbidden, 3.)


def test_lookups_compared_not_replaced() -> None:
    k407 = m.reference_k(407, 2.0)
    k412 = m.reference_k(412, 3.0)
    result = m.compare([
        {"reaction_id": "407", "Te_eV": "2", "k_lookup_m3_s": str(1.1*k407)},
        {"reaction_id": "412", "Te_eV": "3", "k_lookup_m3_s": str(.9*k412)},
    ])
    assert [r["reaction_id"] for r in result] == [407, 412]
    assert result[0]["relative_deviation"] == pytest.approx(.1)
    assert result[1]["relative_deviation"] == pytest.approx(-.1)
    assert all("comparison only" in r["note"] for r in result)


def test_benchmark_fail_closed_out_of_range_and_duplicate() -> None:
    with pytest.raises(ValueError, match="1..7 eV"):
        m.reference_k(407, .5)
    with pytest.raises(ValueError, match="1..7 eV"):
        m.reference_k(407, 7.1)
    for bad in ("NaN", "-1", "inf"):
        with pytest.raises(ValueError):
            m.compare([{"reaction_id":"407", "Te_eV":"3", "k_lookup_m3_s":bad}])
    row = {"reaction_id":"412", "Te_eV":"2.0", "k_lookup_m3_s":"1e-15"}
    with pytest.raises(ValueError, match="Duplicate"):
        m.compare([row, row])
    with pytest.raises(ValueError, match="No scientifically matched"):
        m.compare([{"reaction_id":"411", "Te_eV":"3", "k_lookup_m3_s":"1e-15"}])
