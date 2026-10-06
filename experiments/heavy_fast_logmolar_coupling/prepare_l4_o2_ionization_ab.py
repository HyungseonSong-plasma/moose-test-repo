#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import prepare_l4_feedback_density_compare as feedback
import prepare_l4_dt_compare as core

HERE = Path(__file__).resolve().parent
DT = 1.0e-10
NUM_STEPS = 10
TOTAL_TIME = 1.0e-9
RATE_TABLE = "../../physics_app/data/electron_impact/o2_ionization.txt"
ELECTRON_WALLS = (
    "plasma_electrode plasma_metal plasma_right plasma_cover "
    "plasma_wafer plasma_focus_ring"
)
CASES = ("chem_off", "o2_ionization_on")


def add_common_diagnostics(text: str) -> str:
    pps = f"""
  [electron_number_inventory_ab]
    type = ADElementIntegralFunctorPostprocessor
    functor = n_e_physical
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [electron_mean_energy_avg_ab]
    type = ElementAverageFunctorPostprocessor
    functor = mean_en_solved
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [electron_sheath_molar_loss_rate_ab]
    type = SideFVFluxBCIntegral
    boundary = '{ELECTRON_WALLS}'
    fvbcs = 'electron_sheath_loss'
    execute_on = 'INITIAL TIMESTEP_END'
  []
"""
    return core.append_to_section(text, "Postprocessors", pps)


def add_o2_ionization(text: str) -> str:
    materials = f"""
  [ei16_c_O2_ab]
    type = ADParsedFunctorMaterial
    property_name = c_O2_ei16_ab
    functor_names = 'rho_mat w_O2_constraint'
    functor_symbols = 'rho wo2'
    expression = 'rho*wo2/0.032'
    block = plasma
  []
  [ei16_rate_ab]
    type = PhysicsElectronImpactIonizationMaterial
    rate_table_file = {RATE_TABLE}
    mean_energy = mean_en_solved
    electron_number_density = n_e_physical
    o2_molar_concentration = c_O2_ei16_ab
    block = plasma
  []
  [ei16_projection_ab]
    type = PhysicsO2IonizationSourceMaterial
    reaction_progress = R_ion_O2
    o2_molar_mass = 0.032
    block = plasma
  []
"""
    text = core.append_to_section(text, "FunctorMaterials", materials)

    kernels = """
  [ei16_O2p_source_ab]
    type = PhysicsFVSpeciesReactionSource
    variable = eta_O2p
    source = O2p_ionization_mass_source
    block = plasma
  []
  [ei16_electron_source_ab]
    type = PhysicsFVLogMolarElectronReactionSource
    variable = log_ne
    number_source = electron_ionization_number_source
    block = plasma
  []
  [ei16_energy_loss_ab]
    type = FVCoupledForce
    variable = log_energy
    v = R_ion_O2
    coef = -12.06
    block = plasma
  []
"""
    text = core.append_to_section(text, "FVKernels", kernels)

    pps = """
  [R_ion_O2_avg_ab]
    type = ElementAverageFunctorPostprocessor
    functor = R_ion_O2
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [R_ion_O2_integral_ab]
    type = ADElementIntegralFunctorPostprocessor
    functor = R_ion_O2
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [electron_ionization_source_integral_ab]
    type = ADElementIntegralFunctorPostprocessor
    functor = electron_ionization_number_source
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [O2p_ionization_mass_source_integral_ab]
    type = ADElementIntegralFunctorPostprocessor
    functor = O2p_ionization_mass_source
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []
"""
    return core.append_to_section(text, "Postprocessors", pps)


def build(case: str) -> Path:
    if case not in CASES:
        raise ValueError(case)

    # Start from the already successful 0.1 ns x 10 feedback case. This retains:
    # ne=nO2+=1e15 m^-3 neutrality, 20 sccm pure-O2 inlet, 10 mTorr outlet,
    # ion surface+migration on inlet/outlet+six walls, and the six-wall electron sheath.
    baseline = feedback.build("dt0p1ns_10steps")
    text = baseline.read_text(encoding="utf-8")
    text = add_common_diagnostics(text)

    if case == "o2_ionization_on":
        text = add_o2_ionization(text)

    # Exact time contract inherited from the successful case.
    exec_start, exec_end = core.executioner_bounds(text)
    exec_section = text[exec_start:exec_end]
    for expected in (
        f"  dt = {DT:.17g}",
        f"  dtmin = {DT:.17g}",
        f"  dtmax = {DT:.17g}",
        f"  end_time = {TOTAL_TIME:.17g}",
        f"  num_steps = {NUM_STEPS}",
    ):
        if expected not in exec_section:
            raise RuntimeError(f"A/B time contract missing: {expected}")

    # Attachment is explicitly excluded from this discriminator.
    forbidden = ("R_attachment", "o2_attachment.txt", "PhysicsElectronImpactAttachmentMaterial")
    for token in forbidden:
        if token in text:
            raise RuntimeError(f"attachment leaked into ionization-only A/B: {token}")

    electron_sheath = core.child_block(text, "electron_sheath_loss")
    if f"    boundary = '{ELECTRON_WALLS}'" not in electron_sheath:
        raise RuntimeError("electron sheath boundary set changed in A/B")
    if "inlet" in electron_sheath or "outlet" in electron_sheath:
        raise RuntimeError("electron sheath unexpectedly includes inlet/outlet")

    ionization_tokens = (
        "type = PhysicsElectronImpactIonizationMaterial",
        f"rate_table_file = {RATE_TABLE}",
        "type = PhysicsO2IonizationSourceMaterial",
        "type = PhysicsFVLogMolarElectronReactionSource",
        "number_source = electron_ionization_number_source",
        "source = O2p_ionization_mass_source",
        "v = R_ion_O2",
        "coef = -12.06",
    )
    if case == "o2_ionization_on":
        for token in ionization_tokens:
            if token not in text:
                raise RuntimeError(f"ionization ON contract missing: {token}")
    else:
        for token in ionization_tokens:
            if token in text:
                raise RuntimeError(f"ionization leaked into OFF case: {token}")

    out = HERE / f"full_monolithic_l4_ionization_ab_{case}.i"
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out}")
    print(f"case={case}; dt=0.1 ns; steps=10; end_time=1 ns")
    print("initial ne=nO2p=1e15 m^-3; attachment=OFF")
    print("ionization reaction: e + O2 -> 2e + O2+" if case == "o2_ionization_on" else "volumetric chemistry=OFF")
    print("EI16 energy loss=12.06 eV per event" if case == "o2_ionization_on" else "EI16 energy loss=OFF")
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=CASES, required=True)
    args = parser.parse_args()
    build(args.case)


if __name__ == "__main__":
    main()
