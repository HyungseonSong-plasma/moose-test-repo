#!/usr/bin/env python3
"""P0 characterization for the historical Issue43 fast-relaxation recipe/runtime split."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.historical_recipe_support import issue43_fast_relaxation as recipe


HISTORICAL_RUNTIME_DT_FEEDBACK_BASE = 1.0e-13
HISTORICAL_RUNTIME_DT_FEEDBACK_SMALL = 1.0e-14
HISTORICAL_RUNTIME_DT_FEEDBACK_LARGE = 1.0e-12


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
        if current.get("class") != expected_class:
            raise AssertionError(
                f"classification branch drift: expected {expected_class}, got {current.get('class')}"
            )

    frozen_runtime_aliases = {
        "DT_FEEDBACK_BASE": HISTORICAL_RUNTIME_DT_FEEDBACK_BASE,
        "DT_FEEDBACK_SMALL": HISTORICAL_RUNTIME_DT_FEEDBACK_SMALL,
        "DT_FEEDBACK_LARGE": HISTORICAL_RUNTIME_DT_FEEDBACK_LARGE,
    }
    for name, expected in frozen_runtime_aliases.items():
        if getattr(recipe, name) != expected:
            raise AssertionError(f"historical runtime alias drifted: {name}")


def _check_runtime_composition_boundary() -> None:
    for relative in (
        "qpx_harness/issue43_relaxation_runtime.py",
        "physics_harness/issue43_relaxation_runtime.py",
    ):
        if (ROOT / relative).exists():
            raise AssertionError(f"retired Issue43 runtime owner resurrected: {relative}")

    for relative in (
        "physics_harness/execution/runtime.py",
        "physics_harness/execution/cases.py",
        "physics_harness/adapters/moose/input.py",
        "physics_harness/adapters/petsc/log.py",
        "physics_harness/analysis/scale_audit.py",
    ):
        if not (ROOT / relative).is_file():
            raise AssertionError(f"canonical generic runtime primitive missing: {relative}")


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
        _check_runtime_composition_boundary()
        _check_recipe_boundary()
    except Exception as exc:
        print(f"ISSUE48_ISSUE43_RELAXATION_RECIPE_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE48_ISSUE43_RELAXATION_RECIPE_SELFTEST: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
