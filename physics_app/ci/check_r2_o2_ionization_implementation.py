#!/usr/bin/env python3
"""Source/ownership and controlled-runtime gate for #176 R2 O2 ionization."""

import argparse
import csv
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
LOOKUP_MIN_EV = 1.40991
LOOKUP_MAX_EV = 22.1378
WP0 = 1.0e-3
RATE_TABLE = (
    (LOOKUP_MIN_EV, 8.0e8),
    (EPSILON_REF_EV, 1.0e9),
    (LOOKUP_MAX_EV, 1.2e9),
)
RUNTIME_REF_RE = re.compile(
    r"^ghcr\.io/hyungseonsong-plasma/physics-runtime@sha256:[0-9a-f]{64}$"
)

RATE = Path("physics_app/src/materials/PhysicsElectronImpactIonizationMaterial.C")
PROJ = Path("physics_app/src/materials/PhysicsO2IonizationSourceMaterial.C")
EK = Path("physics_app/src/fvkernels/PhysicsFVElectronReactionSource.C")

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
  [r2_ionization_rate]
    type = PhysicsElectronImpactIonizationMaterial
    rate_table_file = r2_o2_ionization_runtime_table.txt
    mean_energy = mean_en_solved
    electron_number_density = n_e_physical
    o2_molar_concentration = c_O2
  []
  [r2_source_projection]
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


def _assert_close(actual, expected, *, rel=2.0e-6, abs_=1.0e-12, label="value"):
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

    if not (ne_i > 0.0 and ne_f > ne_i and eps_i >= 0.0 and eps_f >= 0.0):
        raise AssertionError((ne_i, ne_f, eps_i, eps_f))
    if not (0.0 <= wp_i < 1.0 and 0.0 <= wp_f < 1.0 and wo2_i > 0.0 and wo2_f > 0.0):
        raise AssertionError((wp_i, wp_f, wo2_i, wo2_f))
    if not (LOOKUP_MIN_EV <= mean_i <= LOOKUP_MAX_EV and LOOKUP_MIN_EV <= mean_f <= LOOKUP_MAX_EV):
        raise AssertionError((mean_i, mean_f))
    _assert_close(eps_f, eps_i, rel=0.0, abs_=1.0e-12, label="Stage-3 energy state")

    _assert_close(wo2_i + wp_i, 1.0, rel=0.0, abs_=2.0e-12, label="initial heavy fraction sum")
    _assert_close(wo2_f + wp_f, 1.0, rel=0.0, abs_=2.0e-12, label="final heavy fraction sum")
    oxygen_i = 2.0 * RHO * (wo2_i + wp_i) / M_O2
    oxygen_f = 2.0 * RHO * (wo2_f + wp_f) / M_O2
    _assert_close(oxygen_f, oxygen_i, rel=2.0e-12, abs_=1.0e-14, label="oxygen-atom molar inventory")

    if not (progress_f > 0.0 and so2_f < 0.0 < so2p_f and se_f > 0.0):
        raise AssertionError((progress_f, so2_f, so2p_f, se_f))
    _assert_close(-so2_f / M_O2, progress_f, label="O2 source / shared progress")
    _assert_close(so2p_f / M_O2, progress_f, label="O2p source / shared progress")
    _assert_close(se_f / N_A, progress_f, label="electron source / shared progress")
    _assert_close(so2_f + so2p_f, 0.0, rel=0.0, abs_=1.0e-11, label="heavy source closure")

    _assert_close(mean_i, EPSILON_REF_EV * eps_i / ne_i, label="initial solved mean energy")
    _assert_close(mean_f, EPSILON_REF_EV * eps_f / ne_f, label="final solved mean energy")
    expected_k = _interp_rate(mean_f)
    expected_c_o2 = RHO * wo2_f / M_O2
    expected_progress = expected_k * (N_REF * ne_f / N_A) * expected_c_o2
    _assert_close(progress_f, expected_progress, rel=3.0e-6, abs_=1.0e-14, label="runtime lookup progress")

    _assert_close(N_REF * (ne_f - ne_i) / DT, se_f, rel=4.0e-6, abs_=1.0, label="electron BE source closure")
    _assert_close(RHO * (wp_f - wp_i) / DT, so2p_f, rel=4.0e-6, abs_=1.0e-12, label="O2p BE source closure")
    _assert_close(RHO * (wo2_f - wo2_i) / DT, so2_f, rel=4.0e-6, abs_=1.0e-12, label="constrained O2 BE source closure")

    delta_e = N_REF * (ne_f - ne_i)
    delta_o2p = N_A * RHO * (wp_f - wp_i) / M_O2
    _assert_close(delta_e, delta_o2p, rel=5.0e-6, abs_=1.0, label="electron-inclusive charge closure")

    return {
        "initial": {
            "n_e_hat": ne_i,
            "n_epsilon_hat": eps_i,
            "w_O2": wo2_i,
            "w_O2p": wp_i,
            "mean_en_solved_eV": mean_i,
        },
        "final": {
            "n_e_hat": ne_f,
            "n_epsilon_hat": eps_f,
            "w_O2": wo2_f,
            "w_O2p": wp_f,
            "mean_en_solved_eV": mean_f,
            "R_ion_O2_mol_m3_s": progress_f,
            "O2_source_kg_m3_s": so2_f,
            "O2p_source_kg_m3_s": so2p_f,
            "electron_source_m3_s": se_f,
        },
        "closure": {
            "heavy_fraction_sum": wo2_f + wp_f,
            "charge_delta_e": delta_e,
            "charge_delta_o2p": delta_o2p,
            "lookup_k_m3_mol_s": expected_k,
        },
    }


def runtime_checker_self_test():
    progress = 0.0
    for _ in range(100):
        ne = 1.0 + DT * N_A * progress / N_REF
        wp = WP0 + DT * M_O2 * progress / RHO
        mean = EPSILON_REF_EV / ne
        k = _interp_rate(mean)
        new_progress = k * (N_REF * ne / N_A) * (RHO * (1.0 - wp) / M_O2)
        if math.isclose(new_progress, progress, rel_tol=1.0e-14, abs_tol=1.0e-18):
            progress = new_progress
            break
        progress = new_progress
    ne = 1.0 + DT * N_A * progress / N_REF
    wp = WP0 + DT * M_O2 * progress / RHO
    mean = EPSILON_REF_EV / ne
    r0 = _interp_rate(EPSILON_REF_EV) * (N_REF / N_A) * (RHO * (1.0 - WP0) / M_O2)
    rows = [
        {
            "n_e_hat_avg": 1.0,
            "n_epsilon_hat_avg": 1.0,
            "w_O2p_avg": WP0,
            "w_O2_avg": 1.0 - WP0,
            "mean_en_solved_avg": EPSILON_REF_EV,
            "R_ion_O2_avg": r0,
            "O2_source_avg": -M_O2 * r0,
            "O2p_source_avg": M_O2 * r0,
            "electron_source_avg": N_A * r0,
        },
        {
            "n_e_hat_avg": ne,
            "n_epsilon_hat_avg": 1.0,
            "w_O2p_avg": wp,
            "w_O2_avg": 1.0 - wp,
            "mean_en_solved_avg": mean,
            "R_ion_O2_avg": progress,
            "O2_source_avg": -M_O2 * progress,
            "O2p_source_avg": M_O2 * progress,
            "electron_source_avg": N_A * progress,
        },
    ]
    validate_runtime_rows(rows)

    for mutate in ("shared_rate", "lookup_range", "positivity"):
        bad = [dict(row) for row in rows]
        if mutate == "shared_rate":
            bad[-1]["electron_source_avg"] *= 1.01
        elif mutate == "lookup_range":
            bad[-1]["mean_en_solved_avg"] = LOOKUP_MAX_EV + 1.0
        else:
            bad[-1]["w_O2p_avg"] = -1.0e-6
        try:
            validate_runtime_rows(bad)
        except AssertionError:
            pass
        else:
            raise AssertionError(f"runtime checker mutation escaped: {mutate}")

    print("R2_O2_IONIZATION_RUNTIME_CHECKER_SELFTEST_PASS")


def static_implementation_gate():
    rate = RATE.read_text()
    proj = PROJ.read_text()
    electron_kernel = EK.read_text()

    assert 'addFunctorProperty<ADReal>(\n      "R_ion_O2"' in rate
    assert 'interpolateStrict(_mean_energy(r, state)) * (n_e / N_A) * c_o2' in rate
    for forbidden in ("O2_ionization_mass_source", "O2p_ionization_mass_source", "electron_ionization_number_source"):
        assert forbidden not in rate
    assert "outside lookup range" in rate and "strict R2 policy forbids clamp/floor" in rate

    assert '_reaction_progress(getFunctor<ADReal>("reaction_progress"))' in proj
    assert '"O2_ionization_mass_source"' in proj
    assert '"O2p_ionization_mass_source"' in proj
    assert '"electron_ionization_number_source"' in proj
    for forbidden in ("PhysicsLookupTable1D", "interpolate", "mean_energy", "electron_number_density", "o2_molar_concentration"):
        assert forbidden not in proj

    assert '_number_source(getFunctor<ADReal>("number_source"))' in electron_kernel
    assert 'return -physical_number_source / _n_ref;' in electron_kernel

    progress = 2.5
    s_o2 = -M_O2 * progress
    s_o2p = M_O2 * progress
    s_e = N_A * progress
    assert s_o2 < 0 < s_o2p and s_e > 0
    assert math.isclose(s_o2 + s_o2p, 0.0, abs_tol=1e-14)
    assert math.isclose(-s_e + N_A * progress, 0.0, abs_tol=1e-6)
    assert not math.isclose(-s_e + N_A * (1.01 * progress), 0.0, abs_tol=1e-6)

    runtime_checker_self_test()
    print("R2_O2_IONIZATION_IMPLEMENTATION_PASS")


def run_controlled_runtime(runtime_ref, evidence_out=None):
    if not RUNTIME_REF_RE.fullmatch(runtime_ref):
        raise SystemExit(f"runtime_ref must be an immutable Physics runtime digest: {runtime_ref}")

    with tempfile.TemporaryDirectory(prefix="r2-o2-ionization-") as tmp:
        work = Path(tmp)
        (work / "r2_o2_ionization_runtime.i").write_text(RUNTIME_INPUT)
        (work / "r2_o2_ionization_runtime_table.txt").write_text(
            "".join(f"{energy:.8g} {rate:.17g}\n" for energy, rate in RATE_TABLE)
        )
        mount = f"{work.resolve()}:/work"
        base = ["docker", "run", "--rm", "-v", mount, "-w", "/work", runtime_ref]
        subprocess.run(base + ["--check-input", "-i", "r2_o2_ionization_runtime.i"], check=True)
        subprocess.run(base + ["-i", "r2_o2_ionization_runtime.i"], check=True)
        csv_path = work / "r2_o2_ionization_runtime_out.csv"
        rows = list(csv.DictReader(csv_path.open(newline="")))
        evidence = validate_runtime_rows(rows)
        evidence["runtime_ref"] = runtime_ref
        evidence["claim"] = "R2 controlled local runtime/integration discriminator"
        evidence["integrated_physics_scope"] = "reaction-only particle coupling; #26 E8 and full R2/R3 network excluded"
        if evidence_out:
            Path(evidence_out).write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")

    final = evidence["final"]
    closure = evidence["closure"]
    print(
        "R2_O2_IONIZATION_RUNTIME_VECTOR "
        f"n_e_hat={final['n_e_hat']:.12g} "
        f"w_O2={final['w_O2']:.12g} "
        f"w_O2p={final['w_O2p']:.12g} "
        f"mean_en_eV={final['mean_en_solved_eV']:.12g} "
        f"R={final['R_ion_O2_mol_m3_s']:.12g}"
    )
    print(
        "R2_O2_IONIZATION_CLOSURE_VECTOR "
        f"sum_w={closure['heavy_fraction_sum']:.12g} "
        f"delta_e={closure['charge_delta_e']:.12g} "
        f"delta_O2p={closure['charge_delta_o2p']:.12g}"
    )
    print("R2_O2_IONIZATION_LOCAL_RUNTIME_PASS")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-ref", help="immutable ghcr Physics runtime ref for controlled P3")
    parser.add_argument("--evidence-out", help="optional JSON evidence path for --runtime-ref")
    parser.add_argument("--self-test", action="store_true", help="run only the runtime checker P0 self-test")
    args = parser.parse_args()

    if args.runtime_ref:
        run_controlled_runtime(args.runtime_ref, args.evidence_out)
    elif args.self_test:
        runtime_checker_self_test()
    else:
        static_implementation_gate()


if __name__ == "__main__":
    main()
