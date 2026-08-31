#!/usr/bin/env python3
"""P0 characterization for the Issue43 fast-relaxation recipe after v2 cutover."""
from __future__ import annotations

import inspect
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness import fast_plasma_relaxation_v2 as v2
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
                "r43_charge_min": -recipe.E_CHARGE * 1.0e10 * decay,
                "r43_charge_max": recipe.E_CHARGE * 1.0e10 * decay,
            }
        )
    return rows


def _check_builder_contract() -> None:
    kwargs = {
        "gas_temperature": 300.0,
        "electron_density": 1.0e16,
        "dt": 1.0e-10,
        "end_time": 2.0e-9,
        "radial_span": 0.243,
    }
    text, meta = recipe.build_fast_input(_fixture(), **kwargs)
    for token in (
        "potential = potential_plasma",
        "r43_positive_background",
        "r43_phi_diffusion",
        "r43_phi_charge_source",
        "r43_phi_plasma_metal",
    ):
        if token not in text:
            raise AssertionError(f"recipe construction lost {token!r}")
    if meta["dt_s"] != kwargs["dt"] or meta["end_time_s"] != kwargs["end_time"]:
        raise AssertionError("recipe construction metadata drift")

    for bad_kwargs in (
        kwargs | {"dt": 0.0},
        kwargs | {"end_time": 0.0},
        kwargs | {"radial_span": 0.0},
    ):
        try:
            recipe.build_fast_input(_fixture(), **bad_kwargs)
        except recipe.Issue43FastRelaxationError:
            pass
        else:
            raise AssertionError("invalid construction input was not rejected")


def _check_analysis_contract() -> None:
    rows = _synthetic_rows()
    result = recipe.analyze_relaxation(
        rows,
        electron_density=1.0e16,
        relax_tol=2.0e-4,
    )
    if result["status"] != "PASS":
        raise AssertionError("positive relaxation analysis failed")

    bad = [dict(row) for row in rows]
    bad[-1]["inventory"] *= 1.01
    if recipe.analyze_relaxation(bad, electron_density=1.0e16)["status"] != "FAIL":
        raise AssertionError("inventory mutation was not rejected")


def _check_csv_contract() -> None:
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

        if recipe.find_relaxation_csv(root) != preferred:
            raise AssertionError("preferred runtime CSV selection changed")
        if recipe.read_relaxation_rows(preferred) != rows:
            raise AssertionError("relaxation CSV parsing changed")

        preferred.unlink()
        alternate.unlink()
        try:
            recipe.find_relaxation_csv(root)
        except recipe.Issue43FastRelaxationError:
            pass
        else:
            raise AssertionError("missing relaxation CSV was not rejected")


def _check_classification_contract() -> None:
    known_good = {"class": "P3_PASS", "canonical_checker": {"status": "PASS"}}
    known_bad = {"class": "RUNTIME_FAIL", "canonical_checker": {"status": "FAIL"}}
    good = {"class": "P3_PASS", "analysis": {"status": "PASS"}}
    bad = {"class": "SOLVER_CONVERGENCE_FAIL", "analysis": {"status": "FAIL"}}
    tau_dr = 1.2e-12

    cases = (
        ("KNOWN_GOOD_ELECTRON_CONTROL_FAIL", (known_bad, good, good, good, None, None, tau_dr)),
        ("ELECTRON_300K_CONTROL_FAIL", (known_good, None, good, good, None, None, tau_dr)),
        ("POISSON_OR_BLOCK_SCALING_FAIL", (known_good, good, None, good, None, None, tau_dr)),
        ("FEEDBACK_CASE_MISSING", (known_good, good, good, None, None, None, tau_dr)),
        ("FEEDBACK_IMPLICIT_COUPLING_RECOVERS_NEAR_TAU_DR", (known_good, good, good, good, None, good, tau_dr)),
        ("DIELECTRIC_TIMESTEP_STIFFNESS_CONFIRMED", (known_good, good, good, good, None, bad, tau_dr)),
        ("FEEDBACK_RECOVERS_BELOW_TAU_DR", (known_good, good, good, good, None, None, tau_dr)),
        ("DIELECTRIC_TIMESTEP_STIFFNESS_STRONG", (known_good, good, good, bad, good, None, tau_dr)),
        ("FEEDBACK_JACOBIAN_SCALING_OR_INITIALIZATION_FAIL", (known_good, good, good, bad, bad, None, tau_dr)),
        ("FEEDBACK_DISCRIMINATOR_INCOMPLETE", (known_good, good, good, bad, None, None, tau_dr)),
    )
    for expected_class, args in cases:
        current = recipe.classify(*args)
        compatibility = v2.classify(*args)
        if current != compatibility:
            raise AssertionError(
                f"v2 classification delegation drift for {expected_class}: recipe={current!r} v2={compatibility!r}"
            )
        if current.get("class") != expected_class:
            raise AssertionError(
                f"classification branch drift: expected {expected_class}, got {current.get('class')}"
            )

    if recipe.DT_FEEDBACK_BASE != v2.DT_FEEDBACK_BASE:
        raise AssertionError("recipe base feedback timestep drifted from v2 compatibility owner")
    if recipe.DT_FEEDBACK_SMALL != v2.DT_FEEDBACK_SMALL:
        raise AssertionError("recipe small feedback timestep drifted from v2 compatibility owner")
    if recipe.DT_FEEDBACK_LARGE != v2.DT_FEEDBACK_LARGE:
        raise AssertionError("recipe large feedback timestep drifted from v2 compatibility owner")

    source = inspect.getsource(v2.classify)
    if "return relaxation_recipe.classify(" not in source:
        raise AssertionError("v2 classify is not a direct recipe compatibility delegate")
    for forbidden in ("_physics_pass(", "DT_FEEDBACK_BASE / tau_dr", "KNOWN_GOOD_ELECTRON_CONTROL_FAIL"):
        if forbidden in source:
            raise AssertionError(f"duplicate scientific policy remains in v2 classify: {forbidden}")


def _check_v2_cutover() -> None:
    source = Path(v2.__file__).read_text()
    if "from . import fast_plasma_relaxation as v1" in source:
        raise AssertionError("v2 still imports historical fast_plasma_relaxation")
    if "from recipes import issue43_fast_relaxation as relaxation_recipe" not in source:
        raise AssertionError("v2 does not bind the canonical Issue43 recipe")
    if v2.FastPlasmaRelaxationError is not recipe.Issue43FastRelaxationError:
        raise AssertionError("v2 relaxation error compatibility changed")
    if v2.v1.FastPlasmaRelaxationError is not v2.FastPlasmaRelaxationError:
        raise AssertionError("v5 exception compatibility path changed")

    feedback = v2._build_feedback(
        _fixture(),
        dt=1.0e-13,
        steps=5,
        radial_span=0.243,
    )
    expected, _ = recipe.build_fast_input(
        _fixture(),
        gas_temperature=v2.GAS_TEMPERATURE,
        electron_density=v2.DEFAULT_ELECTRON_DENSITY,
        dt=1.0e-13,
        end_time=5.0e-13,
        radial_span=0.243,
    )
    if feedback != expected:
        raise AssertionError("v2 feedback builder drifted from canonical recipe")


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
        _check_builder_contract()
        _check_analysis_contract()
        _check_csv_contract()
        _check_classification_contract()
        _check_v2_cutover()
        _check_recipe_boundary()
    except Exception as exc:
        print(f"ISSUE48_ISSUE43_RELAXATION_RECIPE_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE48_ISSUE43_RELAXATION_RECIPE_SELFTEST: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
