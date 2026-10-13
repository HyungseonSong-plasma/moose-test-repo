#!/usr/bin/env python3
"""T6-v2 overlays: transfer physical density/mean energy before Drude closure.

T6-v1 transferred log(ne) and log(energy) onto the nonmatching Maxwell mesh and
then exponentiated.  That nonlinear ordering biased the steep edge-density
profile enough to produce a 3.09% raw power defect.  V2 keeps standard MOOSE
SolutionUserObject/SolutionAux transfer but transfers physical n_e and mean
energy first, then evaluates the conductivity on the Maxwell mesh.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import build_t6_overlays as v1


def replace_once(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise RuntimeError(f"{label}: expected one match, found {n}")
    return text.replace(old, new, 1)


def maxwell_overlay(x: list[float], mu_n: list[float]) -> str:
    text = v1.maxwell_overlay(x, mu_n)
    old = """[AuxVariables]\n  [log_ne_state_t6]\n    family = LAGRANGE\n    order = FIRST\n    block = plasma\n  []\n  [log_energy_state_t6]\n    family = LAGRANGE\n    order = FIRST\n    block = plasma\n  []\n  [pressure_state_t6]\n    family = MONOMIAL\n    order = CONSTANT\n    block = plasma\n  []\n  [mean_energy_state_t6]\n    family = LAGRANGE\n    order = FIRST\n    block = plasma\n  []\n[]\n\n[UserObjects]\n  [plasma_state_t6]\n    type = SolutionUserObject\n    mesh = '${plasma_solution_file_t6}'\n    system_variables = 'log_ne log_energy p'\n    timestep = LATEST\n    execute_on = INITIAL\n  []\n[]\n\n[AuxKernels]\n  [map_log_ne_t6]\n    type = SolutionAux\n    variable = log_ne_state_t6\n    solution = plasma_state_t6\n    from_variable = log_ne\n    execute_on = INITIAL\n  []\n  [map_log_energy_t6]\n    type = SolutionAux\n    variable = log_energy_state_t6\n    solution = plasma_state_t6\n    from_variable = log_energy\n    execute_on = INITIAL\n  []\n  [map_pressure_t6]\n    type = SolutionAux\n    variable = pressure_state_t6\n    solution = plasma_state_t6\n    from_variable = p\n    execute_on = INITIAL\n  []\n  [mean_energy_t6]\n    type = ParsedAux\n    variable = mean_energy_state_t6\n    coupled_variables = 'log_ne_state_t6 log_energy_state_t6'\n    expression = 'exp(log_energy_state_t6-log_ne_state_t6)'\n    execute_on = INITIAL\n    block = plasma\n  []\n[]\n"""
    new = """[AuxVariables]\n  [electron_density_state_t6]\n    family = LAGRANGE\n    order = FIRST\n    block = plasma\n  []\n  [mean_energy_state_t6]\n    family = LAGRANGE\n    order = FIRST\n    block = plasma\n  []\n  [pressure_state_t6]\n    family = MONOMIAL\n    order = CONSTANT\n    block = plasma\n  []\n[]\n\n[UserObjects]\n  [plasma_state_t6]\n    type = SolutionUserObject\n    mesh = '${plasma_solution_file_t6}'\n    system_variables = 'electron_density_rf_state_t6 mean_energy_rf_state_t6 p'\n    timestep = LATEST\n    execute_on = INITIAL\n  []\n[]\n\n[AuxKernels]\n  [map_electron_density_t6]\n    type = SolutionAux\n    variable = electron_density_state_t6\n    solution = plasma_state_t6\n    from_variable = electron_density_rf_state_t6\n    execute_on = INITIAL\n  []\n  [map_mean_energy_t6]\n    type = SolutionAux\n    variable = mean_energy_state_t6\n    solution = plasma_state_t6\n    from_variable = mean_energy_rf_state_t6\n    execute_on = INITIAL\n  []\n  [map_pressure_t6]\n    type = SolutionAux\n    variable = pressure_state_t6\n    solution = plasma_state_t6\n    from_variable = p\n    execute_on = INITIAL\n  []\n[]\n"""
    text = replace_once(text, old, new, "physical-state Maxwell transfer")
    text = text.replace("coupled_variables = 'log_ne_state_t6 pressure_state_t6'", "coupled_variables = 'electron_density_state_t6 pressure_state_t6'")
    text = text.replace("constant_names = 'NA qe me kb Tg om'", "constant_names = 'qe me kb Tg om'")
    text = text.replace("constant_expressions = '6.02214076e23 1.602176634e-19 9.1093837015e-31 1.380649e-23 300 ${omega}'", "constant_expressions = '1.602176634e-19 9.1093837015e-31 1.380649e-23 300 ${omega}'")
    text = text.replace("exp(log_ne_state_t6)*NA*qe^2", "electron_density_state_t6*qe^2")
    if "log_ne_state_t6" in text or "log_energy_state_t6" in text:
        raise RuntimeError("obsolete Maxwell log-state coupling remains")
    return text


def plasma_overlay(x: list[float], mu_n: list[float]) -> str:
    text = v1.plasma_overlay(x, mu_n)
    old = """  [log_energy_rf_state_t6]\n    family = LAGRANGE\n    order = FIRST\n    block = plasma\n  []\n  [pressure_rf_state_t6]\n"""
    new = """  [log_energy_rf_state_t6]\n    family = LAGRANGE\n    order = FIRST\n    block = plasma\n  []\n  [electron_density_rf_state_t6]\n    family = LAGRANGE\n    order = FIRST\n    block = plasma\n  []\n  [pressure_rf_state_t6]\n"""
    text = replace_once(text, old, new, "source physical density variable")
    old = """  [freeze_log_energy_t6]\n    type = ParsedAux\n    variable = log_energy_rf_state_t6\n    coupled_variables = 'log_energy'\n    expression = 'log_energy'\n    execute_on = 'INITIAL TIMESTEP_BEGIN'\n    block = plasma\n  []\n  [freeze_pressure_t6]\n"""
    new = """  [freeze_log_energy_t6]\n    type = ParsedAux\n    variable = log_energy_rf_state_t6\n    coupled_variables = 'log_energy'\n    expression = 'log_energy'\n    execute_on = 'INITIAL TIMESTEP_BEGIN'\n    block = plasma\n  []\n  [electron_density_rf_state_t6_aux]\n    type = ParsedAux\n    variable = electron_density_rf_state_t6\n    coupled_variables = 'log_ne_rf_state_t6'\n    expression = 'exp(log_ne_rf_state_t6)*6.02214076e23'\n    execute_on = 'INITIAL TIMESTEP_BEGIN'\n    block = plasma\n  []\n  [freeze_pressure_t6]\n"""
    return replace_once(text, old, new, "source physical density evaluation")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", type=Path, required=True)
    ap.add_argument("--maxwell-overlay", type=Path, required=True)
    ap.add_argument("--plasma-overlay", type=Path, required=True)
    a = ap.parse_args()
    x, mu_n = v1.table(a.table)
    a.maxwell_overlay.parent.mkdir(parents=True, exist_ok=True)
    a.plasma_overlay.parent.mkdir(parents=True, exist_ok=True)
    a.maxwell_overlay.write_text(maxwell_overlay(x, mu_n), encoding="utf-8")
    a.plasma_overlay.write_text(plasma_overlay(x, mu_n), encoding="utf-8")
    print(
        "T6_V2_OVERLAY_BUILD_PASS "
        f"table_points={len(x)} energy_range_eV=[{x[0]:.9g},{x[-1]:.9g}] "
        "physical_density_transfer=true physical_mean_energy_transfer=true "
        "standard_moose_only=true custom_cpp=false"
    )


if __name__ == "__main__":
    main()
