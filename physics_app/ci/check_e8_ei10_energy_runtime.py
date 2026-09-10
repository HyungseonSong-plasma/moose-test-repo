#!/usr/bin/env python3
"""Governed-runtime discriminator for #26 E8 EI10 inelastic electron-energy coupling."""

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
WP0 = 1.0e-3
K_O2S = 4.71e8

RUNTIME_INPUT = r"""[Mesh]
  [mesh]
    type = GeneratedMeshGenerator
    dim = 3
    nx = 1
    ny = 1
    nz = 1
    xmin = 0.0
    xmax = 1.0
    ymin = 0.0
    ymax = 0.01
    zmin = 0.0
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
    type = PhysicsFVElectronReactionEnergySource
    variable = n_epsilon
    reaction_progress = R_O2s
    energy_loss_eV = 0.977
    n_ref = 1.0e16
    energy_reference_eV = 5.73276
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


def _assert_close(actual, expected, *, rel=3.0e-6, abs_=1.0e-12, label="value"):
    if not math.isclose(actual, expected, rel_tol=rel, abs_tol=abs_):
        raise AssertionError(f"{label}: actual={actual:.17g} expected={expected:.17g}")


def _f(row, key):
    value = float(row[key])
    if not math.isfinite(value):
        raise AssertionError(f"non-finite {key}: {value}")
    return value


def validate_runtime_rows(rows):
    if len(rows) < 2:
        raise AssertionError(f"expected INITIAL + TIMESTEP_END rows, got {len(rows)}")
    initial = rows[0]
    final = rows[-1]

    ne_i = _f(initial, "n_e_hat_avg")
    ne_f = _f(final, "n_e_hat_avg")
    eps_i = _f(initial, "n_epsilon_hat_avg")
    eps_f = _f(final, "n_epsilon_hat_avg")
    ws_i = _f(initial, "w_O2s_avg")
    ws_f = _f(final, "w_O2s_avg")
    wo2_i = _f(initial, "w_O2_avg")
    wo2_f = _f(final, "w_O2_avg")
    mean_i = _f(initial, "mean_en_solved_avg")
    mean_f = _f(final, "mean_en_solved_avg")
    progress_f = _f(final, "R_O2s_avg")
    so2_f = _f(final, "O2_source_avg")
    so2s_f = _f(final, "O2s_source_avg")

    if not (ne_i > 0.0 and eps_i > 0.0 and eps_f > 0.0):
        raise AssertionError((ne_i, eps_i, eps_f))
    _assert_close(ne_f, ne_i, rel=0.0, abs_=1.0e-12, label="zero EI10 electron-particle source")
    if not eps_f < eps_i:
        raise AssertionError(f"EI10 energy sink did not reduce n_epsilon_hat: {eps_i} -> {eps_f}")

    if not (0.0 <= ws_i < ws_f < 1.0 and wo2_i > wo2_f > 0.0):
        raise AssertionError((ws_i, ws_f, wo2_i, wo2_f))
    _assert_close(wo2_i + ws_i, 1.0, rel=0.0, abs_=2.0e-12, label="initial heavy fraction sum")
    _assert_close(wo2_f + ws_f, 1.0, rel=0.0, abs_=2.0e-12, label="final heavy fraction sum")

    oxygen_i = 2.0 * RHO * (wo2_i + ws_i) / M_O2
    oxygen_f = 2.0 * RHO * (wo2_f + ws_f) / M_O2
    _assert_close(oxygen_f, oxygen_i, rel=2.0e-12, abs_=1.0e-14, label="oxygen-atom molar inventory")

    _assert_close(mean_i, EPSILON_REF_EV * eps_i / ne_i, label="initial solved mean energy")
    _assert_close(mean_f, EPSILON_REF_EV * eps_f / ne_f, label="final solved mean energy")
    _assert_close(mean_i, EPSILON_REF_EV, rel=0.0, abs_=1.0e-12, label="initial reference mean energy")
    if not mean_f < mean_i:
        raise AssertionError(f"EI10 energy loss did not reduce mean_en_solved: {mean_i} -> {mean_f}")

    if not (progress_f > 0.0 and so2_f < 0.0 < so2s_f):
        raise AssertionError((progress_f, so2_f, so2s_f))
    _assert_close(-so2_f / M_O2, progress_f, label="O2 source / shared R_O2s")
    _assert_close(so2s_f / M_O2, progress_f, label="O2s source / shared R_O2s")
    _assert_close(so2_f + so2s_f, 0.0, rel=0.0, abs_=1.0e-12, label="heavy source closure")

    expected_c_o2 = RHO * wo2_f / M_O2
    expected_progress = K_O2S * (N_REF * ne_f / N_A) * expected_c_o2
    _assert_close(progress_f, expected_progress, rel=3.0e-6, abs_=1.0e-14, label="shared constant-surrogate progress")

    _assert_close(RHO * (ws_f - ws_i) / DT, so2s_f, rel=5.0e-6, abs_=1.0e-12, label="O2s BE source closure")
    _assert_close(RHO * (wo2_f - wo2_i) / DT, so2_f, rel=5.0e-6, abs_=1.0e-12, label="constrained O2 BE source closure")

    normalized_rhs_f = -DELTA_E_EV * N_A * progress_f / (N_REF * EPSILON_REF_EV)
    residual_f = -normalized_rhs_f
    if not (normalized_rhs_f < 0.0 and residual_f > 0.0):
        raise AssertionError((normalized_rhs_f, residual_f))
    _assert_close((eps_f - eps_i) / DT, normalized_rhs_f, rel=5.0e-6, abs_=1.0e-8, label="EI10 n_epsilon backward-Euler closure")

    return {
        "initial": {"n_e_hat": ne_i, "n_epsilon_hat": eps_i, "w_O2": wo2_i, "w_O2s": ws_i, "mean_en_solved_eV": mean_i},
        "final": {"n_e_hat": ne_f, "n_epsilon_hat": eps_f, "w_O2": wo2_f, "w_O2s": ws_f, "mean_en_solved_eV": mean_f, "R_O2s_mol_m3_s": progress_f, "O2_source_kg_m3_s": so2_f, "O2s_source_kg_m3_s": so2s_f},
        "energy_closure": {"energy_loss_eV_per_event": DELTA_E_EV, "normalized_rhs_per_s": normalized_rhs_f, "residual_contribution_per_s": residual_f, "observed_dn_epsilon_hat_dt_per_s": (eps_f - eps_i) / DT, "electron_energy_delta_hat": eps_f - eps_i, "electron_particle_delta_hat": ne_f - ne_i},
        "particle_heavy_closure": {"heavy_fraction_sum": wo2_f + ws_f, "oxygen_atom_molar_inventory_initial": oxygen_i, "oxygen_atom_molar_inventory_final": oxygen_f, "k_O2s_m3_mol_s": K_O2S},
    }


def runtime_checker_self_test():
    a = DT * K_O2S * N_REF / N_A
    ws_f = (WP0 + a) / (1.0 + a)
    wo2_f = 1.0 - ws_f
    r0 = K_O2S * (N_REF / N_A) * (RHO * (1.0 - WP0) / M_O2)
    rf = K_O2S * (N_REF / N_A) * (RHO * wo2_f / M_O2)
    eps_f = 1.0 - DT * DELTA_E_EV * N_A * rf / (N_REF * EPSILON_REF_EV)
    rows = [
        {"n_e_hat_avg": 1.0, "n_epsilon_hat_avg": 1.0, "w_O2s_avg": WP0, "w_O2_avg": 1.0 - WP0, "mean_en_solved_avg": EPSILON_REF_EV, "R_O2s_avg": r0, "O2_source_avg": -M_O2 * r0, "O2s_source_avg": M_O2 * r0},
        {"n_e_hat_avg": 1.0, "n_epsilon_hat_avg": eps_f, "w_O2s_avg": ws_f, "w_O2_avg": wo2_f, "mean_en_solved_avg": EPSILON_REF_EV * eps_f, "R_O2s_avg": rf, "O2_source_avg": -M_O2 * rf, "O2s_source_avg": M_O2 * rf},
    ]
    validate_runtime_rows(rows)
    for mutate in ("electron_source", "energy_sign", "wrong_energy_identity", "shared_rate", "positivity"):
        bad = [dict(row) for row in rows]
        if mutate == "electron_source":
            bad[-1]["n_e_hat_avg"] *= 1.001
        elif mutate == "energy_sign":
            bad[-1]["n_epsilon_hat_avg"] = 1.001
            bad[-1]["mean_en_solved_avg"] = EPSILON_REF_EV * 1.001
        elif mutate == "wrong_energy_identity":
            bad[-1]["n_epsilon_hat_avg"] = 1.0 - DT * 9.97 * N_A * rf / (N_REF * EPSILON_REF_EV)
            bad[-1]["mean_en_solved_avg"] = EPSILON_REF_EV * bad[-1]["n_epsilon_hat_avg"]
        elif mutate == "shared_rate":
            bad[-1]["O2s_source_avg"] *= 1.01
        else:
            bad[-1]["w_O2s_avg"] = -1.0e-6
        try:
            validate_runtime_rows(bad)
        except AssertionError:
            pass
        else:
            raise AssertionError(f"E8 runtime checker mutation escaped: {mutate}")
    print("E8_EI10_INELASTIC_ENERGY_RUNTIME_CHECKER_SELFTEST_PASS")


def _sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_controlled_executable(executable, evidence_out=None, repository_sha=None, build_base_ref=None):
    executable = Path(executable).resolve()
    if not executable.is_file():
        raise SystemExit(f"Physics executable does not exist: {executable}")
    with tempfile.TemporaryDirectory(prefix="e8-ei10-energy-") as tmp:
        work = Path(tmp)
        input_name = "e8_ei10_energy_runtime.i"
        (work / input_name).write_text(RUNTIME_INPUT)
        subprocess.run([str(executable), "--check-input", "-i", input_name], cwd=work, check=True)
        subprocess.run([str(executable), "-i", input_name], cwd=work, check=True)
        rows = list(csv.DictReader((work / "e8_ei10_energy_runtime_out.csv").open(newline="")))
        evidence = validate_runtime_rows(rows)
        evidence.update({"runtime_mode": "direct_executable", "runtime_executable": str(executable), "runtime_executable_sha256": _sha256_file(executable), "claim": "#26 E8 EI10 bounded controlled local runtime discriminator", "integrated_physics_scope": "EI10 O2(a1Delta_g) inelastic electron-energy projection using the existing Stage-3 R_O2s only; elastic and other reaction-energy channels excluded"})
        if repository_sha:
            evidence["repository_sha"] = repository_sha
        if build_base_ref:
            evidence["build_base_ref"] = build_base_ref
        if evidence_out:
            Path(evidence_out).write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    final = evidence["final"]
    energy = evidence["energy_closure"]
    print("E8_EI10_INELASTIC_ENERGY_RUNTIME_VECTOR " f"n_e_hat={final['n_e_hat']:.12g} " f"n_epsilon_hat={final['n_epsilon_hat']:.12g} " f"mean_en_eV={final['mean_en_solved_eV']:.12g} " f"w_O2={final['w_O2']:.12g} " f"w_O2s={final['w_O2s']:.12g} " f"R={final['R_O2s_mol_m3_s']:.12g}")
    print("E8_EI10_INELASTIC_ENERGY_CLOSURE_VECTOR " f"delta_ne={energy['electron_particle_delta_hat']:.12g} " f"delta_nepsilon={energy['electron_energy_delta_hat']:.12g} " f"rhs={energy['normalized_rhs_per_s']:.12g} " f"observed={energy['observed_dn_epsilon_hat_dt_per_s']:.12g}")
    print("E8_EI10_INELASTIC_ENERGY_LOCAL_RUNTIME_PASS")


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--executable", help="direct Physics executable for governed JIT-capable E8 runtime")
    mode.add_argument("--self-test", action="store_true", help="run only the E8 runtime checker mutation tests")
    parser.add_argument("--evidence-out", help="optional JSON evidence path for controlled E8 runtime")
    parser.add_argument("--repository-sha", help="repository SHA associated with --executable")
    parser.add_argument("--build-base-ref", help="immutable build-base identity associated with --executable")
    args = parser.parse_args()
    if args.executable:
        run_controlled_executable(args.executable, args.evidence_out, repository_sha=args.repository_sha, build_base_ref=args.build_base_ref)
    else:
        runtime_checker_self_test()


if __name__ == "__main__":
    main()
