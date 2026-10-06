#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

import prepare_l4_dt_compare as core
import prepare_l4_dt_ramp_ionization_20ns_compare as ramp

HERE = Path(__file__).resolve().parent
RATE_TABLE = "../../physics_app/data/electron_impact/o2_dissociation.txt"
OUT = HERE / "full_monolithic_l4_dt_ramp_ionization_dissociation_20ns_ti_te_2eV.i"
DISSOCIATION_ENERGY_LOSS_EV = 6.0
O_ATOM_MOLAR_MASS = 0.016


def add_o2_dissociation(text: str) -> str:
    # The 2 eV ionization baseline already owns c_O2_ei16_ab. Reuse that exact
    # O2 molar concentration so ionization and dissociation see the same target.
    materials = f"""
  [o2_dissociation_rate]
    type = PhysicsElectronImpactDissociationMaterial
    rate_table_file = {RATE_TABLE}
    mean_energy = mean_en_solved
    electron_number_density = n_e_physical
    o2_molar_concentration = c_O2_ei16_ab
    block = plasma
  []
  [o2_dissociation_O_mass_source]
    type = ADParsedFunctorMaterial
    property_name = O_dissociation_mass_source
    functor_names = 'R_diss_O2'
    functor_symbols = 'R'
    expression = '{2.0 * O_ATOM_MOLAR_MASS:.17g}*R'
    block = plasma
  []
"""
    text = core.append_to_section(text, "FunctorMaterials", materials)

    # e + O2 -> e + 2 O:
    #   * electron number source = 0
    #   * O production = 2 M_O R_diss = 0.032 R_diss kg/(m^3 s)
    #   * O2 is the constrained simplex reference species, so its equal mass
    #     loss follows automatically from sum(Y_k)=1 and the conservative O row.
    #   * electron-energy loss = 6 eV per dissociation event.
    kernels = f"""
  [o2_dissociation_O_source]
    type = PhysicsFVSpeciesReactionSource
    variable = eta_O
    source = O_dissociation_mass_source
    block = plasma
  []
  [o2_dissociation_energy_loss]
    type = FVCoupledForce
    variable = log_energy
    v = R_diss_O2
    coef = -{DISSOCIATION_ENERGY_LOSS_EV:.1f}
    block = plasma
  []
"""
    text = core.append_to_section(text, "FVKernels", kernels)

    pps = """
  [R_diss_O2_avg]
    type = ElementAverageFunctorPostprocessor
    functor = R_diss_O2
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [R_diss_O2_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = R_diss_O2
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [O_dissociation_mass_source_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = O_dissociation_mass_source
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [O_mass_fraction_avg_diss]
    type = ElementAverageFunctorPostprocessor
    functor = w_O
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [O2_mass_fraction_avg_diss]
    type = ElementAverageFunctorPostprocessor
    functor = w_O2_constraint
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
"""
    return core.append_to_section(text, "Postprocessors", pps)


def build() -> Path:
    # Base state:
    #   Ti = 2 eV for ion-wall thermal velocity
    #   Te = 2 eV -> initial mean electron energy = 3 eV
    #   ne = nO2+ = 1e15 m^-3
    #   O2 ionization retained
    #   time sequence = 0.1 ns x100, then 0.2 ns x50, end_time=20 ns
    baseline = ramp.build("ti_te_2eV")
    text = baseline.read_text(encoding="utf-8")
    text = add_o2_dissociation(text)

    required = (
        "ion_temperature_eV = 2.0",
        "type = TimeSequenceStepper",
        "type = PhysicsElectronImpactIonizationMaterial",
        "rate_table_file = ../../physics_app/data/electron_impact/o2_ionization.txt",
        "v = R_ion_O2",
        "coef = -12.06",
        "type = PhysicsElectronImpactDissociationMaterial",
        f"rate_table_file = {RATE_TABLE}",
        "property_name = O_dissociation_mass_source",
        "variable = eta_O",
        "source = O_dissociation_mass_source",
        "v = R_diss_O2",
        f"coef = -{DISSOCIATION_ENERGY_LOSS_EV:.1f}",
        "functor = R_diss_O2",
        "functor = w_O",
        "functor = w_O2_constraint",
    )
    for token in required:
        if token not in text:
            raise RuntimeError(f"dissociation 2 eV ramp missing required token: {token}")

    # Dissociation is number-conserving for electrons; no electron continuity
    # source is permitted for R_diss_O2.
    if "number_source = R_diss_O2" in text:
        raise RuntimeError("dissociation incorrectly changes electron number")

    # O2 is constrained and must not receive a separate residual kernel.
    if "variable = w_O2_constraint" in text or "variable = eta_O2" in text:
        raise RuntimeError("constrained O2 was given an explicit residual equation")

    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT}")
    print("case=ti_te_2eV + O2 ionization + O2 dissociation")
    print("Ti=2 eV; Te=2 eV; initial mean electron energy=3 eV")
    print("dissociation: e + O2 -> e + 2O")
    print("O mass source=0.032*R_diss_O2 kg/(m^3 s); constrained O2 supplies equal mass loss")
    print("dissociation electron-energy loss=6.0 eV/event")
    print("electron number source from dissociation=0")
    print("ramp=0.1 ns x100 then 0.2 ns x50; end_time=20 ns")
    return OUT


if __name__ == "__main__":
    build()
