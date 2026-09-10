#!/usr/bin/env python3
"""Governed-runtime discriminator for #26 E8-I2 EI16 O2 ionization energy coupling."""

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
DELTA_E_EV = 12.06
LOOKUP_MIN_EV = 1.40991
LOOKUP_MAX_EV = 22.1378
WP0 = 1.0e-3
RATE_TABLE = (
    (LOOKUP_MIN_EV, 8.0e8),
    (EPSILON_REF_EV, 1.0e9),
    (LOOKUP_MAX_EV, 1.2e9),
)

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
  [w_O2p]
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
    functor_names = 'w_O2p'
    functor_symbols = 'wp'
    expression = '1.0-wp'
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
  [ei16_ionization_rate]
    type = PhysicsElectronImpactIonizationMaterial
    rate_table_file = e8_ei16_runtime_table.txt
    mean_energy = mean_en_solved
    electron_number_density = n_e_physical
    o2_molar_concentration = c_O2
  []
  [ei16_particle_projection]
    type = PhysicsO2IonizationSourceMaterial
    reaction_progress = R_ion_O2
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
  [ei16_energy_loss]
    type = PhysicsFVElectronReactionEnergySource
    variable = n_epsilon
    reaction_progress = R_ion_O2
    energy_loss_eV = 12.06
    n_ref = 1.0e16
    energy_reference_eV = 5.73276
  []
  [w_O2p_time]
    type = PhysicsFVMassFractionTimeDerivative
    variable = w_O2p
    rho = rho_const
  []
  [w_O2p_source]
    type = PhysicsFVSpeciesReactionSource
    variable = w_O2p
    source = O2p_ionization_mass_source
  []
  [n_e_source]
    type = PhysicsFVElectronReactionSource
    variable = n_e
    number_source = electron_ionization_number_source
    n_ref = 1.0e16
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
  [w_O2p_avg]
    type = ElementAverageFunctorPostprocessor
    functor = w_O2p
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
  [R_ion_O2_avg]
    type = ElementAverageFunctorPostprocessor
    functor = R_ion_O2
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [O2_source_avg]
    type = ElementAverageFunctorPostprocessor
    functor = O2_ionization_mass_source
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [O2p_source_avg]
    type = ElementAverageFunctorPostprocessor
    functor = O2p_ionization_mass_source
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [electron_source_avg]
    type = ElementAverageFunctorPostprocessor
    functor = electron_ionization_number_source
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


def _assert_close(actual, expected, *, rel=5.0e-6, abs_=1.0e-12, label="value"):
    if not math.isclose(actual, expected, rel_tol=rel, abs_tol=abs_):
        raise AssertionError(f"{label}: actual={actual:.17g} expected={expected:.17g}")


def _interp_rate(mean_energy):
    if not (LOOKUP_MIN_EV <= mean_energy <= LOOKUP_MAX_EV):
        raise AssertionError(f"mean energy outside strict lookup range: {mean_energy}")
    for (x0, y0), (x1, y1) in zip(RATE_TABLE, RATE_TABLE[1:]):
        if x0 <= mean_energy <= x1:
            return y0 + (mean_energy - x0) * (y1 - y0) / (x1 - x0)
    raise AssertionError(f"failed to bracket mean energy: {mean_energy}")


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
    wp_i = _f(initial, "w_O2p_avg")
    wp_f = _f(final, "w_O2p_avg")
    wo2_i = _f(initial, "w_O2_avg")
    wo2_f = _f(final, "w_O2_avg")
    mean_i = _f(initial, "mean_en_solved_avg")
    mean_f = _f(final, "mean_en_solved_avg")
    progress_f = _f(final, "R_ion_O2_avg")
    so2_f = _f(final, "O2_source_avg")
    so2p_f = _f(final, "O2p_source_avg")
    se_f = _f(final, "electron_source_avg")

    if not (ne_i > 0.0 and ne_f > ne_i and eps_i > 0.0 and 0.0 < eps_f < eps_i):
        raise AssertionError((ne_i, ne_f, eps_i, eps_f))
    if not (0.0 <= wp_i < wp_f < 1.0 and wo2_i > wo2_f > 0.0):
        raise AssertionError((wp_i, wp_f, wo2_i, wo2_f))
    if not (LOOKUP_MIN_EV <= mean_i <= LOOKUP_MAX_EV and LOOKUP_MIN_EV <= mean_f <= LOOKUP_MAX_EV):
        raise AssertionError((mean_i, mean_f))

    _assert_close(wo2_i + wp_i, 1.0, rel=0.0, abs_=2.0e-12, label="initial heavy fraction sum")
    _assert_close(wo2_f + wp_f, 1.0, rel=0.0, abs_=2.0e-12, label="final heavy fraction sum")
    oxygen_i = 2.0 * RHO * (wo2_i + wp_i) / M_O2
    oxygen_f = 2.0 * RHO * (wo2_f + wp_f) / M_O2
    _assert_close(oxygen_f, oxygen_i, rel=2.0e-12, abs_=1.0e-14, label="oxygen-atom inventory")

    if not (progress_f > 0.0 and so2_f < 0.0 < so2p_f and se_f > 0.0):
        raise AssertionError((progress_f, so2_f, so2p_f, se_f))
    _assert_close(-so2_f / M_O2, progress_f, label="O2 / shared R_ion_O2")
    _assert_close(so2p_f / M_O2, progress_f, label="O2p / shared R_ion_O2")
    _assert_close(se_f / N_A, progress_f, label="electron / shared R_ion_O2")
    _assert_close(so2_f + so2p_f, 0.0, rel=0.0, abs_=1.0e-11, label="heavy source closure")

    _assert_close(mean_i, EPSILON_REF_EV * eps_i / ne_i, label="initial solved mean energy")
    _assert_close(mean_f, EPSILON_REF_EV * eps_f / ne_f, label="final solved mean energy")
    if not mean_f < mean_i:
        raise AssertionError(f"EI16 coupled energy loss did not reduce mean energy: {mean_i} -> {mean_f}")

    expected_k = _interp_rate(mean_f)
    expected_c_o2 = RHO * wo2_f / M_O2
    expected_progress = expected_k * (N_REF * ne_f / N_A) * expected_c_o2
    _assert_close(progress_f, expected_progress, rel=4.0e-6, abs_=1.0e-14, label="strict-lookup final R_ion_O2")

    _assert_close(N_REF * (ne_f - ne_i) / DT, se_f, rel=5.0e-6, abs_=1.0, label="electron BE closure")
    _assert_close(RHO * (wp_f - wp_i) / DT, so2p_f, rel=5.0e-6, abs_=1.0e-12, label="O2p BE closure")
    _assert_close(RHO * (wo2_f - wo2_i) / DT, so2_f, rel=5.0e-6, abs_=1.0e-12, label="constrained O2 BE closure")

    delta_e = N_REF * (ne_f - ne_i)
    delta_o2p = N_A * RHO * (wp_f - wp_i) / M_O2
    _assert_close(delta_e, delta_o2p, rel=6.0e-6, abs_=1.0, label="electron-inclusive charge closure")

    normalized_rhs = -DELTA_E_EV * N_A * progress_f / (N_REF * EPSILON_REF_EV)
    residual = -normalized_rhs
    observed = (eps_f - eps_i) / DT
    if not (normalized_rhs < 0.0 < residual and observed < 0.0):
        raise AssertionError((normalized_rhs, residual, observed))
    _assert_close(observed, normalized_rhs, rel=6.0e-6, abs_=1.0e-8, label="EI16 energy BE closure")

    return {
        "initial": {"n_e_hat": ne_i, "n_epsilon_hat": eps_i, "w_O2": wo2_i, "w_O2p": wp_i, "mean_en_solved_eV": mean_i},
        "final": {"n_e_hat": ne_f, "n_epsilon_hat": eps_f, "w_O2": wo2_f, "w_O2p": wp_f, "mean_en_solved_eV": mean_f, "R_ion_O2_mol_m3_s": progress_f, "O2_source_kg_m3_s": so2_f, "O2p_source_kg_m3_s": so2p_f, "electron_source_m3_s": se_f},
        "energy_closure": {"energy_loss_eV_per_event": DELTA_E_EV, "normalized_rhs_per_s": normalized_rhs, "residual_contribution_per_s": residual, "observed_dn_epsilon_hat_dt_per_s": observed, "electron_energy_delta_hat": eps_f - eps_i},
        "particle_heavy_charge_closure": {"heavy_fraction_sum": wo2_f + wp_f, "oxygen_atom_inventory_initial": oxygen_i, "oxygen_atom_inventory_final": oxygen_f, "charge_delta_e": delta_e, "charge_delta_o2p": delta_o2p, "lookup_k_m3_mol_s": expected_k},
    }


def _fixed_point_rows():
    progress = 0.0
    for _ in range(200):
        ne = 1.0 + DT * N_A * progress / N_REF
        wp = WP0 + DT * M_O2 * progress / RHO
        eps = 1.0 - DT * DELTA_E_EV * N_A * progress / (N_REF * EPSILON_REF_EV)
        mean = EPSILON_REF_EV * eps / ne
        new_progress = _interp_rate(mean) * (N_REF * ne / N_A) * (RHO * (1.0 - wp) / M_O2)
        if math.isclose(new_progress, progress, rel_tol=1.0e-14, abs_tol=1.0e-18):
            progress = new_progress
            break
        progress = new_progress
    ne = 1.0 + DT * N_A * progress / N_REF
    wp = WP0 + DT * M_O2 * progress / RHO
    eps = 1.0 - DT * DELTA_E_EV * N_A * progress / (N_REF * EPSILON_REF_EV)
    mean = EPSILON_REF_EV * eps / ne
    r0 = _interp_rate(EPSILON_REF_EV) * (N_REF / N_A) * (RHO * (1.0 - WP0) / M_O2)
    return [
        {"n_e_hat_avg": 1.0, "n_epsilon_hat_avg": 1.0, "w_O2p_avg": WP0, "w_O2_avg": 1.0 - WP0, "mean_en_solved_avg": EPSILON_REF_EV, "R_ion_O2_avg": r0, "O2_source_avg": -M_O2 * r0, "O2p_source_avg": M_O2 * r0, "electron_source_avg": N_A * r0},
        {"n_e_hat_avg": ne, "n_epsilon_hat_avg": eps, "w_O2p_avg": wp, "w_O2_avg": 1.0 - wp, "mean_en_solved_avg": mean, "R_ion_O2_avg": progress, "O2_source_avg": -M_O2 * progress, "O2p_source_avg": M_O2 * progress, "electron_source_avg": N_A * progress},
    ]


def runtime_checker_self_test():
    rows = _fixed_point_rows()
    validate_runtime_rows(rows)
    for mutate in ("shared_rate", "energy_sign", "energy_identity", "lookup_range", "charge"):
        bad = [dict(row) for row in rows]
        if mutate == "shared_rate":
            bad[-1]["electron_source_avg"] *= 1.01
        elif mutate == "energy_sign":
            bad[-1]["n_epsilon_hat_avg"] = 1.001
            bad[-1]["mean_en_solved_avg"] = EPSILON_REF_EV * bad[-1]["n_epsilon_hat_avg"] / bad[-1]["n_e_hat_avg"]
        elif mutate == "energy_identity":
            progress = bad[-1]["R_ion_O2_avg"]
            wrong_eps = 1.0 - DT * 0.977 * N_A * progress / (N_REF * EPSILON_REF_EV)
            bad[-1]["n_epsilon_hat_avg"] = wrong_eps
            bad[-1]["mean_en_solved_avg"] = EPSILON_REF_EV * wrong_eps / bad[-1]["n_e_hat_avg"]
        elif mutate == "lookup_range":
            bad[-1]["mean_en_solved_avg"] = LOOKUP_MIN_EV - 0.1
        else:
            bad[-1]["w_O2p_avg"] *= 1.02
        try:
            validate_runtime_rows(bad)
        except AssertionError:
            pass
        else:
            raise AssertionError(f"E8 EI16 runtime checker mutation escaped: {mutate}")
    print("E8_EI16_O2_IONIZATION_ENERGY_RUNTIME_CHECKER_SELFTEST_PASS")


def _prepare_fixture(work):
    (work / "e8_ei16_energy_runtime.i").write_text(RUNTIME_INPUT)
    (work / "e8_ei16_runtime_table.txt").write_text("".join(f"{energy:.8g} {rate:.17g}\n" for energy, rate in RATE_TABLE))


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
    with tempfile.TemporaryDirectory(prefix="e8-ei16-energy-") as tmp:
        work = Path(tmp)
        _prepare_fixture(work)
        subprocess.run([str(executable), "--check-input", "-i", "e8_ei16_energy_runtime.i"], cwd=work, check=True)
        subprocess.run([str(executable), "-i", "e8_ei16_energy_runtime.i"], cwd=work, check=True)
        rows = list(csv.DictReader((work / "e8_ei16_energy_runtime_out.csv").open(newline="")))
        evidence = validate_runtime_rows(rows)
        evidence.update({"runtime_mode": "direct_executable", "runtime_executable": str(executable), "runtime_executable_sha256": _sha256_file(executable), "claim": "#26 E8-I2 EI16 bounded controlled local runtime discriminator", "integrated_physics_scope": "EI16 O2 ionization particle/heavy/electron + 12.06 eV energy projection using the same synthetic-discriminator R_ion_O2; not physical rate provenance or full real-QVT"})
        if repository_sha:
            evidence["repository_sha"] = repository_sha
        if build_base_ref:
            evidence["build_base_ref"] = build_base_ref
        if evidence_out:
            Path(evidence_out).write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    f = evidence["final"]
    e = evidence["energy_closure"]
    c = evidence["particle_heavy_charge_closure"]
    print("E8_EI16_RUNTIME_VECTOR " f"n_e_hat={f['n_e_hat']:.12g} n_epsilon_hat={f['n_epsilon_hat']:.12g} mean_en_eV={f['mean_en_solved_eV']:.12g} w_O2={f['w_O2']:.12g} w_O2p={f['w_O2p']:.12g} R={f['R_ion_O2_mol_m3_s']:.12g}")
    print("E8_EI16_CLOSURE_VECTOR " f"delta_e={c['charge_delta_e']:.12g} delta_O2p={c['charge_delta_o2p']:.12g} rhs={e['normalized_rhs_per_s']:.12g} observed={e['observed_dn_epsilon_hat_dt_per_s']:.12g}")
    print("E8_EI16_O2_IONIZATION_ENERGY_LOCAL_RUNTIME_PASS")


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--executable", help="direct Physics executable in governed JIT-capable lane")
    mode.add_argument("--self-test", action="store_true", help="run runtime checker mutation tests")
    parser.add_argument("--evidence-out")
    parser.add_argument("--repository-sha")
    parser.add_argument("--build-base-ref")
    args = parser.parse_args()
    if args.executable:
        run_controlled_executable(args.executable, args.evidence_out, args.repository_sha, args.build_base_ref)
    else:
        runtime_checker_self_test()


if __name__ == "__main__":
    main()
