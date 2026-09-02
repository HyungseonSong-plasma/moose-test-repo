from __future__ import annotations

from experiments.Issue92_r3_nonlinear.evr3 import (
    _load_reference,
    _plasma_cell_count_v41,
    _with_electron_fallback,
)


def test_evr3_starts_from_preserved_b2_reference() -> None:
    ref = _load_reference()
    assert ref.parse_complete
    assert ref.two_cycle
    assert ref.dominant_groups == ["ELECTRON"] * 4
    assert ref.global_residuals == [0.983996, 1.03367, 0.947657, 1.03367]


def test_evr3_uses_electron_residual_when_framework_global_marker_is_absent() -> None:
    log = """|residual|_2 of individual variables:
  u: 1.0e-4
  n_e: 9.8e-1
|residual|_2 of individual variables:
  u: 1.0e-8
  n_e: 1.03
|residual|_2 of individual variables:
  u: 1.0e-12
  n_e: 9.5e-1
|residual|_2 of individual variables:
  u: 1.0e-14
  n_e: 1.03
"""
    a = _with_electron_fallback(log)
    assert a.parse_complete
    assert a.global_residuals == [0.98, 1.03, 0.95, 1.03]
    assert a.two_cycle


def test_evr3_counts_gmsh41_plasma_cells_for_cost_guard() -> None:
    mesh = """$PhysicalNames
1
2 53 "plasma"
$EndPhysicalNames
$Entities
0 0 1 0
2 0 0 0 1 1 0 1 53 0
$EndEntities
$Elements
2 3 1 3
1 1 1 1
1 1 2
2 2 2 2
2 1 2 3
3 1 3 4
$EndElements
"""
    assert _plasma_cell_count_v41(mesh) == 2
