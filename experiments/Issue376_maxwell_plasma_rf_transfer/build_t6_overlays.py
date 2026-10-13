#!/usr/bin/env python3
"""Build standard-MOOSE T6 spatial-conductivity overlays for Issue #376.

No custom C++ is required.  The state transfer uses SolutionUserObject/SolutionAux,
the exact electron-mobility table uses PiecewiseLinearInterpolationMaterial, and
ParsedMaterial performs the Drude algebra.
"""
from __future__ import annotations

import argparse
from pathlib import Path


def table(path: Path) -> tuple[list[float], list[float]]:
    x: list[float] = []
    y: list[float] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        c = s.replace(",", " ").split()
        if len(c) < 2:
            continue
        x.append(float(c[0]))
        y.append(float(c[1]))
    if len(x) < 2 or any(x[i + 1] <= x[i] for i in range(len(x) - 1)):
        raise RuntimeError("invalid electron mobility table")
    return x, y


def vals(v: list[float]) -> str:
    return " ".join(format(z, ".17g") for z in v)


def maxwell_overlay(x: list[float], mu_n: list[float]) -> str:
    xs = vals(x)
    ys = vals(mu_n)
    return f"""# Issue #376 T6 spatial-state Maxwell overlay.
# Applied after Issue202_maxwell_scalar_fem_m0/rf_power.i.
plasma_solution_file_t6 = 'results_t6/bootstrap/state100ns.e'

[AuxVariables]
  [log_ne_state_t6]
    family = LAGRANGE
    order = FIRST
    block = plasma
  []
  [log_energy_state_t6]
    family = LAGRANGE
    order = FIRST
    block = plasma
  []
  [pressure_state_t6]
    family = MONOMIAL
    order = CONSTANT
    block = plasma
  []
  [mean_energy_state_t6]
    family = LAGRANGE
    order = FIRST
    block = plasma
  []
[]

[UserObjects]
  [plasma_state_t6]
    type = SolutionUserObject
    mesh = '${{plasma_solution_file_t6}}'
    system_variables = 'log_ne log_energy p'
    timestep = LATEST
    execute_on = INITIAL
  []
[]

[AuxKernels]
  [map_log_ne_t6]
    type = SolutionAux
    variable = log_ne_state_t6
    solution = plasma_state_t6
    from_variable = log_ne
    execute_on = INITIAL
  []
  [map_log_energy_t6]
    type = SolutionAux
    variable = log_energy_state_t6
    solution = plasma_state_t6
    from_variable = log_energy
    execute_on = INITIAL
  []
  [map_pressure_t6]
    type = SolutionAux
    variable = pressure_state_t6
    solution = plasma_state_t6
    from_variable = p
    execute_on = INITIAL
  []
  [mean_energy_t6]
    type = ParsedAux
    variable = mean_energy_state_t6
    coupled_variables = 'log_ne_state_t6 log_energy_state_t6'
    expression = 'exp(log_energy_state_t6-log_ne_state_t6)'
    execute_on = INITIAL
    block = plasma
  []
[]

[Functions]
  active = 'zero_fn neg_a_vac_fn neg_a_cover_fn neg_a_wafer_fn neg_a_focus_fn neg_a_plasma_geom_t6'
  [neg_a_plasma_geom_t6]
    type = ParsedFunction
    expression = '-(1/(x*x) - k2*epsr)'
    symbol_names = 'k2 epsr'
    symbol_values = '${{wave_k2}} ${{plasma_eps_r}}'
  []
[]

[Materials]
  active = 'vacuum_like cover wafer focus_ring plasma_geom_t6 muN_t6 sigma_real_t6 sigma_imag_t6 plasma_neg_a_t6 plasma_b_t6 rf_power_density_t6'
  [plasma_geom_t6]
    type = GenericFunctionMaterial
    prop_names = 'neg_a_geom_t6'
    prop_values = 'neg_a_plasma_geom_t6'
    block = plasma
  []
  [muN_t6]
    type = PiecewiseLinearInterpolationMaterial
    property = muN_t6
    variable = mean_energy_state_t6
    x = '{xs}'
    y = '{ys}'
    block = plasma
  []
  [sigma_real_t6]
    type = ParsedMaterial
    property_name = sigma_real_t6
    coupled_variables = 'log_ne_state_t6 pressure_state_t6'
    material_property_names = 'muN_t6'
    constant_names = 'NA qe me kb Tg om'
    constant_expressions = '6.02214076e23 1.602176634e-19 9.1093837015e-31 1.380649e-23 300 ${{omega}}'
    expression = '(exp(log_ne_state_t6)*NA*qe^2*(qe/(me*(muN_t6/(pressure_state_t6/(kb*Tg))))))/(me*((qe/(me*(muN_t6/(pressure_state_t6/(kb*Tg)))))^2+om^2))'
    block = plasma
  []
  [sigma_imag_t6]
    type = ParsedMaterial
    property_name = sigma_imag_t6
    coupled_variables = 'log_ne_state_t6 pressure_state_t6'
    material_property_names = 'muN_t6'
    constant_names = 'NA qe me kb Tg om'
    constant_expressions = '6.02214076e23 1.602176634e-19 9.1093837015e-31 1.380649e-23 300 ${{omega}}'
    expression = '-(exp(log_ne_state_t6)*NA*qe^2*om)/(me*((qe/(me*(muN_t6/(pressure_state_t6/(kb*Tg)))))^2+om^2))'
    block = plasma
  []
  [plasma_neg_a_t6]
    type = ParsedMaterial
    property_name = neg_a
    material_property_names = 'neg_a_geom_t6 sigma_imag_t6'
    constant_names = 'ommu'
    constant_expressions = '${{omega_mu0}}'
    expression = 'neg_a_geom_t6 + ommu*sigma_imag_t6'
    block = plasma
  []
  [plasma_b_t6]
    type = ParsedMaterial
    property_name = b
    material_property_names = 'sigma_real_t6'
    constant_names = 'ommu'
    constant_expressions = '${{omega_mu0}}'
    expression = 'ommu*sigma_real_t6'
    block = plasma
  []
  [rf_power_density_t6]
    type = ParsedMaterial
    property_name = q_rf
    coupled_variables = 'E_real E_imag'
    material_property_names = 'sigma_real_t6'
    expression = '0.5*sigma_real_t6*(E_real^2 + E_imag^2)'
    block = plasma
  []
[]
"""


def plasma_overlay(x: list[float], mu_n: list[float]) -> str:
    xs = vals(x)
    ys = vals(mu_n)
    return f"""# Issue #376 T6 full oxygen-ICP RF-heating overlay.
# Applied after the generated Issue #3 full-dielectric 100 ns baseline input.
rf_scale_t6 = 1.0
source_enable_t6 = 0.0
faraday_t6 = 96485.33212331001
maxwell_solution_file_t6 = 'results_t6/seed/maxwell.e'

[AuxVariables]
  [E_real_rf_t6]
    family = LAGRANGE
    order = FIRST
    block = plasma
  []
  [E_imag_rf_t6]
    family = LAGRANGE
    order = FIRST
    block = plasma
  []
  [log_ne_rf_state_t6]
    family = LAGRANGE
    order = FIRST
    block = plasma
  []
  [log_energy_rf_state_t6]
    family = LAGRANGE
    order = FIRST
    block = plasma
  []
  [pressure_rf_state_t6]
    family = MONOMIAL
    order = CONSTANT
    block = plasma
  []
  [mean_energy_rf_state_t6]
    family = LAGRANGE
    order = FIRST
    block = plasma
  []
[]

[UserObjects]
  [maxwell_solution_t6]
    type = SolutionUserObject
    mesh = '${{maxwell_solution_file_t6}}'
    system_variables = 'E_real E_imag'
    timestep = LATEST
    execute_on = 'INITIAL TIMESTEP_BEGIN'
  []
[]

[AuxKernels]
  [map_E_real_t6]
    type = SolutionAux
    variable = E_real_rf_t6
    solution = maxwell_solution_t6
    from_variable = E_real
    execute_on = 'INITIAL TIMESTEP_BEGIN'
  []
  [map_E_imag_t6]
    type = SolutionAux
    variable = E_imag_rf_t6
    solution = maxwell_solution_t6
    from_variable = E_imag
    execute_on = 'INITIAL TIMESTEP_BEGIN'
  []
  [freeze_log_ne_t6]
    type = ParsedAux
    variable = log_ne_rf_state_t6
    coupled_variables = 'log_ne'
    expression = 'log_ne'
    execute_on = 'INITIAL TIMESTEP_BEGIN'
    block = plasma
  []
  [freeze_log_energy_t6]
    type = ParsedAux
    variable = log_energy_rf_state_t6
    coupled_variables = 'log_energy'
    expression = 'log_energy'
    execute_on = 'INITIAL TIMESTEP_BEGIN'
    block = plasma
  []
  [freeze_pressure_t6]
    type = ParsedAux
    variable = pressure_rf_state_t6
    coupled_variables = 'p'
    expression = 'p'
    execute_on = 'INITIAL TIMESTEP_BEGIN'
    block = plasma
  []
  [mean_energy_rf_state_t6_aux]
    type = ParsedAux
    variable = mean_energy_rf_state_t6
    coupled_variables = 'log_ne_rf_state_t6 log_energy_rf_state_t6'
    expression = 'exp(log_energy_rf_state_t6-log_ne_rf_state_t6)'
    execute_on = 'INITIAL TIMESTEP_BEGIN'
    block = plasma
  []
[]

[Materials]
  [muN_rf_t6]
    type = PiecewiseLinearInterpolationMaterial
    property = muN_rf_t6
    variable = mean_energy_rf_state_t6
    x = '{xs}'
    y = '{ys}'
    block = plasma
  []
  [sigma_real_rf_t6]
    type = ParsedMaterial
    property_name = sigma_real_rf_t6
    coupled_variables = 'log_ne_rf_state_t6 pressure_rf_state_t6'
    material_property_names = 'muN_rf_t6'
    constant_names = 'NA qe me kb Tg om'
    constant_expressions = '6.02214076e23 1.602176634e-19 9.1093837015e-31 1.380649e-23 300 85199992.765355185'
    expression = '(exp(log_ne_rf_state_t6)*NA*qe^2*(qe/(me*(muN_rf_t6/(pressure_rf_state_t6/(kb*Tg))))))/(me*((qe/(me*(muN_rf_t6/(pressure_rf_state_t6/(kb*Tg)))))^2+om^2))'
    block = plasma
  []
  [q_rf_raw_t6]
    type = ParsedMaterial
    property_name = q_rf_raw_t6
    coupled_variables = 'E_real_rf_t6 E_imag_rf_t6'
    material_property_names = 'sigma_real_rf_t6'
    expression = '0.5*sigma_real_rf_t6*(E_real_rf_t6^2 + E_imag_rf_t6^2)'
    block = plasma
  []
  [q_rf_scaled_t6]
    type = ParsedMaterial
    property_name = q_rf_scaled_t6
    coupled_variables = 'E_real_rf_t6 E_imag_rf_t6'
    material_property_names = 'sigma_real_rf_t6'
    constant_names = 'scale'
    constant_expressions = '${{rf_scale_t6}}'
    expression = 'scale*0.5*sigma_real_rf_t6*(E_real_rf_t6^2 + E_imag_rf_t6^2)'
    block = plasma
  []
  [q_rf_eV_mol_t6]
    type = ParsedMaterial
    property_name = q_rf_eV_mol_t6
    coupled_variables = 'E_real_rf_t6 E_imag_rf_t6'
    material_property_names = 'sigma_real_rf_t6'
    constant_names = 'scale enabled F'
    constant_expressions = '${{rf_scale_t6}} ${{source_enable_t6}} ${{faraday_t6}}'
    expression = 'enabled*scale*0.5*sigma_real_rf_t6*(E_real_rf_t6^2 + E_imag_rf_t6^2)/F'
    block = plasma
  []
[]

[Kernels]
  [rf_heating_t6]
    type = MatBodyForce
    variable = log_energy
    material_property = q_rf_eV_mol_t6
    block = plasma
  []
[]

[Postprocessors]
  [P_rf_raw_W_t6]
    type = ElementIntegralMaterialProperty
    mat_prop = q_rf_raw_t6
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [P_rf_scaled_W_t6]
    type = ElementIntegralMaterialProperty
    mat_prop = q_rf_scaled_t6
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [S_rf_eV_mol_s_t6]
    type = ElementIntegralMaterialProperty
    mat_prop = q_rf_eV_mol_t6
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [mean_energy_rf_state_min_t6]
    type = ElementExtremeValue
    variable = mean_energy_rf_state_t6
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [mean_energy_rf_state_max_t6]
    type = ElementExtremeValue
    variable = mean_energy_rf_state_t6
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]

[Outputs]
  checkpoint = true
  execute_on = 'INITIAL TIMESTEP_END'
[]
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", type=Path, required=True)
    ap.add_argument("--maxwell-overlay", type=Path, required=True)
    ap.add_argument("--plasma-overlay", type=Path, required=True)
    a = ap.parse_args()
    x, mu_n = table(a.table)
    a.maxwell_overlay.parent.mkdir(parents=True, exist_ok=True)
    a.plasma_overlay.parent.mkdir(parents=True, exist_ok=True)
    a.maxwell_overlay.write_text(maxwell_overlay(x, mu_n), encoding="utf-8")
    a.plasma_overlay.write_text(plasma_overlay(x, mu_n), encoding="utf-8")
    print(
        "T6_OVERLAY_BUILD_PASS "
        f"table_points={len(x)} energy_range_eV=[{x[0]:.9g},{x[-1]:.9g}] "
        "standard_solution_transfer=true standard_piecewise_linear_material=true custom_cpp=false"
    )


if __name__ == "__main__":
    main()
