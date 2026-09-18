#!/usr/bin/env python3
"""Build Issue #234 electron-only one-way Poisson observer from the accepted drift+surface baseline."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent / "Issue234_m1_1d_electron_drift_surface" / "input_drift_surface.i"
OUT = ROOT / "input_poisson_observer.i"


def replace_once(text: str, old: str, new: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"expected exactly one anchor, found {count}: {old!r}")
    return text.replace(old, new, 1)


def build(text: str) -> str:
    text = replace_once(
        text,
        "# Issue #234 bottom-up discriminator: 1D electron electrostatic drift + controlled thermal wall loss.\n",
        "# Issue #234 bottom-up discriminator: electron-only one-way Poisson observer.\n"
        "# Electron transport remains on the accepted prescribed phi_ramp; potential_plasma is observation-only.\n",
    )

    variable_anchor = """  [log_e]
    type = MooseVariableFVReal
    # n_e0 = 1e18 m^-3 -> c_e0 = n_e0/N_A mol/m^3
    initial_condition = -13.30836826905085
  []
"""
    variable_insert = variable_anchor + """  [potential_plasma]
    type = MooseVariableFVReal
    initial_condition = 0.0
  []
"""
    text = replace_once(text, variable_anchor, variable_insert)

    material_anchor = """  [thermal_surface_flux]
    type = ADParsedFunctorMaterial
"""
    material_insert = """  [electrostatic_constants]
    type = ADGenericFunctorMaterial
    prop_names = 'relative_permittivity'
    prop_values = '1.0'
  []

  [physical_charge_density]
    type = ADParsedFunctorMaterial
    property_name = charge_density_C_m3
    functor_names = 'electron_density_m3'
    functor_symbols = 'ne'
    # Fixed positive background n_i=1e18 m^-3 gives exact quasi-neutrality at t=0.
    expression = '1.602176634e-19*(1.0e18-ne)'
  []

  [poisson_charge_source]
    type = ADParsedFunctorMaterial
    property_name = poisson_charge_source
    functor_names = 'charge_density_C_m3'
    functor_symbols = 'rhoq'
    expression = 'rhoq/8.8541878128e-12'
  []

""" + material_anchor
    text = replace_once(text, material_anchor, material_insert)

    kernel_anchor = """[]

[FVBCs]
"""
    kernel_insert = """  [phi_diffusion]
    type = FVDiffusion
    variable = potential_plasma
    coeff = relative_permittivity
  []

  [phi_charge_source]
    type = FVCoupledForce
    variable = potential_plasma
    v = poisson_charge_source
    coef = 1.0
  []
[]

[FVBCs]
"""
    text = replace_once(text, kernel_anchor, kernel_insert)

    bc_anchor = """[FVBCs]
  [right_thermal_surface_loss]
"""
    bc_insert = """[FVBCs]
  [left_ground]
    type = FVDirichletBC
    variable = potential_plasma
    boundary = left
    value = 0.0
  []

  [right_thermal_surface_loss]
"""
    text = replace_once(text, bc_anchor, bc_insert)

    pp_anchor = """  [wall_thermal_flux_rate_per_area]
    type = ADSideIntegralFunctorPostprocessor
"""
    pp_insert = """  [charge_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = charge_density_C_m3
    execute_on = 'INITIAL TIMESTEP_END'
  []

  [phi_min]
    type = ADElementExtremeFunctorValue
    functor = potential_plasma
    value_type = min
    execute_on = 'INITIAL TIMESTEP_END'
  []

  [phi_max]
    type = ADElementExtremeFunctorValue
    functor = potential_plasma
    value_type = max
    execute_on = 'INITIAL TIMESTEP_END'
  []

  [gauss_flux_reduced]
    type = SideDiffusiveFluxIntegral
    variable = potential_plasma
    boundary = 'left right'
    functor_diffusivity = relative_permittivity
    execute_on = 'INITIAL TIMESTEP_END'
  []

  [gauss_flux_charge]
    type = ScalePostprocessor
    value = gauss_flux_reduced
    scaling_factor = 8.8541878128e-12
    execute_on = 'INITIAL TIMESTEP_END'
  []

""" + pp_anchor
    text = replace_once(text, pp_anchor, pp_insert)

    return text


def static_contract_text(text: str) -> dict[str, bool]:
    return {
        "one_dimensional": "dim = 1" in text,
        "states_loge_and_potential": "[log_e]" in text and "[potential_plasma]" in text,
        "fixed_positive_background": "1.602176634e-19*(1.0e18-ne)" in text,
        "physical_electron_density": "6.02214076e23*exp(loge)" in text,
        "poisson_diffusion": all(
            token in text
            for token in (
                "[phi_diffusion]",
                "type = FVDiffusion",
                "variable = potential_plasma",
                "coeff = relative_permittivity",
            )
        ),
        "poisson_source": all(
            token in text
            for token in (
                "[phi_charge_source]",
                "type = FVCoupledForce",
                "v = poisson_charge_source",
            )
        ),
        "left_ground": all(
            token in text
            for token in (
                "[left_ground]",
                "variable = potential_plasma",
                "boundary = left",
                "value = 0.0",
            )
        ),
        "right_natural_poisson": text.count("variable = potential_plasma") >= 3
        and "boundary = right\n    value = 0.0" not in text,
        "electron_drift_prescribed_field": "potential = phi_ramp" in text,
        "poisson_feedback_off": "potential = potential_plasma" not in text,
        "wall_loss_preserved": "[right_thermal_surface_loss]" in text,
        "no_diffusion": "PhysicsFVLogMolarElectronDiffusion" not in text,
        "no_heavy_evolution": "PhysicsFVConservativeMassFractionTimeDerivative" not in text
        and "INSFVMassAdvection" not in text,
        "no_energy_solve": "c_epsilon" not in text and "n_epsilon" not in text,
        "no_chemistry": "ReactionSource" not in text,
        "no_see": "secondary_emission" not in text.lower() and "see_bc" not in text.lower(),
        "gauss_observables": all(
            token in text
            for token in (
                "[charge_integral]",
                "[gauss_flux_reduced]",
                "[gauss_flux_charge]",
                "[phi_min]",
                "[phi_max]",
            )
        ),
        "automatic_scaling_off": "automatic_scaling = false" in text,
        "exodus_enabled": "exodus = true" in text,
    }


def self_test() -> None:
    base = BASE.read_text(encoding="utf-8")
    candidate = build(base)
    checks = static_contract_text(candidate)
    failed = sorted(k for k, ok in checks.items() if not ok)
    if failed:
        raise RuntimeError(f"candidate static contract failed: {failed}")

    mutated = candidate.replace("potential = phi_ramp", "potential = potential_plasma", 1)
    mutation_checks = static_contract_text(mutated)
    if mutation_checks["poisson_feedback_off"]:
        raise RuntimeError("feedback mutation was not rejected")
    if mutation_checks["electron_drift_prescribed_field"]:
        raise RuntimeError("feedback mutation retained prescribed-field classification")


def main() -> int:
    self_test()
    candidate = build(BASE.read_text(encoding="utf-8"))
    OUT.write_text(candidate, encoding="utf-8")
    print(f"WROTE {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
