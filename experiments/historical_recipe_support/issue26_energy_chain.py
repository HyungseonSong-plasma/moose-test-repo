"""Issue #26 E2b-E5 integrated electron-energy promotion chain.

The chain intentionally keeps production coefficient provenance and solved-energy
transport lookup coupling out of scope.  It validates, in one user-local QPX
execution, the controlled energy-drift sign, drift-only Joule source,
COMSOL thermal electron-energy wall flux, and the previously frozen A8
ion-induced 4 eV SEE energy flux.
"""
from __future__ import annotations

import math
import re
from typing import Any, Mapping

from experiments.Issue27_surface_reactions.controlled_wall.combined import PLASMA_WALLS
from experiments.Issue27_surface_reactions.controlled_wall.electron_wall import (
    ELECTRON_MASS_KG,
)
from experiments.Issue27_surface_reactions.controlled_wall.electron_wall_stable import (
    A7_DISCRIMINATOR_DT_S,
)
from experiments.Issue27_surface_reactions.controlled_wall.see import (
    SEE_ENERGY_PP as A8_SEE_ENERGY_PP,
    SEE_FUNCTOR as A8_SEE_PARTICLE_FLUX_FUNCTOR,
    _build_a8_case_input,
)
from physics_harness.adapters.moose import blocks as mb
from physics_harness.adapters.moose import parameters as mp
from experiments.historical_recipe_support.issue26_e1 import (
    E1_DT_S,
    ELEMENTARY_CHARGE_C,
    ENERGY_DENSITY_EV_FUNCTOR,
    ENERGY_DENSITY_J_FUNCTOR,
    ENERGY_INVENTORY_PP,
    ENERGY_NORM_AVG_PP,
    ENERGY_NORM_MAX_PP,
    ENERGY_NORM_MIN_PP,
    ENERGY_REFERENCE_EV,
    ENERGY_TIME_KERNEL,
    ENERGY_VARIABLE,
    MEAN_EN_AVG_PP,
    MEAN_EN_MAX_PP,
    MEAN_EN_MIN_PP,
    MEAN_EN_SOLVED_FUNCTOR,
    build_issue26_e1_input,
)
from experiments.historical_recipe_support.issue26_e2a import E2A_INITIAL_EXPRESSION
from experiments.historical_recipe_support.issue91_r3 import BOUNDARIES_TO_AVOID

E2B_DT_S = E1_DT_S
E2B_FIELD_V_M = 1.0e5
E2B_MOBILITY_M2_V_S = 1.0
E2B_PROFILE_FUNCTION = "e2b_energy_profile"
E2B_PROFILE_IC = "e2b_energy_profile_ic"
E2B_POTENTIAL_FUNCTION = "e2b_energy_potential"
E2B_MOBILITY_MATERIAL = "e2b_energy_mobility"
E2B_DRIFT_KERNEL = "n_epsilon_drift"
E2B_LEFT_PP = "e2b_energy_left"
E2B_RIGHT_PP = "e2b_energy_right"
E2B_LEFT_POINT = (0.10227957, 0.21949655, 0.0)
E2B_RIGHT_POINT = (0.14252049, 0.21961408, 0.0)

E3_DT_S = E1_DT_S
E3_FIELD_V_M = 1.0e3
E3_MOBILITY_M2_V_S = 0.1
E3_JOULE_KERNEL = "n_epsilon_joule_control"
E3_JOULE_POWER_PP = "e3_joule_power_W"

ENERGY_WALL_THERMAL_MATERIAL = "issue26_energy_wall_thermal_material"
ENERGY_WALL_THERMAL_FUNCTOR = "issue26_energy_wall_thermal_flux_outward"
ENERGY_WALL_THERMAL_BC = "issue26_energy_wall_thermal_loss"
ENERGY_WALL_THERMAL_RATE_PP = "issue26_energy_wall_thermal_rate"
ENERGY_WALL_THERMAL_POWER_PP = "issue26_energy_wall_thermal_power_W"

SEE_ENERGY_MATERIAL = "issue26_see_energy_material"
SEE_ENERGY_FUNCTOR = "issue26_see_energy_normalized_flux_inward"
SEE_ENERGY_BC = "issue26_see_energy_source"
SEE_ENERGY_RATE_PP = "issue26_see_energy_rate"
SEE_ENERGY_COUPLED_POWER_PP = "issue26_see_energy_coupled_power_W"

A8_WALL_PARAMETERS: dict[str, Any] = {
    "wall_model": "finite_see_control",
    "wall_scope": "all_plasma_walls",
    "electron_wall_migration": False,
    "electron_energy_equation_coupled": False,
    "O2p_secondary_emission_coefficient": 0.05,
    "Op_secondary_emission_coefficient": 0.05,
    "secondary_electron_mean_energy_eV": 4.0,
    "O_sticking_coefficient": 0.2,
    "O2s_sticking_coefficient": 1.0,
    "Os_sticking_coefficient": 0.2,
    "O2p_sticking_coefficient": 1.0,
    "Om_sticking_coefficient": 1.0,
    "Op_sticking_coefficient": 1.0,
}


class Issue26EnergyChainError(RuntimeError):
    pass


def _top_level_float(text: str, name: str) -> float:
    matches = re.findall(rf"(?m)^\s*{re.escape(name)}\s*=\s*([^#\r\n]+)", text)
    if len(matches) != 1:
        raise Issue26EnergyChainError(f"cannot resolve unique top-level scalar {name}")
    value = float(matches[0].strip())
    if not math.isfinite(value):
        raise Issue26EnergyChainError(f"non-finite scalar {name}={value}")
    return value


def _wall_list() -> str:
    return "'" + " ".join(PLASMA_WALLS) + "'"


def _insert_profile_ic(text: str) -> str:
    text = mp.remove_parameter(text, f"Variables/{ENERGY_VARIABLE}", "initial_condition")
    for path in (
        f"Functions/{E2B_PROFILE_FUNCTION}",
        f"ICs/{E2B_PROFILE_IC}",
    ):
        mb.require_absent(text, path)
    text = mb.insert_child_block(
        text,
        "Functions",
        f"""  [{E2B_PROFILE_FUNCTION}]
    type = ParsedFunction
    expression = '{E2A_INITIAL_EXPRESSION}'
  []""",
    )
    return mb.insert_child_block(
        text,
        "ICs",
        f"""  [{E2B_PROFILE_IC}]
    type = FunctionIC
    variable = {ENERGY_VARIABLE}
    function = {E2B_PROFILE_FUNCTION}
  []""",
    )


def build_e2b_drift_input(
    base_text: str,
    *,
    field_v_m: float,
    mobility_m2_v_s: float = E2B_MOBILITY_M2_V_S,
) -> tuple[str, dict[str, Any]]:
    if not math.isfinite(field_v_m):
        raise Issue26EnergyChainError("field_v_m must be finite")
    if not math.isfinite(mobility_m2_v_s) or mobility_m2_v_s < 0.0:
        raise Issue26EnergyChainError("mobility_m2_v_s must be finite and non-negative")

    text, predecessor = build_issue26_e1_input(base_text, initial_energy_hat=1.0)
    text = _insert_profile_ic(text)

    for path in (
        f"Functions/{E2B_POTENTIAL_FUNCTION}",
        f"FunctorMaterials/{E2B_MOBILITY_MATERIAL}",
        f"FVKernels/{E2B_DRIFT_KERNEL}",
        f"Postprocessors/{E2B_LEFT_PP}",
        f"Postprocessors/{E2B_RIGHT_PP}",
    ):
        mb.require_absent(text, path)

    potential_x_coefficient = -field_v_m
    text = mb.insert_child_block(
        text,
        "Functions",
        f"""  [{E2B_POTENTIAL_FUNCTION}]
    type = ParsedFunction
    expression = '{potential_x_coefficient:.17g}*x'
  []""",
    )
    text = mb.insert_child_block(
        text,
        "FunctorMaterials",
        f"""  [{E2B_MOBILITY_MATERIAL}]
    type = ADGenericFunctorMaterial
    prop_names = 'electron_energy_mobility_control'
    prop_values = '{mobility_m2_v_s:.17g}'
    block = plasma
  []""",
    )
    text = mb.insert_child_block(
        text,
        "FVKernels",
        f"""  [{E2B_DRIFT_KERNEL}]
    type = QPXFVElectrostaticDrift
    variable = {ENERGY_VARIABLE}
    potential = {E2B_POTENTIAL_FUNCTION}
    mobility = electron_energy_mobility_control
    carrier = carrier_one
    charge_number = -1
    advected_interp_method = upwind
    boundaries_to_avoid = '{BOUNDARIES_TO_AVOID}'
    block = plasma
  []""",
    )
    for name, point in (
        (E2B_LEFT_PP, E2B_LEFT_POINT),
        (E2B_RIGHT_PP, E2B_RIGHT_POINT),
    ):
        text = mb.insert_child_block(
            text,
            "Postprocessors",
            f"""  [{name}]
    type = PointValue
    variable = {ENERGY_VARIABLE}
    point = '{point[0]:.17g} {point[1]:.17g} {point[2]:.17g}'
    execute_on = 'INITIAL TIMESTEP_END'
  []""",
        )
    text = mp.upsert_parameter(text, "Executioner", "dt", f"{E2B_DT_S:.17g}")
    text = mp.upsert_parameter(text, "Executioner", "end_time", f"{E2B_DT_S:.17g}")

    return text, {
        "issue": 26,
        "phase": "E2b",
        "model": "CONTROLLED_ELECTRON_ENERGY_DRIFT",
        "predecessor": predecessor,
        "field_v_m": field_v_m,
        "mobility_m2_v_s": mobility_m2_v_s,
        "drift_velocity_m_s": -mobility_m2_v_s * field_v_m,
        "sign_contract": (
            "Gamma_epsilon,drift = -mu_epsilon*n_epsilon*E; "
            "positive E_x must move the energy profile toward -x"
        ),
        "closed_boundary_contract": BOUNDARIES_TO_AVOID,
        "left_probe": E2B_LEFT_POINT,
        "right_probe": E2B_RIGHT_POINT,
        "timestep_s": E2B_DT_S,
        "production_energy_mobility_validated": False,
    }


def build_e3_joule_input(
    base_text: str,
    *,
    field_v_m: float,
    mobility_m2_v_s: float = E3_MOBILITY_M2_V_S,
) -> tuple[str, dict[str, Any]]:
    if not math.isfinite(field_v_m):
        raise Issue26EnergyChainError("field_v_m must be finite")
    if not math.isfinite(mobility_m2_v_s) or mobility_m2_v_s < 0.0:
        raise Issue26EnergyChainError("mobility_m2_v_s must be finite and non-negative")

    text, predecessor = build_issue26_e1_input(base_text, initial_energy_hat=1.0)
    for path in (
        f"FVKernels/{E3_JOULE_KERNEL}",
        f"Postprocessors/{E3_JOULE_POWER_PP}",
    ):
        mb.require_absent(text, path)

    coefficient_s_inv = mobility_m2_v_s * field_v_m * field_v_m / ENERGY_REFERENCE_EV
    text = mb.insert_child_block(
        text,
        "FVKernels",
        f"""  [{E3_JOULE_KERNEL}]
    type = FVCoupledForce
    variable = {ENERGY_VARIABLE}
    v = n_e
    coef = {coefficient_s_inv:.17g}
    block = plasma
  []""",
    )
    power_per_electron_w = (
        ELEMENTARY_CHARGE_C * mobility_m2_v_s * field_v_m * field_v_m
    )
    text = mb.insert_child_block(
        text,
        "Postprocessors",
        f"""  [{E3_JOULE_POWER_PP}]
    type = ScalePostprocessor
    value = n_e_inventory
    scaling_factor = {power_per_electron_w:.17g}
    execute_on = 'INITIAL TIMESTEP_END'
  []""",
    )
    text = mp.upsert_parameter(text, "Executioner", "dt", f"{E3_DT_S:.17g}")
    text = mp.upsert_parameter(text, "Executioner", "end_time", f"{E3_DT_S:.17g}")

    return text, {
        "issue": 26,
        "phase": "E3",
        "model": "CONTROLLED_DRIFT_ONLY_JOULE_HEATING",
        "predecessor": predecessor,
        "field_v_m": field_v_m,
        "mobility_m2_v_s": mobility_m2_v_s,
        "normalized_source_coefficient_s_inv": coefficient_s_inv,
        "power_per_electron_W": power_per_electron_w,
        "joule_contract": (
            "E.Gamma_e = -mu_e*n_e*E^2; residual source is "
            "+mu_e*E^2/epsilon_ref times n_hat through FVCoupledForce"
        ),
        "timestep_s": E3_DT_S,
        "production_solved_field_joule_coupling_validated": False,
    }


def _insert_energy_state_on_existing(text: str, *, initial_energy_hat: float = 1.0) -> tuple[str, float]:
    if initial_energy_hat <= 0.0 or not math.isfinite(initial_energy_hat):
        raise Issue26EnergyChainError("initial_energy_hat must be finite and positive")
    for path in (
        f"Variables/{ENERGY_VARIABLE}",
        f"FunctorMaterials/{ENERGY_DENSITY_EV_FUNCTOR}",
        f"FunctorMaterials/{ENERGY_DENSITY_J_FUNCTOR}",
        f"FunctorMaterials/{MEAN_EN_SOLVED_FUNCTOR}",
        f"FVKernels/{ENERGY_TIME_KERNEL}",
        f"Postprocessors/{ENERGY_INVENTORY_PP}",
        f"Postprocessors/{ENERGY_NORM_AVG_PP}",
        f"Postprocessors/{ENERGY_NORM_MIN_PP}",
        f"Postprocessors/{ENERGY_NORM_MAX_PP}",
        f"Postprocessors/{MEAN_EN_AVG_PP}",
        f"Postprocessors/{MEAN_EN_MIN_PP}",
        f"Postprocessors/{MEAN_EN_MAX_PP}",
    ):
        mb.require_absent(text, path)

    n_ref = _top_level_float(text, "n_e_value")
    energy_scale_ev_m3 = n_ref * ENERGY_REFERENCE_EV
    energy_scale_j_m3 = energy_scale_ev_m3 * ELEMENTARY_CHARGE_C

    text = mb.insert_child_block(
        text,
        "Variables",
        f"""  [{ENERGY_VARIABLE}]
    type = MooseVariableFVReal
    initial_condition = {initial_energy_hat:.17g}
    block = plasma
  []""",
    )
    text = mb.insert_child_block(
        text,
        "FunctorMaterials",
        f"""  [{ENERGY_DENSITY_EV_FUNCTOR}]
    type = ADParsedFunctorMaterial
    property_name = {ENERGY_DENSITY_EV_FUNCTOR}
    functor_names = '{ENERGY_VARIABLE}'
    functor_symbols = 'eps_hat'
    expression = '{energy_scale_ev_m3:.17g}*eps_hat'
    block = plasma
  []""",
    )
    text = mb.insert_child_block(
        text,
        "FunctorMaterials",
        f"""  [{ENERGY_DENSITY_J_FUNCTOR}]
    type = ADParsedFunctorMaterial
    property_name = {ENERGY_DENSITY_J_FUNCTOR}
    functor_names = '{ENERGY_VARIABLE}'
    functor_symbols = 'eps_hat'
    expression = '{energy_scale_j_m3:.17g}*eps_hat'
    block = plasma
  []""",
    )
    text = mb.insert_child_block(
        text,
        "FunctorMaterials",
        f"""  [{MEAN_EN_SOLVED_FUNCTOR}]
    type = ADParsedFunctorMaterial
    property_name = {MEAN_EN_SOLVED_FUNCTOR}
    functor_names = '{ENERGY_VARIABLE} n_e'
    functor_symbols = 'eps_hat ne_hat'
    expression = '{ENERGY_REFERENCE_EV:.17g}*eps_hat/ne_hat'
    block = plasma
  []""",
    )
    text = mb.insert_child_block(
        text,
        "FVKernels",
        f"""  [{ENERGY_TIME_KERNEL}]
    type = FVTimeKernel
    variable = {ENERGY_VARIABLE}
    block = plasma
  []""",
    )

    postprocessors = (
        (ENERGY_INVENTORY_PP, "ADElementIntegralFunctorPostprocessor",
         f"    functor = {ENERGY_DENSITY_J_FUNCTOR}\n    block = plasma"),
        (ENERGY_NORM_AVG_PP, "ElementAverageFunctorPostprocessor",
         f"    functor = {ENERGY_VARIABLE}\n    block = plasma"),
        (ENERGY_NORM_MIN_PP, "ADElementExtremeFunctorValue",
         f"    functor = {ENERGY_VARIABLE}\n    value_type = min\n    block = plasma"),
        (ENERGY_NORM_MAX_PP, "ADElementExtremeFunctorValue",
         f"    functor = {ENERGY_VARIABLE}\n    value_type = max\n    block = plasma"),
        (MEAN_EN_AVG_PP, "ElementAverageFunctorPostprocessor",
         f"    functor = {MEAN_EN_SOLVED_FUNCTOR}\n    block = plasma"),
        (MEAN_EN_MIN_PP, "ADElementExtremeFunctorValue",
         f"    functor = {MEAN_EN_SOLVED_FUNCTOR}\n    value_type = min\n    block = plasma"),
        (MEAN_EN_MAX_PP, "ADElementExtremeFunctorValue",
         f"    functor = {MEAN_EN_SOLVED_FUNCTOR}\n    value_type = max\n    block = plasma"),
    )
    for name, type_name, body in postprocessors:
        text = mb.insert_child_block(
            text,
            "Postprocessors",
            f"""  [{name}]
    type = {type_name}
{body}
    execute_on = 'INITIAL TIMESTEP_END'
  []""",
        )
    return text, n_ref


def _insert_energy_wall_terms(
    text: str,
    *,
    n_ref: float,
    thermal_energy_on: bool,
    see_energy_on: bool,
    secondary_energy_ev: float = 4.0,
) -> str:
    if secondary_energy_ev != 4.0:
        raise Issue26EnergyChainError("Issue26 E5 freezes secondary energy to 4 eV")
    for path in (
        f"FunctorMaterials/{ENERGY_WALL_THERMAL_MATERIAL}",
        f"FVBCs/{ENERGY_WALL_THERMAL_BC}",
        f"Postprocessors/{ENERGY_WALL_THERMAL_RATE_PP}",
        f"Postprocessors/{ENERGY_WALL_THERMAL_POWER_PP}",
        f"FunctorMaterials/{SEE_ENERGY_MATERIAL}",
        f"FVBCs/{SEE_ENERGY_BC}",
        f"Postprocessors/{SEE_ENERGY_RATE_PP}",
        f"Postprocessors/{SEE_ENERGY_COUPLED_POWER_PP}",
    ):
        mb.require_absent(text, path)

    wall_list = _wall_list()
    thermal_expression = (
        f"{5.0/6.0:.17g}*eps_hat*"
        f"sqrt(16.0*{ELEMENTARY_CHARGE_C:.17g}*mean_ev/"
        f"(3.0*3.14159265358979323846*{ELECTRON_MASS_KG:.17g}))"
    )
    text = mb.insert_child_block(
        text,
        "FunctorMaterials",
        f"""  [{ENERGY_WALL_THERMAL_MATERIAL}]
    type = ADParsedFunctorMaterial
    property_name = {ENERGY_WALL_THERMAL_FUNCTOR}
    functor_names = '{ENERGY_VARIABLE} {MEAN_EN_SOLVED_FUNCTOR}'
    functor_symbols = 'eps_hat mean_ev'
    expression = '{thermal_expression}'
    block = plasma
  []""",
    )
    text = mb.insert_child_block(
        text,
        "FVBCs",
        f"""  [{ENERGY_WALL_THERMAL_BC}]
    type = FVFunctorNeumannBC
    variable = {ENERGY_VARIABLE}
    boundary = {wall_list}
    functor = {ENERGY_WALL_THERMAL_FUNCTOR}
    factor = {-1.0 if thermal_energy_on else 0.0:.17g}
  []""",
    )
    text = mb.insert_child_block(
        text,
        "Postprocessors",
        f"""  [{ENERGY_WALL_THERMAL_RATE_PP}]
    type = SideFVFluxBCIntegral
    boundary = {wall_list}
    fvbcs = '{ENERGY_WALL_THERMAL_BC}'
    execute_on = 'INITIAL TIMESTEP_END'
  []""",
    )
    energy_flux_scale_w_per_m3_s = n_ref * ENERGY_REFERENCE_EV * ELEMENTARY_CHARGE_C
    text = mb.insert_child_block(
        text,
        "Postprocessors",
        f"""  [{ENERGY_WALL_THERMAL_POWER_PP}]
    type = ScalePostprocessor
    value = {ENERGY_WALL_THERMAL_RATE_PP}
    scaling_factor = {energy_flux_scale_w_per_m3_s:.17g}
    execute_on = 'INITIAL TIMESTEP_END'
  []""",
    )

    see_scale = secondary_energy_ev / ENERGY_REFERENCE_EV
    text = mb.insert_child_block(
        text,
        "FunctorMaterials",
        f"""  [{SEE_ENERGY_MATERIAL}]
    type = ADParsedFunctorMaterial
    property_name = {SEE_ENERGY_FUNCTOR}
    functor_names = '{A8_SEE_PARTICLE_FLUX_FUNCTOR}'
    functor_symbols = 'see_particle_hat_flux'
    expression = '{see_scale:.17g}*see_particle_hat_flux'
    block = plasma
  []""",
    )
    text = mb.insert_child_block(
        text,
        "FVBCs",
        f"""  [{SEE_ENERGY_BC}]
    type = FVFunctorNeumannBC
    variable = {ENERGY_VARIABLE}
    boundary = {wall_list}
    functor = {SEE_ENERGY_FUNCTOR}
    factor = {1.0 if see_energy_on else 0.0:.17g}
  []""",
    )
    text = mb.insert_child_block(
        text,
        "Postprocessors",
        f"""  [{SEE_ENERGY_RATE_PP}]
    type = SideFVFluxBCIntegral
    boundary = {wall_list}
    fvbcs = '{SEE_ENERGY_BC}'
    execute_on = 'INITIAL TIMESTEP_END'
  []""",
    )
    text = mb.insert_child_block(
        text,
        "Postprocessors",
        f"""  [{SEE_ENERGY_COUPLED_POWER_PP}]
    type = ScalePostprocessor
    value = {SEE_ENERGY_RATE_PP}
    scaling_factor = {energy_flux_scale_w_per_m3_s:.17g}
    execute_on = 'INITIAL TIMESTEP_END'
  []""",
    )
    return text


def build_e4_e5_wall_input(
    base_text: str,
    *,
    see_particle_on: bool,
    see_energy_on: bool,
) -> tuple[str, dict[str, Any]]:
    mode = "see_on" if see_particle_on else "see_off"
    text, a8_meta = _build_a8_case_input(
        base_text,
        parameters=A8_WALL_PARAMETERS,
        mode=mode,
    )
    text, n_ref = _insert_energy_state_on_existing(text, initial_energy_hat=1.0)
    text = _insert_energy_wall_terms(
        text,
        n_ref=n_ref,
        thermal_energy_on=True,
        see_energy_on=see_energy_on,
        secondary_energy_ev=4.0,
    )
    text = mp.upsert_parameter(
        text, "Executioner", "dt", f"{A7_DISCRIMINATOR_DT_S:.17g}"
    )
    text = mp.upsert_parameter(
        text, "Executioner", "end_time", f"{A7_DISCRIMINATOR_DT_S:.17g}"
    )
    return text, {
        "issue": 26,
        "phase": "E5" if see_particle_on else "E4",
        "model": (
            "A8_WALL_PLUS_THERMAL_AND_4EV_ENERGY"
            if see_particle_on
            else "A7_WALL_PLUS_THERMAL_ENERGY"
        ),
        "a8_construction": a8_meta,
        "electron_reference_density_m3": n_ref,
        "thermal_energy_wall_enabled": True,
        "see_particle_enabled": see_particle_on,
        "see_energy_enabled": see_energy_on,
        "thermal_energy_contract": (
            "Gamma_epsilon,out/(n_ref*epsilon_ref) = "
            "(5/6)*v_th(mean_en_solved)*n_epsilon_hat"
        ),
        "see_energy_contract": (
            "Gamma_epsilon,SEE,in/(n_ref*epsilon_ref) = "
            "(4 eV/epsilon_ref)*(Gamma_e,SEE/n_ref)"
        ),
        "wall_boundaries": list(PLASMA_WALLS),
        "excluded_boundaries": ["inlet", "outlet"],
        "secondary_electron_mean_energy_eV": 4.0,
        "timestep_s": A7_DISCRIMINATOR_DT_S,
        "particle_transport_lookup_coupled_to_solved_energy": False,
        "physical_plasma_potential_acceptance": False,
    }


__all__ = [
    "A8_SEE_ENERGY_PP",
    "A8_WALL_PARAMETERS",
    "E2B_DT_S",
    "E2B_FIELD_V_M",
    "E2B_LEFT_PP",
    "E2B_MOBILITY_M2_V_S",
    "E2B_RIGHT_PP",
    "E3_DT_S",
    "E3_FIELD_V_M",
    "E3_JOULE_POWER_PP",
    "E3_MOBILITY_M2_V_S",
    "ENERGY_WALL_THERMAL_POWER_PP",
    "SEE_ENERGY_COUPLED_POWER_PP",
    "Issue26EnergyChainError",
    "build_e2b_drift_input",
    "build_e3_joule_input",
    "build_e4_e5_wall_input",
]
