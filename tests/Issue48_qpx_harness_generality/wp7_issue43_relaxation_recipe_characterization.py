#!/usr/bin/env python3
"""P0 characterization for the Issue43 fast-relaxation recipe extraction."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness import fast_plasma_relaxation as legacy
from recipes import issue43_fast_relaxation as recipe


def _fixture() -> str:
    return """[Variables]
  [n_e]
    type = MooseVariableFVReal
    initial_condition = 1e16
    block = plasma
  []
[]
[Functions]
  [phi_prescribed]
    type = ParsedFunction
    expression = '-0.01*x'
  []
[]
[FunctorMaterials]
  [electron_constants]
    type = ADGenericFunctorMaterial
    prop_names = 'mean_en p_abs T_g carrier_one'
    prop_values = '5.73276 1.33322 600.0 1.0'
    block = plasma
  []
[]
[FVKernels]
  [drift]
    type = QPXFVElectrostaticDrift
    variable = n_e
    potential = phi_prescribed
    mobility = electron_mobility
    carrier = carrier_one
    charge_number = -1
    block = plasma
  []
[]
[Postprocessors]
  [n_min]
    type = ADElementExtremeFunctorValue
    functor = n_e
    value_type = min
    block = plasma
  []
[]
[Executioner]
  type = Transient
  dt = 1e-8
  end_time = 2e-8
  compute_scaling_once = true
[]
[Outputs]
  csv = true
[]
"""


def _synthetic_rows() -> list[dict[str, float]]:
    rows: list[dict[str, float]] = []
    for i in range(1, 6):
        decay = 10.0 ** (-i)
        rows.append(
            {
                "time": i * 1.0e-10,
                "n_min": 1.0e16 * (1.0 - 1.0e-6 * decay),
                "n_max": 1.0e16 * (1.0 + 1.0e-6 * decay),
                "inventory": 1.0e16,
                "domain_volume": 1.0,
                "r43_n_l2": 1.0e16 * (1.0 + 1.0e-7 * decay),
                "r43_phi_l2": decay,
                "r43_phi_min": -decay,
                "r43_phi_max": decay,
                "r43_phi_integral": 0.0,
                "r43_charge_integral": 0.0,
                "r43_background_inventory": 1.0e16,
                "r43_charge_min": -legacy.E_CHARGE * 1.0e10 * decay,
                "r43_charge_max": legacy.E_CHARGE * 1.0e10 * decay,
            }
        )
    return rows


def _check_builder_equivalence() -> None:
    kwargs = {
        "gas_temperature": 300.0,
        "electron_density": 1.0e16,
        "dt": 1.0e-10,
        "end_time": 2.0e-9,
        "radial_span": 0.243,
    }
    old_text, old_meta = legacy.build_fast_input(_fixture(), **kwargs)
    new_text, new_meta = recipe.build_fast_input(_fixture(), **kwargs)
    if new_text != old_text:
        raise AssertionError("Issue43 relaxation input text drift")
    if new_meta != old_meta:
        raise AssertionError("Issue43 relaxation construction metadata drift")

    for bad_kwargs in (
        kwargs | {"dt": 0.0},
        kwargs | {"end_time": 0.0},
        kwargs | {"radial_span": 0.0},
    ):
        old_failed = False
        new_failed = False
        try:
            legacy.build_fast_input(_fixture(), **bad_kwargs)
        except legacy.FastPlasmaRelaxationError:
            old_failed = True
        try:
            recipe.build_fast_input(_fixture(), **bad_kwargs)
        except recipe.Issue43FastRelaxationError:
            new_failed = True
        if not old_failed or not new_failed:
            raise AssertionError("invalid construction input was not rejected equivalently")


def _check_analysis_equivalence() -> None:
    rows = _synthetic_rows()
    old = legacy.analyze_relaxation(rows, electron_density=1.0e16, relax_tol=2.0e-4)
    new = recipe.analyze_relaxation(rows, electron_density=1.0e16, relax_tol=2.0e-4)
    if new != old:
        raise AssertionError("Issue43 relaxation analysis result drift")

    bad = [dict(row) for row in rows]
    bad[-1]["inventory"] *= 1.01
    old_bad = legacy.analyze_relaxation(bad, electron_density=1.0e16)
    new_bad = recipe.analyze_relaxation(bad, electron_density=1.0e16)
    if new_bad != old_bad or new_bad["status"] != "FAIL":
        raise AssertionError("inventory-mutation analysis drift")


def _check_csv_equivalence() -> None:
    rows = _synthetic_rows()
    with tempfile.TemporaryDirectory() as tmp_name:
        root = Path(tmp_name)
        alternate = root / "alternate.csv"
        preferred = root / "input_out.csv"
        header = ",".join(recipe.REQUIRED_COLUMNS)

        def row_text(row: dict[str, float]) -> str:
            return ",".join(str(row[key]) for key in recipe.REQUIRED_COLUMNS)

        payload = header + "\n" + "\n".join(row_text(row) for row in rows) + "\n"
        alternate.write_text(payload)
        preferred.write_text(payload)

        if recipe.find_relaxation_csv(root) != legacy._find_csv(root):
            raise AssertionError("Issue43 relaxation CSV selection drift")
        old_rows = legacy._rows(preferred)
        new_rows = recipe.read_relaxation_rows(preferred)
        if new_rows != old_rows:
            raise AssertionError("Issue43 relaxation CSV parsing drift")

        preferred.unlink()
        alternate.unlink()
        old_failed = False
        new_failed = False
        try:
            legacy._find_csv(root)
        except legacy.FastPlasmaRelaxationError:
            old_failed = True
        try:
            recipe.find_relaxation_csv(root)
        except recipe.Issue43FastRelaxationError:
            new_failed = True
        if not old_failed or not new_failed:
            raise AssertionError("missing relaxation CSV was not rejected equivalently")


def _check_recipe_boundary() -> None:
    source = Path(recipe.__file__).read_text()
    for forbidden in (
        "fast_plasma_relaxation",
        "qpx_harness.runtime",
        "qpx_harness.cases",
        "electron_inventory_nullspace",
        "petsc_first_linear_diagnostic",
        "augmented_jacobian_localization",
    ):
        if forbidden in source:
            raise AssertionError(f"recipe reverse dependency leaked: {forbidden}")


def main() -> int:
    try:
        _check_builder_equivalence()
        _check_analysis_equivalence()
        _check_csv_equivalence()
        _check_recipe_boundary()
    except Exception as exc:
        print(f"ISSUE48_ISSUE43_RELAXATION_RECIPE_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE48_ISSUE43_RELAXATION_RECIPE_SELFTEST: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
