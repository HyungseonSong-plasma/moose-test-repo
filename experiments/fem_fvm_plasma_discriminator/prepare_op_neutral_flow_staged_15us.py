#!/usr/bin/env python3
"""Issue #331 Stage B: add neutral flow/species to the Stage-A charged DD baseline.

Charged species remain independent number-density drift-diffusion states:
  O2+, O-, O+.

Neutral flow uses a Q-1 mass-fraction closure:
  solved:      O2*, O, O*
  constrained: O2 = 1 - w_O2* - w_O - w_O*

The legacy seven-heavy-species inlet recipe assigned 3% mass fraction to
charged species. Because charged species are no longer neutral-flow mass
fractions in this architecture, the neutral ratios are renormalized to one.

The 15 us time sequence is inherited byte-for-byte in time from the accepted
Stage-A long-horizon discriminator.
"""
from pathlib import Path
import math

import prepare_cases as base
import prepare_op_fvm_hybrid_staged_15us as staged

Q_SCCM = 100.0
VM_STD = 0.0224136
MU_FLOW = 2.0e-5
OUTLET_PRESSURE = base.PRESSURE
TG = base.TG

RAW_NEUTRAL = {
    "O2": 0.70,
    "O2s": 0.05,
    "O": 0.10,
    "Os": 0.12,
}
RAW_NEUTRAL_SUM = sum(RAW_NEUTRAL.values())
Y = {name: value / RAW_NEUTRAL_SUM for name, value in RAW_NEUTRAL.items()}

Y_O2 = Y["O2"]
Y_O2S = Y["O2s"]
Y_O = Y["O"]
Y_OS = Y["Os"]

M_INLET = 1.0 / (
    Y_O2 / 0.032
    + Y_O2S / 0.032
    + Y_O / 0.016
    + Y_OS / 0.016
)
Q_STD = Q_SCCM * 1.0e-6 / 60.0
INLET_MDOT = Q_STD * M_INLET / VM_STD
INLET_MDOT_O2 = INLET_MDOT * Y_O2
INLET_MDOT_O2S = INLET_MDOT * Y_O2S
INLET_MDOT_O = INLET_MDOT * Y_O
INLET_MDOT_OS = INLET_MDOT * Y_OS

CASE_NAME = "ion_om_op_neutral_flow_contour_staged_1ns100_10ns90_100ns90_1000ns5"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"expected exactly one {label}, found {count}")
    return text.replace(old, new, 1)


def validate_analytic_constraints() -> None:
    s = Y_O2 + Y_O2S + Y_O + Y_OS
    if not math.isclose(s, 1.0, rel_tol=0.0, abs_tol=5.0e-16):
        raise RuntimeError(f"neutral inlet simplex not normalized: sum={s:.17g}")
    if min(Y.values()) <= 0.0:
        raise RuntimeError(f"neutral inlet fraction is non-positive: {Y}")

    mdot_sum = INLET_MDOT_O2 + INLET_MDOT_O2S + INLET_MDOT_O + INLET_MDOT_OS
    if not math.isclose(mdot_sum, INLET_MDOT, rel_tol=5.0e-16, abs_tol=1.0e-30):
        raise RuntimeError(
            f"inlet species mass-flow closure failed: species={mdot_sum:.17g}, "
            f"total={INLET_MDOT:.17g}"
        )

    # With O2/O2* at 0.032 kg/mol and O/O* at 0.016 kg/mol:
    #   Mn = 1 / [(1-A)/0.032 + A/0.016] = 0.032/(1+A),
    #   A = w_O + w_O*
    A = Y_O + Y_OS
    closed_form = 0.032 / (1.0 + A)
    if not math.isclose(M_INLET, closed_form, rel_tol=5.0e-15, abs_tol=0.0):
        raise RuntimeError(
            f"mean-molar-mass constraint mismatch: harmonic={M_INLET:.17g}, "
            f"closed={closed_form:.17g}"
        )


def build_case() -> str:
    validate_analytic_constraints()
    text = staged.build_case()

    pre_variables = f"""[GlobalParams]
  rhie_chow_user_object = rc
  advected_interp_method = upwind
  velocity_interp_method = rc
  two_term_boundary_expansion = true
[]

[UserObjects]
  [rc]
    type = INSFVRhieChowInterpolator
    u = u
    v = v
    pressure = p
    block = plasma
  []
[]

[Variables]
  [u]
    type = INSFVVelocityVariable
    initial_condition = 0.0
    block = plasma
  []
  [v]
    type = INSFVVelocityVariable
    initial_condition = 0.0
    block = plasma
  []
  [p]
    type = INSFVPressureVariable
    initial_condition = {OUTLET_PRESSURE:.17g}
    block = plasma
  []
  [w_O2s]
    type = INSFVScalarFieldVariable
    initial_condition = {Y_O2S:.17g}
    block = plasma
  []
  [w_O]
    type = INSFVScalarFieldVariable
    initial_condition = {Y_O:.17g}
    block = plasma
  []
  [w_Os]
    type = INSFVScalarFieldVariable
    initial_condition = {Y_OS:.17g}
    block = plasma
  []
"""
    text = replace_once(text, "[Variables]\n", pre_variables, "Variables header")

    # Stage A used fixed pressure only for electron transport. Replace that one
    # pressure dependency with the nonlinear neutral-flow pressure.
    text = replace_once(
        text,
        "    pressure = p_fixed\n    gas_temperature = T_g_fixed\n",
        "    pressure = p\n    gas_temperature = T_g_fixed\n",
        "electron-transport pressure coupling",
    )

    neutral_materials = f"""
  [neutral_flow_constants]
    type = ADGenericFunctorMaterial
    prop_names = 'mu_flow'
    prop_values = '{MU_FLOW:.17g}'
    block = plasma
  []

  [neutral_state_dot_aliases]
    type = ADGenericFunctorMaterial
    prop_names = 'p_state wO_state wOs_state'
    prop_values = 'p w_O w_Os'
    define_dot_functors = true
    block = plasma
  []

  [neutral_O2_constraint]
    type = ADParsedFunctorMaterial
    property_name = w_O2_constraint
    functor_names = 'w_O2s w_O w_Os'
    functor_symbols = 's o a'
    expression = '1.0-s-o-a'
    block = plasma
  []

  [neutral_mean_molar_mass]
    type = ADParsedFunctorMaterial
    property_name = Mn_neutral
    functor_names = 'w_O2_constraint w_O2s w_O w_Os'
    functor_symbols = 'm0 m1 m2 m3'
    expression = '1.0/(m0/0.032+m1/0.032+m2/0.016+m3/0.016)'
    block = plasma
  []

  [neutral_density]
    type = ADParsedFunctorMaterial
    property_name = rho_neutral
    functor_names = 'p Mn_neutral T_g_fixed'
    functor_symbols = 'prs mol tmp'
    expression = 'prs*mol/(8.31446*tmp)'
    block = plasma
  []

  # A = w_O + w_O*. Molecular redistribution O2 <-> O2* leaves Mn unchanged.
  # Mn = 0.032/(1+A), hence dMn/dt = -31.25*Mn^2*dA/dt.
  [neutral_mean_molar_mass_dot]
    type = ADParsedFunctorMaterial
    property_name = dMn_neutral_dt
    functor_names = 'Mn_neutral dwO_state_dt dwOs_state_dt'
    functor_symbols = 'mn dwo dwos'
    expression = '-31.25*mn*mn*(dwo+dwos)'
    block = plasma
  []

  # Isothermal Stage-B flow: rho = p*Mn/(R*Tg).
  [neutral_density_dot]
    type = ADParsedFunctorMaterial
    property_name = drho_neutral_dt
    functor_names = 'p Mn_neutral dp_state_dt dMn_neutral_dt T_g_fixed'
    functor_symbols = 'prs mn dp dmn tmp'
    expression = '(mn*dp+prs*dmn)/(8.31446*tmp)'
    block = plasma
  []

  [neutral_sum_w]
    type = ADParsedFunctorMaterial
    property_name = neutral_sum_w_functor
    functor_names = 'w_O2_constraint w_O2s w_O w_Os'
    functor_symbols = 'q0 q1 q2 q3'
    expression = 'q0+q1+q2+q3'
    block = plasma
  []

  [rho_w_O2]
    type = ADParsedFunctorMaterial
    property_name = rho_w_O2
    functor_names = 'rho_neutral w_O2_constraint'
    functor_symbols = 'rho w'
    expression = 'rho*w'
    block = plasma
  []
  [rho_w_O2s]
    type = ADParsedFunctorMaterial
    property_name = rho_w_O2s
    functor_names = 'rho_neutral w_O2s'
    functor_symbols = 'rho w'
    expression = 'rho*w'
    block = plasma
  []
  [rho_w_O]
    type = ADParsedFunctorMaterial
    property_name = rho_w_O
    functor_names = 'rho_neutral w_O'
    functor_symbols = 'rho w'
    expression = 'rho*w'
    block = plasma
  []
  [rho_w_Os]
    type = ADParsedFunctorMaterial
    property_name = rho_w_Os
    functor_names = 'rho_neutral w_Os'
    functor_symbols = 'rho w'
    expression = 'rho*w'
    block = plasma
  []

  [neutral_transport]
    type = PhysicsThermalDiffusionMaterial
    temperature = T_g_fixed
    pressure = p
    transport_data_file = '../Issue21_qvt_six_species_bulk_advection/transport_data.txt'
    species = 'O2 O2s O Os'
    mass_fractions = 'w_O2_constraint w_O2s w_O w_Os'
    D_mix_names = 'D_mix_O2 D_mix_O2s D_mix_O D_mix_Os'
    D_T_names = 'D_T_O2 D_T_O2s D_T_O D_T_Os'
    kT_names = 'kT_O2 kT_O2s kT_O kT_Os'
    block = plasma
  []
"""
    text = replace_once(
        text,
        "\n[]\n\n[Kernels]\n",
        neutral_materials + "\n[]\n\n[Kernels]\n",
        "FunctorMaterials closing block",
    )

    neutral_fv = """
  [neutral_mass_time]
    type = WCNSFVMassTimeDerivative
    variable = p
    drho_dt = drho_neutral_dt
    block = plasma
  []
  [neutral_mass_advection]
    type = INSFVMassAdvection
    variable = p
    rho = rho_neutral
    block = plasma
  []

  [u_advection]
    type = INSFVMomentumAdvection
    variable = u
    rho = rho_neutral
    momentum_component = x
    block = plasma
  []
  [u_diffusion]
    type = INSFVMomentumDiffusion
    variable = u
    mu = mu_flow
    momentum_component = x
    block = plasma
  []
  [u_pressure]
    type = INSFVMomentumPressure
    variable = u
    pressure = p
    momentum_component = x
    block = plasma
  []
  [v_advection]
    type = INSFVMomentumAdvection
    variable = v
    rho = rho_neutral
    momentum_component = y
    block = plasma
  []
  [v_diffusion]
    type = INSFVMomentumDiffusion
    variable = v
    mu = mu_flow
    momentum_component = y
    block = plasma
  []
  [v_pressure]
    type = INSFVMomentumPressure
    variable = v
    pressure = p
    momentum_component = y
    block = plasma
  []
  [u_rz_viscous_source]
    type = INSFVMomentumViscousSourceRZ
    variable = u
    mu = mu_flow
    momentum_component = x
    block = plasma
  []

  [O2s_time]
    type = PhysicsFVConservativeMassFractionTimeDerivative
    variable = w_O2s
    rho = rho_neutral
    block = plasma
  []
  [O2s_advection]
    type = PhysicsFVMassFractionAdvection
    variable = w_O2s
    rho = rho_neutral
    block = plasma
  []
  [O2s_diffusion]
    type = PhysicsFVMixtureAveragedDiffusion
    variable = w_O2s
    rho = rho_neutral
    diffusivity = D_mix_O2s
    mean_molar_mass = Mn_neutral
    include_molar_mass_gradient = true
    block = plasma
  []

  [O_time]
    type = PhysicsFVConservativeMassFractionTimeDerivative
    variable = w_O
    rho = rho_neutral
    block = plasma
  []
  [O_advection]
    type = PhysicsFVMassFractionAdvection
    variable = w_O
    rho = rho_neutral
    block = plasma
  []
  [O_diffusion]
    type = PhysicsFVMixtureAveragedDiffusion
    variable = w_O
    rho = rho_neutral
    diffusivity = D_mix_O
    mean_molar_mass = Mn_neutral
    include_molar_mass_gradient = true
    block = plasma
  []

  [Os_time]
    type = PhysicsFVConservativeMassFractionTimeDerivative
    variable = w_Os
    rho = rho_neutral
    block = plasma
  []
  [Os_advection]
    type = PhysicsFVMassFractionAdvection
    variable = w_Os
    rho = rho_neutral
    block = plasma
  []
  [Os_diffusion]
    type = PhysicsFVMixtureAveragedDiffusion
    variable = w_Os
    rho = rho_neutral
    diffusivity = D_mix_Os
    mean_molar_mass = Mn_neutral
    include_molar_mass_gradient = true
    block = plasma
  []
"""
    text = replace_once(
        text,
        "\n[]\n\n[FVBCs]\n",
        neutral_fv + "\n[]\n\n[FVBCs]\n",
        "FVKernels closing block",
    )

    neutral_bcs = f"""
  [neutral_inlet_mass]
    type = WCNSFVMassFluxBC
    variable = p
    boundary = inlet
    mdot_pp = neutral_inlet_mdot
    area_pp = neutral_inlet_area
    rho = rho_neutral
    vel_x = u
    vel_y = v
    direction = '-1 0 0'
  []
  [neutral_inlet_u]
    type = WCNSFVMomentumFluxBC
    variable = u
    boundary = inlet
    mdot_pp = neutral_inlet_mdot
    area_pp = neutral_inlet_area
    rho = rho_neutral
    vel_x = u
    vel_y = v
    momentum_component = x
    direction = '-1 0 0'
  []
  [neutral_inlet_v]
    type = WCNSFVMomentumFluxBC
    variable = v
    boundary = inlet
    mdot_pp = neutral_inlet_mdot
    area_pp = neutral_inlet_area
    rho = rho_neutral
    vel_x = u
    vel_y = v
    momentum_component = y
    direction = '-1 0 0'
  []

  [neutral_inlet_O2s]
    type = WCNSFVScalarFluxBC
    variable = w_O2s
    boundary = inlet
    passive_scalar = w_O2s
    scalar_flux_pp = neutral_inlet_mdot_O2s
    area_pp = neutral_inlet_area
    rho = rho_neutral
    vel_x = u
    vel_y = v
    direction = '-1 0 0'
  []
  [neutral_inlet_O]
    type = WCNSFVScalarFluxBC
    variable = w_O
    boundary = inlet
    passive_scalar = w_O
    scalar_flux_pp = neutral_inlet_mdot_O
    area_pp = neutral_inlet_area
    rho = rho_neutral
    vel_x = u
    vel_y = v
    direction = '-1 0 0'
  []
  [neutral_inlet_Os]
    type = WCNSFVScalarFluxBC
    variable = w_Os
    boundary = inlet
    passive_scalar = w_Os
    scalar_flux_pp = neutral_inlet_mdot_Os
    area_pp = neutral_inlet_area
    rho = rho_neutral
    vel_x = u
    vel_y = v
    direction = '-1 0 0'
  []

  [neutral_wall_u]
    type = INSFVNoSlipWallBC
    variable = u
    boundary = 'plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
    function = 0
  []
  [neutral_wall_v]
    type = INSFVNoSlipWallBC
    variable = v
    boundary = 'plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'
    function = 0
  []
  [neutral_outlet_p]
    type = INSFVOutletPressureBC
    variable = p
    boundary = outlet
    function = {OUTLET_PRESSURE:.17g}
  []
"""
    text = replace_once(
        text,
        "\n[]\n\n[Postprocessors]\n",
        neutral_bcs + "\n[]\n\n[Postprocessors]\n",
        "FVBCs closing block",
    )

    neutral_pp = f"""
  [neutral_inlet_area]
    type = AreaPostprocessor
    boundary = inlet
    execute_on = INITIAL
  []
  [neutral_inlet_mdot]
    type = Receiver
    default = {INLET_MDOT:.17g}
  []
  [neutral_inlet_mdot_O2]
    type = Receiver
    default = {INLET_MDOT_O2:.17g}
  []
  [neutral_inlet_mdot_O2s]
    type = Receiver
    default = {INLET_MDOT_O2S:.17g}
  []
  [neutral_inlet_mdot_O]
    type = Receiver
    default = {INLET_MDOT_O:.17g}
  []
  [neutral_inlet_mdot_Os]
    type = Receiver
    default = {INLET_MDOT_OS:.17g}
  []

  [neutral_outlet_mass]
    type = VolumetricFlowRate
    boundary = outlet
    vel_x = u
    vel_y = v
    advected_quantity = rho_neutral
    rhie_chow_user_object = rc
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [neutral_outlet_mdot_O2]
    type = VolumetricFlowRate
    boundary = outlet
    vel_x = u
    vel_y = v
    advected_quantity = rho_w_O2
    rhie_chow_user_object = rc
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [neutral_outlet_mdot_O2s]
    type = VolumetricFlowRate
    boundary = outlet
    vel_x = u
    vel_y = v
    advected_quantity = rho_w_O2s
    rhie_chow_user_object = rc
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [neutral_outlet_mdot_O]
    type = VolumetricFlowRate
    boundary = outlet
    vel_x = u
    vel_y = v
    advected_quantity = rho_w_O
    rhie_chow_user_object = rc
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [neutral_outlet_mdot_Os]
    type = VolumetricFlowRate
    boundary = outlet
    vel_x = u
    vel_y = v
    advected_quantity = rho_w_Os
    rhie_chow_user_object = rc
    execute_on = 'INITIAL TIMESTEP_END'
  []

  [neutral_sum_w_min]
    type = ADElementExtremeFunctorValue
    functor = neutral_sum_w_functor
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [neutral_sum_w_max]
    type = ADElementExtremeFunctorValue
    functor = neutral_sum_w_functor
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []

  [w_O2_min]
    type = ADElementExtremeFunctorValue
    functor = w_O2_constraint
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [w_O2_max]
    type = ADElementExtremeFunctorValue
    functor = w_O2_constraint
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [w_O2s_min]
    type = ADElementExtremeFunctorValue
    functor = w_O2s
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [w_O2s_max]
    type = ADElementExtremeFunctorValue
    functor = w_O2s
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [w_O_min]
    type = ADElementExtremeFunctorValue
    functor = w_O
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [w_O_max]
    type = ADElementExtremeFunctorValue
    functor = w_O
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [w_Os_min]
    type = ADElementExtremeFunctorValue
    functor = w_Os
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [w_Os_max]
    type = ADElementExtremeFunctorValue
    functor = w_Os
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []

  [neutral_Mn_min]
    type = ADElementExtremeFunctorValue
    functor = Mn_neutral
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [neutral_Mn_max]
    type = ADElementExtremeFunctorValue
    functor = Mn_neutral
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [neutral_rho_min]
    type = ADElementExtremeFunctorValue
    functor = rho_neutral
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [neutral_rho_max]
    type = ADElementExtremeFunctorValue
    functor = rho_neutral
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [neutral_p_min]
    type = ADElementExtremeFunctorValue
    functor = p
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [neutral_p_max]
    type = ADElementExtremeFunctorValue
    functor = p
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [neutral_u_min]
    type = ADElementExtremeFunctorValue
    functor = u
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [neutral_u_max]
    type = ADElementExtremeFunctorValue
    functor = u
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [neutral_v_min]
    type = ADElementExtremeFunctorValue
    functor = v
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [neutral_v_max]
    type = ADElementExtremeFunctorValue
    functor = v
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []

  [neutral_mass_total]
    type = ADElementIntegralFunctorPostprocessor
    functor = rho_neutral
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [neutral_mass_O2]
    type = ADElementIntegralFunctorPostprocessor
    functor = rho_w_O2
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [neutral_mass_O2s]
    type = ADElementIntegralFunctorPostprocessor
    functor = rho_w_O2s
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [neutral_mass_O]
    type = ADElementIntegralFunctorPostprocessor
    functor = rho_w_O
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [neutral_mass_Os]
    type = ADElementIntegralFunctorPostprocessor
    functor = rho_w_Os
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
"""
    text = replace_once(
        text,
        "\n[]\n[Executioner]\n",
        neutral_pp + "\n[]\n[Executioner]\n",
        "Postprocessors closing block",
    )

    return text


def validate_generated_contract(text: str) -> None:
    required = (
        "[rc]",
        "[u]",
        "[v]",
        "[p]",
        "[w_O2s]",
        "[w_O]",
        "[w_Os]",
        "expression = '1.0-s-o-a'",
        "property_name = drho_neutral_dt",
        "type = WCNSFVMassTimeDerivative",
        "type = PhysicsFVConservativeMassFractionTimeDerivative",
        "type = PhysicsFVMassFractionAdvection",
        "type = PhysicsFVMixtureAveragedDiffusion",
        "pressure = p",
        "species = 'O2 O2s O Os'",
        "expression = 'ni+nop-ne-nm'",
        "type = TimeSequenceStepper",
    )
    for token in required:
        if token not in text:
            raise RuntimeError(f"missing Stage-B neutral-flow contract token: {token}")

    forbidden_neutral_vars = ("[w_O2p]", "[w_Om]", "[w_Op]")
    for token in forbidden_neutral_vars:
        if token in text:
            raise RuntimeError(
                f"charged species leaked back into neutral-flow mass-fraction variables: {token}"
            )

    # Charged DD ownership must be untouched.
    for variable in ("log_ni", "log_nm", "log_nop"):
        if f"variable = {variable}" not in text:
            raise RuntimeError(f"missing charged DD variable ownership for {variable}")
    for kernel, charge in (("[ni_drift]", "1"), ("[nm_drift]", "-1"), ("[nop_drift]", "1")):
        section = text.split(kernel, 1)[1].split("  []", 1)[0]
        if f"charge_number = {charge}" not in section:
            raise RuntimeError(f"{kernel} charge sign changed")

    if text.count("pressure = p\n    gas_temperature = T_g_fixed") != 1:
        raise RuntimeError("electron transport is not coupled exactly once to nonlinear pressure")


def main() -> None:
    text = build_case()
    validate_generated_contract(text)

    out = Path(base.HERE) / f"{CASE_NAME}.i"
    out.write_text(text, encoding="utf-8")

    print(f"wrote {out}")
    print("Stage B ownership: charged O2+/O-/O+ remain DD; neutral O2/O2*/O/O* use flow/species transport")
    print("neutral Q-1 closure: O2 = 1 - O2* - O - O*")
    print(f"raw neutral sum before normalization={RAW_NEUTRAL_SUM:.17g}")
    print(
        "normalized neutral mass fractions: "
        f"O2={Y_O2:.17g} O2*={Y_O2S:.17g} O={Y_O:.17g} O*={Y_OS:.17g}"
    )
    print(f"normalized neutral sum={Y_O2 + Y_O2S + Y_O + Y_OS:.17g}")
    print(f"neutral mean molar mass kg/mol={M_INLET:.17g}")
    print(f"inlet total mdot kg/s={INLET_MDOT:.17g}")
    print(
        "inlet species mdot kg/s: "
        f"O2={INLET_MDOT_O2:.17g} O2*={INLET_MDOT_O2S:.17g} "
        f"O={INLET_MDOT_O:.17g} O*={INLET_MDOT_OS:.17g}"
    )
    print(
        "inlet species mdot closure kg/s="
        f"{INLET_MDOT_O2 + INLET_MDOT_O2S + INLET_MDOT_O + INLET_MDOT_OS:.17g}"
    )
    print("density derivative: drho/dt = (Mn*dp/dt + p*dMn/dt)/(R*Tg)")
    print("dMn/dt = -31.25*Mn^2*(dw_O/dt + dw_O*/dt)")
    print("time schedule inherited: 1nsx100 + 10nsx90 + 100nsx90 + 1000nsx5 = 15us")


if __name__ == "__main__":
    main()
