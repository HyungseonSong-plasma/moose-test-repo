#!/usr/bin/env python3
"""Build the Issue #395 source-backed O2 dissociation overlay.

The overlay is intended to be present from t=0 of a fresh powered trajectory.
It adds one canonical dissociation progress owner, the O mass projection through
the existing Q-1 O2 closure, and the electron-energy sink.  It does not add an
electron-particle source because e + O2 -> e + 2O has zero net electron stoich.
"""
from __future__ import annotations

import argparse
from pathlib import Path

M_O = 0.016
M_O2 = 0.032
DISS_RATE_PREF_M3_S = 1.41e-15
DISS_FIT_EXP_ENERGY_EV = 2.98
DISS_TE_EXPONENT = -0.22
DISS_ENERGY_LOSS_EV = 6.0

REQUIRED_BASE_TOKENS = (
    "[w_O]",
    "property_name = w_O2_constraint",
    "property_name = n_e_physical",
    "type = PhysicsElectronMeanEnergyMaterial",
    "mean_energy = mean_en_solved",
    "[log_energy]",
)

FORBIDDEN_BASE_TOKENS = (
    "R_diss_O2",
    "S_O_mass_diss",
    "diss_o2_progress",
)


# New *separate* product-state channel, not a replacement for the accepted
# ground-state 2O(3P) channel.  This exploratory fit was used as a Maxwellian
# comparison in Excitation Kinetics of Oxygen O(1D) State in Low-Pressure
# Oxygen Plasma (2017), doi:10.1515/jaots-2017-0002.
# k=3.49e-8*exp(-5.92/Te[eV]) cm3/s = 3.49e-14 ... m3/s.
# COMSOL Ar/O2 ICP electron-impact table, reaction 14: 8.4 eV/event.
MIXED_RATE_PREF_M3_S = 3.49e-14
MIXED_FIT_ENERGY_EV = 5.92
MIXED_ENERGY_LOSS_EV = 8.4


def build_mixed_dissociation_overlay(base: str) -> str:
    """One O(3P) + one O(1D) per O2; no new species or electron source."""
    needed = REQUIRED_BASE_TOKENS + (
        "[w_Os]",
        "property_name = rho_neutral",
    )
    missing = [token for token in needed if token not in base]
    if missing:
        raise RuntimeError(f"mixed O(3P)/O(1D) capability audit failed: {missing}")
    owner = ("R_diss_O2_mixed", "S_Os_mass_diss_mixed", "mixed_o2_progress")
    inherited = [token for token in owner if token in base]
    if inherited:
        raise RuntimeError(f"mixed O2 dissociation owner already present: {inherited}")

    return f"""# EXPERIMENTAL: e + O2(X) -> e + O(3P) + O(1D)
# Existing independent states: O(3P)=w_O, O(1D)=w_Os.
# 2017 empirical Maxwellian comparison: doi:10.1515/jaots-2017-0002
# k_num=3.49e-14 * exp(-5.92 / Te[eV]) m3/s, Te=(2/3)*mean_en_solved.
# COMSOL Ar/O2 ICP reaction 14: 8.4 eV electron energy loss per event.
# Science HOLD: cross-section/EEPF parity, excited-state quenching and
# overlap independence from existing ground-state dissociation unproven.
# R_mixed [mol/(m3 s)]; n_e [1/m3], c_O2 [mol/m3], both mass sources [kg/(m3 s)].

[FunctorMaterials]
  [mixed_o2_concentration]
    type = ADParsedFunctorMaterial
    property_name = c_O2_diss_mixed
    functor_names = 'rho_neutral w_O2_constraint'
    functor_symbols = 'rho w'
    expression = 'rho*w/{M_O2:.17g}'
    block = plasma
  []
  [mixed_electron_temperature]
    type = ADParsedFunctorMaterial
    property_name = Te_diss_mixed_eV
    functor_names = 'mean_en_solved'
    functor_symbols = 'eps'
    expression = '(2.0/3.0)*eps'
    block = plasma
  []
  [mixed_o2_progress]
    type = ADParsedFunctorMaterial
    property_name = R_diss_O2_mixed
    functor_names = 'n_e_physical c_O2_diss_mixed Te_diss_mixed_eV'
    functor_symbols = 'ne co2 te'
    expression = '{MIXED_RATE_PREF_M3_S:.17g}*ne*co2*exp(-{MIXED_FIT_ENERGY_EV:.17g}/te)'
    block = plasma
  []
  [mixed_o3p_mass_source]
    type = ADParsedFunctorMaterial
    property_name = S_O_mass_diss_mixed
    functor_names = 'R_diss_O2_mixed'
    functor_symbols = 'R'
    expression = '{M_O:.17g}*R'
    block = plasma
  []
  [mixed_o1d_mass_source]
    type = ADParsedFunctorMaterial
    property_name = S_Os_mass_diss_mixed
    functor_names = 'R_diss_O2_mixed'
    functor_symbols = 'R'
    expression = '{M_O:.17g}*R'
    block = plasma
  []
  [mixed_o2_mass_sink_implicit]
    type = ADParsedFunctorMaterial
    property_name = S_O2_mass_diss_mixed_implicit
    functor_names = 'R_diss_O2_mixed'
    functor_symbols = 'R'
    expression = '-{M_O2:.17g}*R'
    block = plasma
  []
  [mixed_heavy_mass_closure]
    type = ADParsedFunctorMaterial
    property_name = S_heavy_mass_closure_diss_mixed
    functor_names = 'S_O_mass_diss_mixed S_Os_mass_diss_mixed S_O2_mass_diss_mixed_implicit'
    functor_symbols = 'So Sos So2'
    expression = 'So+Sos+So2'
    block = plasma
  []
  [mixed_electron_energy_sink]
    type = ADParsedFunctorMaterial
    property_name = S_electron_energy_mol_diss_mixed
    functor_names = 'R_diss_O2_mixed'
    functor_symbols = 'R'
    expression = '-{MIXED_ENERGY_LOSS_EV:.17g}*R'
    block = plasma
  []
[]

[Kernels]
  [mixed_electron_energy]
    type = FunctorKernel
    variable = log_energy
    functor = S_electron_energy_mol_diss_mixed
    functor_on_rhs = true
    block = plasma
  []
[]

[FVKernels]
  [mixed_o3p_source]
    type = PhysicsFVSpeciesReactionSource
    variable = w_O
    source = S_O_mass_diss_mixed
    block = plasma
  []
  [mixed_o1d_source]
    type = PhysicsFVSpeciesReactionSource
    variable = w_Os
    source = S_Os_mass_diss_mixed
    block = plasma
  []
[]

[Postprocessors]
  [mixed_R_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = R_diss_O2_mixed
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [mixed_o3p_mass_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_O_mass_diss_mixed
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [mixed_o1d_mass_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_Os_mass_diss_mixed
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [mixed_oxygen_molecular_sink_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_O2_mass_diss_mixed_implicit
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [mixed_heavy_mass_closure_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_heavy_mass_closure_diss_mixed
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [mixed_energy_sink_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_electron_energy_mol_diss_mixed
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]
"""


def args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--base-input", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--channel", choices=("ground", "mixed", "off"), default="ground")
    return p.parse_args()


def main() -> int:
    a = args()
    base = a.base_input.read_text(encoding="utf-8")
    if a.channel == "off":
        # Exact chemistry knockout: this overlay contributes no owners, kernels
        # or source terms. All other case inputs and overlays remain unchanged.
        if any(token in base for token in ("R_diss_O2_mixed", "R_diss_O2",
                                          "S_O_mass_diss", "mixed_o2_progress")):
            raise RuntimeError("OFF dissociation requires no inherited dissociation owner")
        a.output.write_text("# Controlled Step0 knockout: ground and mixed O2 dissociation OFF.\n",
                            encoding="utf-8")
        print("ISSUE395_O2_DISSOCIATION_BOTH_OFF_PASS")
        print("chemistry_knockout=only_dissociation_overlay")
        print(f"output={a.output}")
        return 0
    if a.channel == "mixed":
        overlay = build_mixed_dissociation_overlay(base)
        a.output.write_text(overlay, encoding="utf-8")
        print("ISSUE395_O2_MIXED_DISSOCIATION_OVERLAY_BUILD_PASS")
        print("science_status=HOLD_CROSS_SECTION_EEPF_QUENCHING")
        print(f"output={a.output}")
        return 0
    missing = [token for token in REQUIRED_BASE_TOKENS if token not in base]
    if missing:
        raise RuntimeError(f"dissociation base-input capability audit failed; missing {missing}")
    inherited = [token for token in FORBIDDEN_BASE_TOKENS if token in base]
    if inherited:
        raise RuntimeError(f"dissociation requires one new progress owner; inherited {inherited}")

    text = f'''# Issue #395: source-backed electron-impact O2 dissociation from t=0
# Reaction: e + O2 -> e + O + O
# Ground-state O + O rate fit: Zhao et al., Phys. Plasmas 31, 083507 (2024), Table I (4).
# https://doi.org/10.1063/5.0214357
# k_particle = 1.41e-15 * Te^(-0.22) * exp(-2.98/Te) [m^3/s]
# Te[eV] = (2/3) * mean_en_solved[eV]
# 2.98 eV is a Maxwellian rate-fit parameter, NOT the collision threshold.
# Effective electron-energy loss = 6.0 eV/event: COMSOL Ar/O2 ICP, Table 2 (13).
# https://doc.comsol.com/6.4/doc/com.comsol.help.models.plasma.icp_argon_oxygen/icp_argon_oxygen.html
# The ground-state thermochemical limit is about 5.12 eV, not this effective loss.
# Historical O2_dissociation.csv is intentionally not used here.

[FunctorMaterials]
  [diss_o2_concentration]
    type = ADParsedFunctorMaterial
    property_name = c_O2_diss
    functor_names = 'rho_neutral w_O2_constraint'
    functor_symbols = 'rho w'
    expression = 'rho*w/{M_O2:.17g}'
    block = plasma
  []
  [diss_electron_temperature]
    type = ADParsedFunctorMaterial
    property_name = Te_diss_eV
    functor_names = 'mean_en_solved'
    functor_symbols = 'eps'
    expression = '(2.0/3.0)*eps'
    block = plasma
  []
  [diss_o2_progress]
    type = ADParsedFunctorMaterial
    property_name = R_diss_O2
    functor_names = 'n_e_physical c_O2_diss Te_diss_eV'
    functor_symbols = 'ne co2 te'
    expression = '{DISS_RATE_PREF_M3_S:.17g}*ne*co2*(te^({DISS_TE_EXPONENT:.17g}))*exp(-{DISS_FIT_EXP_ENERGY_EV:.17g}/te)'
    block = plasma
  []
  [diss_o_mass_source]
    type = ADParsedFunctorMaterial
    property_name = S_O_mass_diss
    functor_names = 'R_diss_O2'
    functor_symbols = 'R'
    expression = '{2.0*M_O:.17g}*R'
    block = plasma
  []
  [diss_o2_mass_source_implicit]
    type = ADParsedFunctorMaterial
    property_name = S_O2_mass_diss_implicit
    functor_names = 'R_diss_O2'
    functor_symbols = 'R'
    expression = '-{M_O2:.17g}*R'
    block = plasma
  []
  [diss_heavy_mass_closure]
    type = ADParsedFunctorMaterial
    property_name = S_heavy_mass_closure_diss
    functor_names = 'S_O_mass_diss S_O2_mass_diss_implicit'
    functor_symbols = 'So So2'
    expression = 'So+So2'
    block = plasma
  []
  [diss_electron_energy_source]
    type = ADParsedFunctorMaterial
    property_name = S_electron_energy_molar_diss
    functor_names = 'R_diss_O2'
    functor_symbols = 'R'
    expression = '-{DISS_ENERGY_LOSS_EV:.17g}*R'
    block = plasma
  []
[]

[Kernels]
  [diss_electron_energy]
    type = FunctorKernel
    variable = log_energy
    functor = S_electron_energy_molar_diss
    functor_on_rhs = true
    block = plasma
  []
[]

[FVKernels]
  [diss_atomic_oxygen_source]
    type = PhysicsFVSpeciesReactionSource
    variable = w_O
    source = S_O_mass_diss
    block = plasma
  []
[]

[Postprocessors]
  [diss_R_min]
    type = ADElementExtremeFunctorValue
    functor = R_diss_O2
    value_type = min
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [diss_R_max]
    type = ADElementExtremeFunctorValue
    functor = R_diss_O2
    value_type = max
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [diss_R_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = R_diss_O2
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [diss_energy_source_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_electron_energy_molar_diss
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [diss_O_mass_source_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_O_mass_diss
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [diss_heavy_mass_closure_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = S_heavy_mass_closure_diss
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]
'''

    a.output.write_text(text, encoding="utf-8")
    print("ISSUE395_O2_DISSOCIATION_OVERLAY_BUILD_PASS")
    print(f"output={a.output}")
    print(f"rate_prefactor_m3_s={DISS_RATE_PREF_M3_S:.17g}")
    print(f"rate_Te_exponent={DISS_TE_EXPONENT:.17g}")
    print(f"rate_fit_energy_eV={DISS_FIT_EXP_ENERGY_EV:.17g}")
    print(f"effective_energy_loss_eV={DISS_ENERGY_LOSS_EV:.17g}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
