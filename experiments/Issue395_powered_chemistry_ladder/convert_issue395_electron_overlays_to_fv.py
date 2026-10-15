#!/usr/bin/env python3
"""Convert Issue #395 RF/chemistry electron source owners to FV-compatible form."""
from __future__ import annotations

import argparse
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise RuntimeError(f"{label}: expected one match, found {n}")
    return text.replace(old, new, 1)


def convert_parent(text: str) -> str:
    for block in (
        """  [log_ne_rf_state_t6]\n    family = LAGRANGE\n    order = FIRST\n    block = plasma\n  []\n""",
        """  [log_energy_rf_state_t6]\n    family = LAGRANGE\n    order = FIRST\n    block = plasma\n  []\n""",
    ):
        text = replace_once(text, block, "", "remove RF log snapshot variable")

    text = replace_once(
        text,
        """  [electron_density_rf_state_t6]\n    family = LAGRANGE\n    order = FIRST\n    block = plasma\n  []\n""",
        """  [electron_density_rf_state_t6]\n    family = MONOMIAL\n    order = CONSTANT\n    initial_condition = 1.0e15\n    block = plasma\n  []\n""",
        "physical electron snapshot variable",
    )
    text = replace_once(
        text,
        """  [mean_energy_rf_state_t6]\n    family = LAGRANGE\n    order = FIRST\n    block = plasma\n  []\n""",
        """  [mean_energy_rf_state_t6]\n    family = MONOMIAL\n    order = CONSTANT\n    initial_condition = 4.0\n    block = plasma\n  []\n""",
        "mean-energy snapshot variable",
    )

    text = replace_once(
        text,
        """  [freeze_log_ne_t6]\n    type = ParsedAux\n    variable = log_ne_rf_state_t6\n    coupled_variables = 'log_ne'\n    expression = 'log_ne'\n    execute_on = 'INITIAL TIMESTEP_BEGIN'\n    block = plasma\n  []\n  [freeze_log_energy_t6]\n    type = ParsedAux\n    variable = log_energy_rf_state_t6\n    coupled_variables = 'log_energy'\n    expression = 'log_energy'\n    execute_on = 'INITIAL TIMESTEP_BEGIN'\n    block = plasma\n  []\n  [electron_density_rf_state_t6_aux]\n    type = ParsedAux\n    variable = electron_density_rf_state_t6\n    coupled_variables = 'log_ne_rf_state_t6'\n    expression = 'exp(log_ne_rf_state_t6)*6.02214076e23'\n    execute_on = 'INITIAL TIMESTEP_BEGIN'\n    block = plasma\n  []\n""",
        """  [electron_density_rf_state_t6_aux]\n    type = FunctorAux\n    variable = electron_density_rf_state_t6\n    functor = n_e_physical\n    execute_on = 'INITIAL TIMESTEP_BEGIN'\n    block = plasma\n  []\n""",
        "physical electron snapshot aux",
    )
    text = replace_once(
        text,
        """  [mean_energy_rf_state_t6_aux]\n    type = ParsedAux\n    variable = mean_energy_rf_state_t6\n    coupled_variables = 'log_ne_rf_state_t6 log_energy_rf_state_t6'\n    expression = 'exp(log_energy_rf_state_t6-log_ne_rf_state_t6)'\n    execute_on = 'INITIAL TIMESTEP_BEGIN'\n    block = plasma\n  []\n""",
        """  [mean_energy_rf_state_t6_aux]\n    type = FunctorAux\n    variable = mean_energy_rf_state_t6\n    functor = mean_en_solved\n    execute_on = 'INITIAL TIMESTEP_BEGIN'\n    block = plasma\n  []\n""",
        "mean-energy snapshot aux",
    )

    text = replace_once(
        text,
        "coupled_variables = 'log_ne_rf_state_t6 pressure_rf_state_t6'",
        "coupled_variables = 'electron_density_rf_state_t6 pressure_rf_state_t6'",
        "RF conductivity state",
    )
    text = replace_once(text, "constant_names = 'NA qe me kb Tg om'", "constant_names = 'qe me kb Tg om'", "RF conductivity constants")
    text = replace_once(
        text,
        "constant_expressions = '6.02214076e23 1.602176634e-19 9.1093837015e-31 1.380649e-23 300 85199992.765355185'",
        "constant_expressions = '1.602176634e-19 9.1093837015e-31 1.380649e-23 300 85199992.765355185'",
        "RF conductivity constant values",
    )
    text = replace_once(
        text,
        "expression = '(exp(log_ne_rf_state_t6)*NA*qe^2*(qe/(me*(muN_rf_t6/(pressure_rf_state_t6/(kb*Tg))))))/(me*((qe/(me*(muN_rf_t6/(pressure_rf_state_t6/(kb*Tg)))))^2+om^2))'",
        "expression = '(electron_density_rf_state_t6*qe^2*(qe/(me*(muN_rf_t6/(pressure_rf_state_t6/(kb*Tg))))))/(me*((qe/(me*(muN_rf_t6/(pressure_rf_state_t6/(kb*Tg)))))^2+om^2))'",
        "RF conductivity expression",
    )
    text = replace_once(
        text,
        """[Kernels]\n  [rf_heating_t6]\n    type = MatBodyForce\n    variable = log_energy\n    material_property = q_rf_eV_mol_t6\n    block = plasma\n  []\n[]\n""",
        """[FVKernels]\n  [rf_heating_t6]\n    type = FVCoupledForce\n    variable = log_energy\n    v = q_rf_eV_mol_t6\n    coef = 1.0\n    block = plasma\n  []\n[]\n""",
        "RF electron heating source",
    )
    if "log_ne_rf_state_t6" in text or "log_energy_rf_state_t6" in text:
        raise RuntimeError("obsolete RF log-state snapshot remains")
    return text


def convert_energy_overlay(text: str, name: str, functor: str) -> str:
    old = f"""[Kernels]\n  [{name}]\n    type = FunctorKernel\n    variable = log_energy\n    functor = {functor}\n    functor_on_rhs = true\n    block = plasma\n  []\n[]\n"""
    new = f"""[FVKernels]\n  [{name}]\n    type = FVCoupledForce\n    variable = log_energy\n    v = {functor}\n    coef = 1.0\n    block = plasma\n  []\n[]\n"""
    return replace_once(text, old, new, name)


def convert_ionization(text: str) -> str:
    old = """[Kernels]\n  [ei16_electron_particle_source]\n    type = FunctorKernel\n    variable = log_ne\n    functor = S_electron_molar_EI16\n    functor_on_rhs = true\n    block = plasma\n  []\n  [ei16_electron_energy_source]\n    type = FunctorKernel\n    variable = log_energy\n    functor = S_electron_energy_molar_EI16\n    functor_on_rhs = true\n    block = plasma\n  []\n[]\n\n"""
    text = replace_once(text, old, "", "remove EI16 FEM electron sources")
    add = """  [ei16_electron_particle_source]\n    type = FVCoupledForce\n    variable = log_ne\n    v = S_electron_molar_EI16\n    coef = 1.0\n    block = plasma\n  []\n  [ei16_electron_energy_source]\n    type = FVCoupledForce\n    variable = log_energy\n    v = S_electron_energy_molar_EI16\n    coef = 1.0\n    block = plasma\n  []\n"""
    return replace_once(text, "[FVKernels]\n", "[FVKernels]\n" + add, "insert EI16 FV electron sources")


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--parent", type=Path, required=True)
    p.add_argument("--elastic", type=Path, required=True)
    p.add_argument("--dissociation", type=Path, required=True)
    p.add_argument("--ionization", type=Path, required=True)
    a = p.parse_args()

    write(a.parent, convert_parent(a.parent.read_text(encoding="utf-8")))
    write(a.elastic, convert_energy_overlay(a.elastic.read_text(encoding="utf-8"), "ei02_electron_energy_loss", "elastic_energy_source_EI02"))
    write(a.dissociation, convert_energy_overlay(a.dissociation.read_text(encoding="utf-8"), "diss_electron_energy", "S_electron_energy_molar_diss"))
    write(a.ionization, convert_ionization(a.ionization.read_text(encoding="utf-8")))

    for path in (a.parent, a.elastic, a.dissociation, a.ionization):
        text = path.read_text(encoding="utf-8")
        if "type = FunctorKernel\n    variable = log_ne" in text or "type = FunctorKernel\n    variable = log_energy" in text:
            raise RuntimeError(f"FEM electron source remains in {path}")
    print("ISSUE395_ELECTRON_FVM_OVERLAYS_PASS")
    print("RF heating + EI02 + dissociation + EI16 electron sources = FV")
    print("RF snapshot = physical density/mean-energy elemental state")


if __name__ == "__main__":
    main()
