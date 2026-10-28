#!/usr/bin/env python3
"""Non-production O2+ dissociative recombination sensitivity overlay.

O2+ + e -> 2 O (coarse-grained O-equivalent product).
Peverall et al., JCP 114, 6679 (2001), DOI: 10.1063/1.1349079:
k = 2.4e-13 (300 K / T_e[K])**0.70 m3/s.

The fit is for predominantly ground-vibrational O2+ and is extrapolated
well beyond its independently validated thermal regime in typical ICP.
Excited product branching is NOT represented. No canonical science PASS.
"""
from __future__ import annotations

import argparse
from pathlib import Path

K300_M3_S = 2.4e-13
EXPONENT = 0.70
KELVIN_PER_EV = 11604.518121550082
M_O = 0.016
M_O2P = 0.032

REQUIRED = (
    "[log_ne]",
    "[log_ni]",
    "[log_energy]",
    "[w_O]",
    "[p]",
    "property_name = n_e_physical",
    "mean_energy = mean_en_solved",
)


def rate_m3_s(mean_energy_ev: float) -> float:
    """Thermal-fit extrapolation using T_e = (2/3)*mean_energy in eV."""
    import math
    if not math.isfinite(mean_energy_ev) or mean_energy_ev <= 0.0:
        raise ValueError("positive finite mean electron energy required")
    electron_temperature_k = KELVIN_PER_EV * (2.0 / 3.0) * mean_energy_ev
    return K300_M3_S * (300.0 / electron_temperature_k) ** EXPONENT


def build(base: str) -> str:
    missing = [token for token in REQUIRED if token not in base]
    if missing:
        raise ValueError(f"O2+ DR prerequisite fields absent: {missing}")
    if "R_o2p_dr" in base or "S_O_mass_o2p_dr" in base:
        raise ValueError("O2+ DR progress or source already exists in base")

    return f'''# EXPERIMENTAL O2+ DR ON ONLY; leave canonical oxygen chemistry unchanged.
# O2+ + e -> O + O in coarse-grained O-equivalent species.
# Literature: Peverall et al. J. Chem. Phys. 114, 6679 (2001).
# Rate: 2.4e-13*(300/Te[K])^0.70 m3/s; Te[K]=(2/3)*mean_en[eV]*11604.518...
# NOTICE: ICP electron temperature extrapolation; product-state branching unknown.
# Energy source -mean_en*R is a controlled removed-electron mean-energy proxy.
# n_e_physical [1/m3], exp(log_ni) [mol/m3]; R [mol/(m3 s)].
[FunctorMaterials]
  [o2p_dr_progress]
    type = ADParsedFunctorMaterial
    property_name = R_o2p_dr
    functor_names = 'n_e_physical log_ni mean_en_solved'
    functor_symbols = 'ne lni eps'
    expression = '{K300_M3_S:.17g}*ne*exp(lni)*(300.0/({KELVIN_PER_EV:.17g}*(2.0/3.0)*eps))^({EXPONENT:.17g})'
    block = plasma
  []
  [o2p_dr_electron_sink]
    type = ADParsedFunctorMaterial
    property_name = S_e_mol_o2p_dr
    functor_names = 'R_o2p_dr'
    functor_symbols = 'R'
    expression = '-R'
    block = plasma
  []
  [o2p_dr_ion_sink]
    type = ADParsedFunctorMaterial
    property_name = S_O2p_mol_o2p_dr
    functor_names = 'R_o2p_dr'
    functor_symbols = 'R'
    expression = '-R'
    block = plasma
  []
  [o2p_dr_atomic_oxygen_source]
    type = ADParsedFunctorMaterial
    property_name = S_O_mass_o2p_dr
    functor_names = 'R_o2p_dr'
    functor_symbols = 'R'
    expression = '{2.0*M_O:.17g}*R'
    block = plasma
  []
  [o2p_dr_neutral_mass_source]
    type = ADParsedFunctorMaterial
    property_name = S_neutral_mass_o2p_dr
    functor_names = 'R_o2p_dr'
    functor_symbols = 'R'
    expression = '{M_O2P:.17g}*R'
    block = plasma
  []
  [o2p_dr_ion_mass_sink]
    type = ADParsedFunctorMaterial
    property_name = S_O2p_mass_o2p_dr
    functor_names = 'R_o2p_dr'
    functor_symbols = 'R'
    expression = '-{M_O2P:.17g}*R'
    block = plasma
  []
  [o2p_dr_energy_sink]
    type = ADParsedFunctorMaterial
    property_name = S_energy_mol_o2p_dr
    functor_names = 'R_o2p_dr mean_en_solved'
    functor_symbols = 'R eps'
    expression = '-eps*R'
    block = plasma
  []
  [o2p_dr_mass_closure]
    type = ADParsedFunctorMaterial
    property_name = S_heavy_mass_closure_o2p_dr
    functor_names = 'S_neutral_mass_o2p_dr S_O2p_mass_o2p_dr'
    functor_symbols = 'Sn Si'
    expression = 'Sn+Si'
    block = plasma
  []
  [o2p_dr_charge_closure]
    type = ADParsedFunctorMaterial
    property_name = S_charge_mol_closure_o2p_dr
    functor_names = 'S_O2p_mol_o2p_dr S_e_mol_o2p_dr'
    functor_symbols = 'Si Se'
    expression = 'Si-Se'
    block = plasma
  []
[]
[Kernels]
  [o2p_dr_electron_particle_sink]
    type = FunctorKernel
    variable = log_ne
    functor = S_e_mol_o2p_dr
    functor_on_rhs = true
    block = plasma
  []
  [o2p_dr_electron_energy_sink]
    type = FunctorKernel
    variable = log_energy
    functor = S_energy_mol_o2p_dr
    functor_on_rhs = true
    block = plasma
  []
[]
[FVKernels]
  [o2p_dr_o_mass_source]
    type = PhysicsFVSpeciesReactionSource
    variable = w_O
    source = S_O_mass_o2p_dr
    block = plasma
  []
  [o2p_dr_o2p_sink]
    type = FVCoupledForce
    variable = log_ni
    v = S_O2p_mol_o2p_dr
    coef = 1.0
    block = plasma
  []
  [o2p_dr_neutral_mass]
    type = FVCoupledForce
    variable = p
    v = S_neutral_mass_o2p_dr
    coef = 1.0
    block = plasma
  []
[]
[Postprocessors]
  [o2p_dr_R_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = R_o2p_dr
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [o2p_dr_O_source_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_O_mass_o2p_dr
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [o2p_dr_electron_sink_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_e_mol_o2p_dr
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [o2p_dr_ion_sink_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_O2p_mol_o2p_dr
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [o2p_dr_energy_sink_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_energy_mol_o2p_dr
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [o2p_dr_mass_closure_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_heavy_mass_closure_o2p_dr
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [o2p_dr_charge_closure_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_charge_mol_closure_o2p_dr
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [o2p_dr_R_max]
    type = ADElementExtremeFunctorValue
    functor = R_o2p_dr
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]
'''


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--base-input", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    a = p.parse_args()
    overlay = build(a.base_input.read_text(encoding="utf-8"))
    a.output.write_text(overlay, encoding="utf-8")
    print("O2P_DR_EXPERIMENTAL_OVERLAY_GENERATED")
    print(f"output={a.output}")
    print("science_status=THERMAL_EXTRAPOLATION_AND_BRANCHING_HOLD")


if __name__ == "__main__":
    main()
