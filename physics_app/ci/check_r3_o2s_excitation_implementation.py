#!/usr/bin/env python3
"""Production ownership and governed-runtime discriminator for #176 R3 O2s excitation."""

import argparse
import csv
import hashlib
import json
import math
import re
import subprocess
import tempfile
from pathlib import Path

N_A = 6.02214076e23
M_O2 = 31.998e-3
N_REF = 1.0e16
RHO = 3.1998e-5
DT = 1.0e-7
EPSILON_REF_EV = 5.73276
WP0 = 1.0e-3
K_O2S = 4.71e8

CONTRACT = Path("docs/development/2026-09-10_issue17_r3_o2s_excitation_contract.json")
RATE = Path("physics_app/src/materials/PhysicsElectronImpactO2sExcitationMaterial.C")
PROJ = Path("physics_app/src/materials/PhysicsO2sExcitationSourceMaterial.C")

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
  [r3_o2s_rate]
    type = PhysicsElectronImpactO2sExcitationMaterial
    electron_number_density = n_e_physical
    o2_molar_concentration = c_O2
  []
  [r3_o2s_projection]
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


def _assert_close(actual, expected, *, rel=2.0e-6, abs_=1.0e-12, label="value"):
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

    if not (ne_i > 0.0 and eps_i >= 0.0):
        raise AssertionError((ne_i, eps_i))
    _assert_close(ne_f, ne_i, rel=0.0, abs_=1.0e-12, label="zero EI10 electron-particle source")
    _assert_close(eps_f, eps_i, rel=0.0, abs_=1.0e-12, label="Stage-3 zero electron-energy source")
    if not (0.0 <= ws_i < ws_f < 1.0 and wo2_i > wo2_f > 0.0):
        raise AssertionError((ws_i, ws_f, wo2_i, wo2_f))

    _assert_close(wo2_i + ws_i, 1.0, rel=0.0, abs_=2.0e-12, label="initial heavy fraction sum")
    _assert_close(wo2_f + ws_f, 1.0, rel=0.0, abs_=2.0e-12, label="final heavy fraction sum")
    oxygen_i = 2.0 * RHO * (wo2_i + ws_i) / M_O2
    oxygen_f = 2.0 * RHO * (wo2_f + ws_f) / M_O2
    _assert_close(oxygen_f, oxygen_i, rel=2.0e-12, abs_=1.0e-14, label="oxygen-atom molar inventory")

    _assert_close(mean_i, EPSILON_REF_EV * eps_i / ne_i, label="initial solved mean energy")
    _assert_close(mean_f, EPSILON_REF_EV * eps_f / ne_f, label="final solved mean energy")
    _assert_close(mean_i, EPSILON_REF_EV, rel=0.0, abs_=1.0e-12, label="surrogate reference mean energy")
    _assert_close(mean_f, mean_i, rel=0.0, abs_=1.0e-12, label="unchanged mean energy")

    if not (progress_f > 0.0 and so2_f < 0.0 < so2s_f):
        raise AssertionError((progress_f, so2_f, so2s_f))
    _assert_close(-so2_f / M_O2, progress_f, label="O2 source / shared R_O2s")
    _assert_close(so2s_f / M_O2, progress_f, label="O2s source / shared R_O2s")
    _assert_close(so2_f + so2s_f, 0.0, rel=0.0, abs_=1.0e-12, label="heavy source closure")

    expected_c_o2 = RHO * wo2_f / M_O2
    expected_progress = K_O2S * (N_REF * ne_f / N_A) * expected_c_o2
    _assert_close(progress_f, expected_progress, rel=3.0e-6, abs_=1.0e-14, label="constant-surrogate runtime progress")

    _assert_close(RHO * (ws_f - ws_i) / DT, so2s_f, rel=4.0e-6, abs_=1.0e-12, label="O2s BE source closure")
    _assert_close(RHO * (wo2_f - wo2_i) / DT, so2_f, rel=4.0e-6, abs_=1.0e-12, label="constrained O2 BE source closure")

    return {
        "initial": {
            "n_e_hat": ne_i,
            "n_epsilon_hat": eps_i,
            "w_O2": wo2_i,
            "w_O2s": ws_i,
            "mean_en_solved_eV": mean_i,
        },
        "final": {
            "n_e_hat": ne_f,
            "n_epsilon_hat": eps_f,
            "w_O2": wo2_f,
            "w_O2s": ws_f,
            "mean_en_solved_eV": mean_f,
            "R_O2s_mol_m3_s": progress_f,
            "O2_source_kg_m3_s": so2_f,
            "O2s_source_kg_m3_s": so2s_f,
        },
        "closure": {
            "heavy_fraction_sum": wo2_f + ws_f,
            "oxygen_atom_molar_inventory_initial": oxygen_i,
            "oxygen_atom_molar_inventory_final": oxygen_f,
            "electron_particle_delta_hat": ne_f - ne_i,
            "electron_energy_delta_hat": eps_f - eps_i,
            "k_O2s_m3_mol_s": K_O2S,
        },
    }


def runtime_checker_self_test():
    a = DT * K_O2S * N_REF / N_A
    ws_f = (WP0 + a) / (1.0 + a)
    wo2_f = 1.0 - ws_f
    r0 = K_O2S * (N_REF / N_A) * (RHO * (1.0 - WP0) / M_O2)
    rf = K_O2S * (N_REF / N_A) * (RHO * wo2_f / M_O2)
    rows = [
        {
            "n_e_hat_avg": 1.0,
            "n_epsilon_hat_avg": 1.0,
            "w_O2s_avg": WP0,
            "w_O2_avg": 1.0 - WP0,
            "mean_en_solved_avg": EPSILON_REF_EV,
            "R_O2s_avg": r0,
            "O2_source_avg": -M_O2 * r0,
            "O2s_source_avg": M_O2 * r0,
        },
        {
            "n_e_hat_avg": 1.0,
            "n_epsilon_hat_avg": 1.0,
            "w_O2s_avg": ws_f,
            "w_O2_avg": wo2_f,
            "mean_en_solved_avg": EPSILON_REF_EV,
            "R_O2s_avg": rf,
            "O2_source_avg": -M_O2 * rf,
            "O2s_source_avg": M_O2 * rf,
        },
    ]
    validate_runtime_rows(rows)

    for mutate in ("electron_source", "energy_source", "shared_rate", "positivity"):
        bad = [dict(row) for row in rows]
        if mutate == "electron_source":
            bad[-1]["n_e_hat_avg"] *= 1.001
        elif mutate == "energy_source":
            bad[-1]["n_epsilon_hat_avg"] *= 0.999
        elif mutate == "shared_rate":
            bad[-1]["O2s_source_avg"] *= 1.01
        else:
            bad[-1]["w_O2s_avg"] = -1.0e-6
        try:
            validate_runtime_rows(bad)
        except AssertionError:
            pass
        else:
            raise AssertionError(f"runtime checker mutation escaped: {mutate}")

    print("R3_O2S_EXCITATION_RUNTIME_CHECKER_SELFTEST_PASS")


def static_implementation_gate():
    contract = json.loads(CONTRACT.read_text())
    rate = RATE.read_text()
    proj = PROJ.read_text()

    assert 'registerMooseObject("PhysicsApp", PhysicsElectronImpactO2sExcitationMaterial);' in rate
    assert 'addFunctorProperty<ADReal>(\n      "R_O2s"' in rate
    assert '_electron_number_density(getFunctor<ADReal>("electron_number_density"))' in rate
    assert '_o2_molar_concentration(getFunctor<ADReal>("o2_molar_concentration"))' in rate
    assert 'return K_O2S * (n_e / N_A) * c_o2;' in rate
    assert 'requires n_e >= 0' in rate and 'requires c_O2 >= 0' in rate

    match = re.search(r"constexpr Real K_O2S = ([0-9.eE+-]+);", rate)
    assert match, "frozen R3 coefficient is not explicit in the canonical rate owner"
    implementation_k = float(match.group(1))
    canonical_k = contract["constant_surrogate_model"][
        "canonical_physics_molar_coefficient_m3_per_mol_s"
    ]
    assert implementation_k == canonical_k == K_O2S

    for forbidden in (
        "O2_o2s_excitation_mass_source",
        "O2s_excitation_mass_source",
        "electron_O2s",
        "electron_energy",
        "0.977",
        "9.97",
    ):
        assert forbidden not in rate

    assert 'registerMooseObject("PhysicsApp", PhysicsO2sExcitationSourceMaterial);' in proj
    assert '_reaction_progress(getFunctor<ADReal>("reaction_progress"))' in proj
    assert '"O2_o2s_excitation_mass_source"' in proj
    assert '"O2s_excitation_mass_source"' in proj
    assert 'return -_o2_molar_mass * R;' in proj
    assert 'return _o2_molar_mass * R;' in proj
    for forbidden in (
        "K_O2S",
        "4.71e8",
        "N_A",
        "mean_energy",
        "electron_number_density",
        "electron_energy",
        "0.977",
        "9.97",
    ):
        assert forbidden not in proj

    R = canonical_k * (N_REF / N_A) * (RHO * 0.999 / M_O2)
    s_o2 = -M_O2 * R
    s_o2s = M_O2 * R
    assert R > 0.0 and s_o2 < 0.0 < s_o2s
    assert math.isclose(s_o2 + s_o2s, 0.0, rel_tol=0.0, abs_tol=1.0e-14)
    assert math.isclose(-s_o2 / M_O2, R, rel_tol=1.0e-15)
    assert math.isclose(s_o2s / M_O2, R, rel_tol=1.0e-15)

    electron_number_source = 0.0
    assert electron_number_source == contract["reaction"]["expected_electron_particle_source"]
    assert contract["reaction"]["net_electron_stoich"] == 0
    assert contract["source_ownership"]["energy_coupling_enabled"] is False
    assert contract["source_ownership"]["electron_energy"] == "DEFERRED_TO_STAGE_4_ISSUE_26_E8"

    assert not math.isclose(s_o2 + 1.01 * s_o2s, 0.0, rel_tol=0.0, abs_tol=1.0e-14)
    assert N_A * 0.01 * R != 0.0

    runtime_checker_self_test()
    print("R3_O2S_EXCITATION_IMPLEMENTATION_PASS")


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

    with tempfile.TemporaryDirectory(prefix="r3-o2s-excitation-") as tmp:
        work = Path(tmp)
        (work / "r3_o2s_excitation_runtime.i").write_text(RUNTIME_INPUT)
        subprocess.run(
            [str(executable), "--check-input", "-i", "r3_o2s_excitation_runtime.i"],
            cwd=work,
            check=True,
        )
        subprocess.run(
            [str(executable), "-i", "r3_o2s_excitation_runtime.i"],
            cwd=work,
            check=True,
        )
        rows = list(csv.DictReader((work / "r3_o2s_excitation_runtime_out.csv").open(newline="")))
        evidence = validate_runtime_rows(rows)
        evidence.update(
            {
                "runtime_mode": "direct_executable",
                "runtime_executable": str(executable),
                "runtime_executable_sha256": _sha256_file(executable),
                "claim": "R3 O2(a1Delta_g) controlled local runtime/integration discriminator",
                "integrated_physics_scope": "EI10 particle coupling at frozen reference surrogate only; electron-energy coupling and full real-QVT network excluded",
            }
        )
        if repository_sha:
            evidence["repository_sha"] = repository_sha
        if build_base_ref:
            evidence["build_base_ref"] = build_base_ref
        if evidence_out:
            Path(evidence_out).write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")

    final = evidence["final"]
    closure = evidence["closure"]
    print(
        "R3_O2S_EXCITATION_RUNTIME_VECTOR "
        f"n_e_hat={final['n_e_hat']:.12g} "
        f"n_epsilon_hat={final['n_epsilon_hat']:.12g} "
        f"w_O2={final['w_O2']:.12g} "
        f"w_O2s={final['w_O2s']:.12g} "
        f"mean_en_eV={final['mean_en_solved_eV']:.12g} "
        f"R={final['R_O2s_mol_m3_s']:.12g}"
    )
    print(
        "R3_O2S_EXCITATION_CLOSURE_VECTOR "
        f"sum_w={closure['heavy_fraction_sum']:.12g} "
        f"delta_ne={closure['electron_particle_delta_hat']:.12g} "
        f"delta_nepsilon={closure['electron_energy_delta_hat']:.12g}"
    )
    print("R3_O2S_EXCITATION_LOCAL_RUNTIME_PASS")


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--executable", help="direct Physics executable for governed JIT-capable R3 P3")
    mode.add_argument("--self-test", action="store_true", help="run only the R3 runtime checker P0 self-test")
    parser.add_argument("--evidence-out", help="optional JSON evidence path for controlled R3 P3")
    parser.add_argument("--repository-sha", help="repository SHA associated with --executable")
    parser.add_argument("--build-base-ref", help="immutable build-base identity associated with --executable")
    args = parser.parse_args()

    if args.executable:
        run_controlled_executable(
            args.executable,
            args.evidence_out,
            repository_sha=args.repository_sha,
            build_base_ref=args.build_base_ref,
        )
    elif args.self_test:
        runtime_checker_self_test()
    else:
        static_implementation_gate()


if __name__ == "__main__":
    main()
