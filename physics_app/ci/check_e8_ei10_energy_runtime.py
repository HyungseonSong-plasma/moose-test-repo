#!/usr/bin/env python3
"""Governed runtime discriminator for #26 E8-I1 EI10 using standard MOOSE energy projection."""

import argparse
import csv
import hashlib
import json
import math
import subprocess
import tempfile
from pathlib import Path

N_A = 6.02214076e23
M_O2 = 31.998e-3
N_REF = 1.0e16
RHO = 3.1998e-5
DT = 1.0e-7
EPSILON_REF_EV = 5.73276
DELTA_E_EV = 0.977
W0 = 1.0e-3
K_O2S = 4.71e8
ENERGY_COEF = -(DELTA_E_EV * N_A / (N_REF * EPSILON_REF_EV))

RUNTIME_INPUT = """[Mesh]
  [mesh]
    type = GeneratedMeshGenerator
    dim = 3
    nx = 1
    ny = 1
    nz = 1
    xmin = 0
    xmax = 1
    ymin = 0
    ymax = 0.01
    zmin = 0
    zmax = 0.01
  []
[]

[Variables]
  [n_e]
    type = MooseVariableFVReal
    initial_condition = 1.0
  []
  [n_epsilon]
    type = MooseVariableFVReal
    initial_condition = 1.0
  []
  [w_O2s]
    type = MooseVariableFVReal
    initial_condition = 1.0e-3
  []
[]

[FunctorMaterials]
  [constants]
    type = ADGenericFunctorMaterial
    prop_names = 'rho_const'
    prop_values = '3.1998e-5'
  []
  [o2_constraint]
    type = ADParsedFunctorMaterial
    property_name = w_O2_constraint
    functor_names = 'w_O2s'
    functor_symbols = 'ws'
    expression = '1.0-ws'
  []
  [electron_number_density]
    type = ADParsedFunctorMaterial
    property_name = n_e_physical
    functor_names = 'n_e'
    functor_symbols = 'nehat'
    expression = '1.0e16*nehat'
  []
  [o2_molar_concentration]
    type = ADParsedFunctorMaterial
    property_name = c_O2
    functor_names = 'rho_const w_O2_constraint'
    functor_symbols = 'dens wo2'
    expression = 'dens*wo2/0.031998'
  []
  [mean_energy_bridge]
    type = PhysicsElectronMeanEnergyMaterial
    electron_energy_density = n_epsilon
    electron_density = n_e
    energy_reference_eV = 5.73276
  []
  [ei10_rate]
    type = PhysicsElectronImpactO2sExcitationMaterial
    electron_number_density = n_e_physical
    o2_molar_concentration = c_O2
  []
  [ei10_heavy_projection]
    type = PhysicsO2sExcitationSourceMaterial
    reaction_progress = R_O2s
    o2_molar_mass = 0.031998
  []
[]

[FVKernels]
  [n_e_time]
    type = FVTimeKernel
    variable = n_e
  []
  [n_epsilon_time]
    type = FVTimeKernel
    variable = n_epsilon
  []
  [ei10_energy_loss]
    type = FVCoupledForce
    variable = n_epsilon
    v = R_O2s
    coef = -10263174.321827531
  []
  [w_O2s_time]
    type = PhysicsFVMassFractionTimeDerivative
    variable = w_O2s
    rho = rho_const
  []
  [w_O2s_source]
    type = PhysicsFVSpeciesReactionSource
    variable = w_O2s
    source = O2s_excitation_mass_source
  []
[]

[Postprocessors]
  [n_e_hat_avg]
    type = ElementAverageFunctorPostprocessor
    functor = n_e
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [n_epsilon_hat_avg]
    type = ElementAverageFunctorPostprocessor
    functor = n_epsilon
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [w_O2s_avg]
    type = ElementAverageFunctorPostprocessor
    functor = w_O2s
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [w_O2_avg]
    type = ElementAverageFunctorPostprocessor
    functor = w_O2_constraint
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [mean_en_solved_avg]
    type = ElementAverageFunctorPostprocessor
    functor = mean_en_solved
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [R_O2s_avg]
    type = ElementAverageFunctorPostprocessor
    functor = R_O2s
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [O2_source_avg]
    type = ElementAverageFunctorPostprocessor
    functor = O2_o2s_excitation_mass_source
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [O2s_source_avg]
    type = ElementAverageFunctorPostprocessor
    functor = O2s_excitation_mass_source
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]

[Executioner]
  type = Transient
  dt = 1.0e-7
  end_time = 1.0e-7
  solve_type = NEWTON
[]

[Outputs]
  csv = true
  exodus = false
[]
"""


def _close(a, b, *, rel=5e-6, abs_=1e-12, label="value"):
    if not math.isclose(a, b, rel_tol=rel, abs_tol=abs_):
        raise AssertionError(f"{label}: {a:.17g} != {b:.17g}")


def _num(row, key):
    value = float(row[key])
    if not math.isfinite(value):
        raise AssertionError(f"non-finite {key}")
    return value


def validate_runtime_rows(rows):
    if len(rows) < 2:
        raise AssertionError("expected initial and final rows")
    i, f = rows[0], rows[-1]
    ne_i, ne_f = _num(i, "n_e_hat_avg"), _num(f, "n_e_hat_avg")
    ep_i, ep_f = _num(i, "n_epsilon_hat_avg"), _num(f, "n_epsilon_hat_avg")
    ws_i, ws_f = _num(i, "w_O2s_avg"), _num(f, "w_O2s_avg")
    wo_i, wo_f = _num(i, "w_O2_avg"), _num(f, "w_O2_avg")
    me_i, me_f = _num(i, "mean_en_solved_avg"), _num(f, "mean_en_solved_avg")
    r_f = _num(f, "R_O2s_avg")
    s_o2, s_o2s = _num(f, "O2_source_avg"), _num(f, "O2s_source_avg")

    _close(ne_f, ne_i, rel=0, abs_=1e-12, label="EI10 electron-particle neutrality")
    if not (ep_i > ep_f > 0 and 0 <= ws_i < ws_f < 1 and wo_i > wo_f > 0):
        raise AssertionError("EI10 positivity/direction failure")
    _close(wo_i + ws_i, 1.0, rel=0, abs_=2e-12, label="initial heavy sum")
    _close(wo_f + ws_f, 1.0, rel=0, abs_=2e-12, label="final heavy sum")
    _close(me_i, EPSILON_REF_EV * ep_i / ne_i, label="initial mean energy")
    _close(me_f, EPSILON_REF_EV * ep_f / ne_f, label="final mean energy")

    if not (r_f > 0 and s_o2 < 0 < s_o2s):
        raise AssertionError("EI10 source signs")
    _close(-s_o2 / M_O2, r_f, label="O2/shared progress")
    _close(s_o2s / M_O2, r_f, label="O2s/shared progress")
    _close(s_o2 + s_o2s, 0, rel=0, abs_=1e-12, label="heavy source closure")

    expected_r = K_O2S * (N_REF * ne_f / N_A) * (RHO * wo_f / M_O2)
    _close(r_f, expected_r, label="canonical R_O2s")
    _close(RHO * (ws_f - ws_i) / DT, s_o2s, label="O2s BE closure")
    _close(RHO * (wo_f - wo_i) / DT, s_o2, label="O2 BE closure")

    rhs = -DELTA_E_EV * N_A * r_f / (N_REF * EPSILON_REF_EV)
    _close((ep_f - ep_i) / DT, rhs, label="EI10 energy BE closure")
    oxygen_i = 2 * RHO * (wo_i + ws_i) / M_O2
    oxygen_f = 2 * RHO * (wo_f + ws_f) / M_O2
    _close(oxygen_f, oxygen_i, rel=2e-12, abs_=1e-14, label="oxygen inventory")

    return {
        "initial": {"n_e_hat": ne_i, "n_epsilon_hat": ep_i, "w_O2": wo_i, "w_O2s": ws_i, "mean_en_solved_eV": me_i},
        "final": {"n_e_hat": ne_f, "n_epsilon_hat": ep_f, "w_O2": wo_f, "w_O2s": ws_f, "mean_en_solved_eV": me_f, "R_O2s_mol_m3_s": r_f},
        "energy_closure": {"energy_loss_eV_per_event": DELTA_E_EV, "standard_moose_object": "FVCoupledForce", "coef": ENERGY_COEF, "normalized_rhs_per_s": rhs, "observed_dn_epsilon_hat_dt_per_s": (ep_f - ep_i) / DT},
        "particle_heavy_closure": {"heavy_fraction_sum": wo_f + ws_f, "oxygen_atom_molar_inventory_initial": oxygen_i, "oxygen_atom_molar_inventory_final": oxygen_f}
    }


def runtime_checker_self_test():
    a = DT * K_O2S * N_REF / N_A
    ws = (W0 + a) / (1 + a)
    wo = 1 - ws
    r = K_O2S * (N_REF / N_A) * (RHO * wo / M_O2)
    ep = 1 - DT * DELTA_E_EV * N_A * r / (N_REF * EPSILON_REF_EV)
    r0 = K_O2S * (N_REF / N_A) * (RHO * (1 - W0) / M_O2)
    rows = [
        {"n_e_hat_avg": 1, "n_epsilon_hat_avg": 1, "w_O2s_avg": W0, "w_O2_avg": 1 - W0, "mean_en_solved_avg": EPSILON_REF_EV, "R_O2s_avg": r0, "O2_source_avg": -M_O2 * r0, "O2s_source_avg": M_O2 * r0},
        {"n_e_hat_avg": 1, "n_epsilon_hat_avg": ep, "w_O2s_avg": ws, "w_O2_avg": wo, "mean_en_solved_avg": EPSILON_REF_EV * ep, "R_O2s_avg": r, "O2_source_avg": -M_O2 * r, "O2s_source_avg": M_O2 * r}
    ]
    validate_runtime_rows(rows)
    assert "type = FVCoupledForce" in RUNTIME_INPUT
    assert "v = R_O2s" in RUNTIME_INPUT
    assert "PhysicsFVElectronReactionEnergySource" not in RUNTIME_INPUT
    print("E8_EI10_INELASTIC_ENERGY_RUNTIME_CHECKER_SELFTEST_PASS")


def _sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as s:
        for chunk in iter(lambda: s.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run_controlled_executable(executable, evidence_out=None, repository_sha=None, build_base_ref=None):
    executable = Path(executable).resolve()
    if not executable.is_file():
        raise SystemExit(f"Physics executable does not exist: {executable}")
    with tempfile.TemporaryDirectory(prefix="e8-ei10-standard-") as tmp:
        work = Path(tmp)
        name = "e8_ei10_energy_runtime.i"
        (work / name).write_text(RUNTIME_INPUT)
        subprocess.run([str(executable), "--check-input", "-i", name], cwd=work, check=True)
        subprocess.run([str(executable), "-i", name], cwd=work, check=True)
        rows = list(csv.DictReader((work / "e8_ei10_energy_runtime_out.csv").open(newline="")))
        evidence = validate_runtime_rows(rows)
    evidence.update({"runtime_mode": "direct_executable", "runtime_executable": str(executable), "runtime_executable_sha256": _sha(executable), "energy_projection_owner": "standard MOOSE FVCoupledForce", "custom_energy_projector_instantiated": False, "claim": "E8-I1 EI10 bounded local runtime discriminator using standard MOOSE energy projection"})
    if repository_sha:
        evidence["repository_sha"] = repository_sha
    if build_base_ref:
        evidence["build_base_ref"] = build_base_ref
    if evidence_out:
        Path(evidence_out).write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(f"E8_EI10_INELASTIC_ENERGY_RUNTIME_VECTOR n_epsilon_hat={evidence['final']['n_epsilon_hat']:.12g} mean_en_eV={evidence['final']['mean_en_solved_eV']:.12g} R={evidence['final']['R_O2s_mol_m3_s']:.12g}")
    print("E8_EI10_INELASTIC_ENERGY_LOCAL_RUNTIME_PASS")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--executable")
    p.add_argument("--evidence-out")
    p.add_argument("--repository-sha")
    p.add_argument("--build-base-ref")
    a = p.parse_args()
    if a.self_test:
        runtime_checker_self_test()
    elif a.executable:
        run_controlled_executable(a.executable, a.evidence_out, a.repository_sha, a.build_base_ref)
    else:
        raise SystemExit("--self-test or --executable is required")


if __name__ == "__main__":
    main()
