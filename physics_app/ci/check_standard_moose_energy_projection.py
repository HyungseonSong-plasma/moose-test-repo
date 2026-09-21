#!/usr/bin/env python3
"""A/B discriminator proving #26 E8 energy projection can use standard MOOSE only."""

import argparse
import csv
import hashlib
import json
import math
import subprocess
import tempfile
from pathlib import Path

N_A = 6.02214076e23
N_REF = 1.0e16
EPSILON_REF_EV = 5.73276
M_O2 = 31.998e-3
RHO = 3.1998e-5
DT = 1.0e-7

EI10_DELTA_E_EV = 0.977
EI16_DELTA_E_EV = 12.06
EI10_COEF = -(EI10_DELTA_E_EV * N_A / (N_REF * EPSILON_REF_EV))
EI16_COEF = -(EI16_DELTA_E_EV * N_A / (N_REF * EPSILON_REF_EV))

# Accepted governed vectors from b882211eb24a94bb645d0c13ecd96badc2c35095.
EI10_ORACLE = {
    "n_e_hat_avg": 1.0,
    "n_epsilon_hat_avg": 0.99198106194124,
    "mean_en_solved_avg": 5.6867893526543,
    "w_O2_avg": 0.99899921866882,
    "w_O2s_avg": 0.0010007813311756,
    "R_O2s_avg": 0.0078133117564827,
}
EI16_ORACLE = {
    "n_e_hat_avg": 1.1016960590289,
    "n_epsilon_hat_avg": 0.78606212855788,
    "mean_en_solved_avg": 4.0903346174113,
    "w_O2_avg": 0.99899831129721,
    "w_O2p_avg": 0.00100168870279,
    "R_ion_O2_avg": 0.016887027897333,
}

EI10_INPUT = f"""[Mesh]
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
  [ei10_energy_loss_standard]
    type = FVCoupledForce
    variable = n_epsilon
    v = R_O2s
    coef = {EI10_COEF:.17g}
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

EI16_INPUT = f"""[Mesh]
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
  [ei16_rate]
    type = PhysicsElectronImpactIonizationMaterial
    rate_table_file = standard_ei16_runtime_table.txt
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
  [ei16_energy_loss_standard]
    type = FVCoupledForce
    variable = n_epsilon
    v = R_ion_O2
    coef = {EI16_COEF:.17g}
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

RATE_TABLE = (
    (1.40991, 8.0e8),
    (EPSILON_REF_EV, 1.0e9),
    (22.1378, 1.2e9),
)


def _assert_close(actual, expected, *, rel=8.0e-6, abs_=1.0e-12, label="value"):
    if not math.isclose(actual, expected, rel_tol=rel, abs_tol=abs_):
        raise AssertionError(f"{label}: actual={actual:.17g} expected={expected:.17g}")


def _validate_input_contract():
    assert "type = FVCoupledForce" in EI10_INPUT
    assert "v = R_O2s" in EI10_INPUT
    assert "type = FVCoupledForce" in EI16_INPUT
    assert "v = R_ion_O2" in EI16_INPUT
    assert "PhysicsFVElectronReactionEnergySource" not in EI10_INPUT
    assert "PhysicsFVElectronReactionEnergySource" not in EI16_INPUT
    _assert_close(-EI10_COEF, EI10_DELTA_E_EV * N_A / (N_REF * EPSILON_REF_EV), rel=1e-15)
    _assert_close(-EI16_COEF, EI16_DELTA_E_EV * N_A / (N_REF * EPSILON_REF_EV), rel=1e-15)


def _sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _final_row(path):
    rows = list(csv.DictReader(Path(path).open(newline="")))
    if len(rows) < 2:
        raise AssertionError(f"expected initial+final rows in {path}")
    return {k: float(v) for k, v in rows[-1].items() if k != "time"}


def _compare(name, actual, oracle):
    deltas = {}
    for key, expected in oracle.items():
        value = actual[key]
        _assert_close(value, expected, rel=8.0e-6, abs_=2.0e-12, label=f"{name}:{key}")
        deltas[key] = value - expected
    return deltas


def run(executable, evidence_out=None, repository_sha=None, build_base_ref=None):
    _validate_input_contract()
    executable = Path(executable).resolve()
    if not executable.is_file():
        raise SystemExit(f"Physics executable does not exist: {executable}")

    with tempfile.TemporaryDirectory(prefix="standard-moose-energy-") as tmp:
        work = Path(tmp)
        (work / "standard_ei10.i").write_text(EI10_INPUT)
        (work / "standard_ei16.i").write_text(EI16_INPUT)
        (work / "standard_ei16_runtime_table.txt").write_text(
            "".join(f"{x:.8g} {y:.17g}\n" for x, y in RATE_TABLE)
        )

        for input_name in ("standard_ei10.i", "standard_ei16.i"):
            subprocess.run([str(executable), "--check-input", "-i", input_name], cwd=work, check=True)
            subprocess.run([str(executable), "-i", input_name], cwd=work, check=True)

        ei10 = _final_row(work / "standard_ei10_out.csv")
        ei16 = _final_row(work / "standard_ei16_out.csv")
        ei10_delta = _compare("EI10", ei10, EI10_ORACLE)
        ei16_delta = _compare("EI16", ei16, EI16_ORACLE)

    evidence = {
        "claim": "standard-MOOSE FVCoupledForce is numerically equivalent to accepted custom E8 energy projection for bounded EI10/EI16 discriminators",
        "standard_moose_object": "FVCoupledForce",
        "custom_energy_projector_instantiated": False,
        "coefficient_convention": "coef = -Delta_epsilon_eV*N_A/(n_ref*epsilon_ref_eV); FVCoupledForce residual = -coef*v",
        "ei10": {"coef": EI10_COEF, "final": ei10, "delta_from_accepted_oracle": ei10_delta},
        "ei16": {"coef": EI16_COEF, "final": ei16, "delta_from_accepted_oracle": ei16_delta},
        "runtime_executable": str(executable),
        "runtime_executable_sha256": _sha256_file(executable),
    }
    if repository_sha:
        evidence["repository_sha"] = repository_sha
    if build_base_ref:
        evidence["build_base_ref"] = build_base_ref
    if evidence_out:
        Path(evidence_out).write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")

    print(
        "STANDARD_MOOSE_ENERGY_AB_VECTOR "
        f"EI10_neps={ei10['n_epsilon_hat_avg']:.12g} "
        f"EI16_neps={ei16['n_epsilon_hat_avg']:.12g}"
    )
    print("STANDARD_MOOSE_ENERGY_PROJECTION_AB_PASS")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--executable")
    parser.add_argument("--evidence-out")
    parser.add_argument("--repository-sha")
    parser.add_argument("--build-base-ref")
    args = parser.parse_args()

    if args.self_test:
        _validate_input_contract()
        print("STANDARD_MOOSE_ENERGY_PROJECTION_SELFTEST_PASS")
        return
    if not args.executable:
        raise SystemExit("--executable or --self-test is required")
    run(args.executable, args.evidence_out, args.repository_sha, args.build_base_ref)


if __name__ == "__main__":
    main()
