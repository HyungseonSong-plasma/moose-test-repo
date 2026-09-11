#!/usr/bin/env python3
"""Stage-5 S5-E bounded validation for H05 O- + O -> O2 + e-."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "docs/development/2026-09-11_issue191_stage5_h05_contract.json"
DATABASE = ROOT / "physics_app/data/heavy_reactions/stage5_s5d_oxygen_heavy.txt"

NA = 6.02214076e23
A = 3.0e-16
RHO = 3.1998e-5
M_O = 0.016
M_O2 = 0.032
NREF = 1.0e16
EREF = 5.73276
DT = 1.0e-7
W_O0 = 0.10
W_OM0 = 0.01
PROGRESS = "reaction_rate_H05_Om_O_to_O2_electron"


def close(a, b, rel=2.0e-5, abs_=1.0e-12, label="value"):
    if not math.isclose(a, b, rel_tol=rel, abs_tol=abs_):
        raise AssertionError(f"{label}: {a:.17g} != {b:.17g}")


def num(row, key):
    value = float(row[key])
    if not math.isfinite(value):
        raise AssertionError(f"non-finite {key}")
    return value


def molar_rate(w_o, w_om):
    c_o = RHO * w_o / M_O
    c_om = RHO * w_om / M_O
    return A * NA * c_o * c_om


def runtime_input():
    return f"""[Mesh]
  [mesh]
    type = GeneratedMeshGenerator
    dim = 1
    nx = 1
  []
[]
[Variables]
  [n_e]
    type = MooseVariableFVReal
    initial_condition = 1
  []
  [n_epsilon]
    type = MooseVariableFVReal
    initial_condition = 1
  []
  [w_O]
    type = MooseVariableFVReal
    initial_condition = {W_O0:.17g}
  []
  [w_Om]
    type = MooseVariableFVReal
    initial_condition = {W_OM0:.17g}
  []
[]
[FunctorMaterials]
  [state]
    type = ADGenericFunctorMaterial
    prop_names = 'rho_const T_g'
    prop_values = '{RHO:.17g} 300'
  []
  [O2_constraint]
    type = ADParsedFunctorMaterial
    property_name = w_O2_constraint
    functor_names = 'w_O w_Om'
    functor_symbols = 'wo wom'
    expression = '1-wo-wom'
  []
  [heavy_rates]
    type = PhysicsReactionRateMaterial
    chemistry_file = '{DATABASE.resolve()}'
    density = rho_const
    temperature = T_g
    species = 'O2 O Om'
    mass_fractions = 'w_O2_constraint w_O w_Om'
    active_reactions = 'H05_Om_O_to_O2_electron'
  []
  [O_source]
    type = ADParsedFunctorMaterial
    property_name = S_O_h05
    functor_names = '{PROGRESS}'
    functor_symbols = 'rprog'
    expression = '-{M_O:.17g}*rprog'
  []
  [Om_source]
    type = ADParsedFunctorMaterial
    property_name = S_Om_h05
    functor_names = '{PROGRESS}'
    functor_symbols = 'rprog'
    expression = '-{M_O:.17g}*rprog'
  []
  [O2_source_expected]
    type = ADParsedFunctorMaterial
    property_name = S_O2_h05_expected
    functor_names = '{PROGRESS}'
    functor_symbols = 'rprog'
    expression = '{M_O2:.17g}*rprog'
  []
  [electron_number_source]
    type = ADParsedFunctorMaterial
    property_name = S_e_h05
    functor_names = '{PROGRESS}'
    functor_symbols = 'rprog'
    expression = '{NA:.17g}*rprog'
  []
  [mean_energy]
    type = PhysicsElectronMeanEnergyMaterial
    electron_energy_density = n_epsilon
    electron_density = n_e
    energy_reference_eV = {EREF:.17g}
  []
[]
[FVKernels]
  [n_e_time]
    type = FVTimeKernel
    variable = n_e
  []
  [n_e_source]
    type = PhysicsFVElectronReactionSource
    variable = n_e
    number_source = S_e_h05
    n_ref = {NREF:.17g}
  []
  [n_epsilon_time]
    type = FVTimeKernel
    variable = n_epsilon
  []
  [w_O_time]
    type = PhysicsFVMassFractionTimeDerivative
    variable = w_O
    rho = rho_const
  []
  [w_O_source]
    type = PhysicsFVSpeciesReactionSource
    variable = w_O
    source = S_O_h05
  []
  [w_Om_time]
    type = PhysicsFVMassFractionTimeDerivative
    variable = w_Om
    rho = rho_const
  []
  [w_Om_source]
    type = PhysicsFVSpeciesReactionSource
    variable = w_Om
    source = S_Om_h05
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
  [mean_energy_avg]
    type = ElementAverageFunctorPostprocessor
    functor = mean_en_solved
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [w_O_avg]
    type = ElementAverageFunctorPostprocessor
    functor = w_O
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [w_Om_avg]
    type = ElementAverageFunctorPostprocessor
    functor = w_Om
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [w_O2_avg]
    type = ElementAverageFunctorPostprocessor
    functor = w_O2_constraint
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [R_avg]
    type = ElementAverageFunctorPostprocessor
    functor = {PROGRESS}
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [O_source_avg]
    type = ElementAverageFunctorPostprocessor
    functor = S_O_h05
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Om_source_avg]
    type = ElementAverageFunctorPostprocessor
    functor = S_Om_h05
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [O2_source_avg]
    type = ElementAverageFunctorPostprocessor
    functor = S_O2_h05_expected
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [electron_source_avg]
    type = ElementAverageFunctorPostprocessor
    functor = S_e_h05
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]
[Executioner]
  type = Transient
  dt = {DT:.17g}
  end_time = {DT:.17g}
  solve_type = NEWTON
[]
[Outputs]
  csv = true
  exodus = false
[]
"""


def validate(rows):
    if len(rows) < 2:
        raise AssertionError("expected initial and final rows")
    i, f = rows[0], rows[-1]
    ni, nf = num(i, "n_e_hat_avg"), num(f, "n_e_hat_avg")
    ei, ef = num(i, "n_epsilon_hat_avg"), num(f, "n_epsilon_hat_avg")
    mi, mf = num(i, "mean_energy_avg"), num(f, "mean_energy_avg")
    oi, of = num(i, "w_O_avg"), num(f, "w_O_avg")
    omi, omf = num(i, "w_Om_avg"), num(f, "w_Om_avg")
    o2i, o2f = num(i, "w_O2_avg"), num(f, "w_O2_avg")
    r = num(f, "R_avg")
    so, som = num(f, "O_source_avg"), num(f, "Om_source_avg")
    so2, se = num(f, "O2_source_avg"), num(f, "electron_source_avg")

    close(oi, W_O0, rel=0.0, abs_=2e-12, label="initial O")
    close(omi, W_OM0, rel=0.0, abs_=2e-12, label="initial Om")
    close(o2i, 1.0 - W_O0 - W_OM0, rel=0.0, abs_=2e-12, label="initial O2")
    if not (0.0 < of < oi and 0.0 < omf < omi and o2i < o2f < 1.0):
        raise AssertionError("H05 heavy-species direction/positivity")
    if not nf > ni > 0.0:
        raise AssertionError("H05 electron production")
    close(ef, ei, rel=0.0, abs_=2e-10, label="zero explicit H05 energy source")
    close(mi, EREF * ei / ni, label="initial mean energy")
    close(mf, EREF * ef / nf, label="final mean energy")
    if not 0.0 < mf < mi:
        raise AssertionError("H05 zero-energy-source convention should dilute mean energy")

    expected_r = molar_rate(of, omf)
    close(r, expected_r, label="canonical H05 progress")
    if not (r > 0.0 and so < 0.0 and som < 0.0 and so2 > 0.0 and se > 0.0):
        raise AssertionError("H05 source signs")
    close(-so / M_O, r, label="O/shared progress")
    close(-som / M_O, r, label="Om/shared progress")
    close(so2 / M_O2, r, label="O2/shared progress")
    close(se / NA, r, label="electron/shared progress")
    close(so + som + so2, 0.0, rel=0.0, abs_=2e-12, label="heavy mass source closure")

    close(RHO * (of - oi) / DT, so, rel=3e-5, abs_=5e-10, label="O BE closure")
    close(RHO * (omf - omi) / DT, som, rel=3e-5, abs_=5e-10, label="Om BE closure")
    close(RHO * (o2f - o2i) / DT, so2, rel=3e-5, abs_=5e-10, label="O2 constrained closure")
    close(NREF * (nf - ni) / DT, se, rel=3e-5, abs_=2.0, label="electron BE closure")

    oxy_i = 2.0 * RHO * o2i / M_O2 + RHO * oi / M_O + RHO * omi / M_O
    oxy_f = 2.0 * RHO * o2f / M_O2 + RHO * of / M_O + RHO * omf / M_O
    close(oxy_f, oxy_i, rel=0.0, abs_=5e-10, label="oxygen nuclei closure")

    charge_i = -NA * RHO * omi / M_O - NREF * ni
    charge_f = -NA * RHO * omf / M_O - NREF * nf
    close(charge_f, charge_i, rel=2e-12, abs_=2.0, label="electron-inclusive charge closure")

    return {
        "initial": {"n_e_hat": ni, "n_epsilon_hat": ei, "mean_energy_eV": mi, "w_O": oi, "w_Om": omi, "w_O2": o2i},
        "final": {"n_e_hat": nf, "n_epsilon_hat": ef, "mean_energy_eV": mf, "w_O": of, "w_Om": omf, "w_O2": o2f,
                  "R_H05_mol_m3_s": r, "electron_source_m3_s": se},
        "closure": {"heavy_mass_source_sum_kg_m3_s": so + som + so2,
                    "oxygen_inventory_initial_mol_O_m3": oxy_i, "oxygen_inventory_final_mol_O_m3": oxy_f,
                    "electron_inclusive_charge_initial_particle_m3": charge_i,
                    "electron_inclusive_charge_final_particle_m3": charge_f,
                    "explicit_H05_energy_source": 0.0}
    }


def synthetic_rows():
    r = molar_rate(W_O0, W_OM0)
    for _ in range(500):
        of = W_O0 - DT * M_O * r / RHO
        omf = W_OM0 - DT * M_O * r / RHO
        new = molar_rate(of, omf)
        if math.isclose(new, r, rel_tol=1e-14, abs_tol=1e-18):
            r = new
            break
        r = new
    of = W_O0 - DT * M_O * r / RHO
    omf = W_OM0 - DT * M_O * r / RHO
    o2i = 1.0 - W_O0 - W_OM0
    o2f = 1.0 - of - omf
    nf = 1.0 + DT * NA * r / NREF
    ef = 1.0
    return [
        {"n_e_hat_avg": 1.0, "n_epsilon_hat_avg": 1.0, "mean_energy_avg": EREF,
         "w_O_avg": W_O0, "w_Om_avg": W_OM0, "w_O2_avg": o2i, "R_avg": molar_rate(W_O0, W_OM0),
         "O_source_avg": -M_O*molar_rate(W_O0, W_OM0), "Om_source_avg": -M_O*molar_rate(W_O0, W_OM0),
         "O2_source_avg": M_O2*molar_rate(W_O0, W_OM0), "electron_source_avg": NA*molar_rate(W_O0, W_OM0)},
        {"n_e_hat_avg": nf, "n_epsilon_hat_avg": ef, "mean_energy_avg": EREF * ef / nf,
         "w_O_avg": of, "w_Om_avg": omf, "w_O2_avg": o2f, "R_avg": r,
         "O_source_avg": -M_O*r, "Om_source_avg": -M_O*r, "O2_source_avg": M_O2*r,
         "electron_source_avg": NA*r},
    ]


def expect_fail(rows):
    try:
        validate(rows)
    except AssertionError:
        return
    raise AssertionError("negative mutation unexpectedly passed")


def self_test():
    rows = synthetic_rows()
    validate(rows)
    for key, mutate in [
        ("R_avg", lambda x: x * 0.5),
        ("electron_source_avg", lambda x: x * 2.0),
        ("O_source_avg", lambda x: -x),
        ("n_epsilon_hat_avg", lambda x: x * 0.99),
        ("n_e_hat_avg", lambda x: 1.0),
    ]:
        bad = [dict(r) for r in rows]
        bad[-1][key] = mutate(bad[-1][key])
        expect_fail(bad)

    text = runtime_input()
    required = (
        "type = PhysicsReactionRateMaterial",
        "active_reactions = 'H05_Om_O_to_O2_electron'",
        f"functor_names = '{PROGRESS}'",
        "type = PhysicsFVElectronReactionSource",
        "number_source = S_e_h05",
        "type = PhysicsFVSpeciesReactionSource",
        "source = S_O_h05",
        "source = S_Om_h05",
        "type = PhysicsElectronMeanEnergyMaterial",
    )
    for token in required:
        if token not in text:
            raise AssertionError(f"runtime input missing {token}")
    if text.count("type = PhysicsReactionRateMaterial") != 1:
        raise AssertionError("H05 must have exactly one canonical progress owner")
    for forbidden in ("PhysicsFVElectronReactionEnergySource", "FVCoupledForce", "S_epsilon_h05"):
        if forbidden in text:
            raise AssertionError(f"H05 zero-explicit-energy convention violated by {forbidden}")
    print("STAGE5_H05_RUNTIME_CHECKER_SELFTEST_PASS")


def static_gate():
    contract = json.loads(CONTRACT.read_text())
    if contract.get("status") != "MODEL_DECISION_FROZEN":
        raise AssertionError("H05 model decision is not frozen")
    if contract["kinetics"]["A_particle_m3_s"] != A or contract["kinetics"]["temperature_exponent"] != 0.0:
        raise AssertionError("H05 frozen kinetic contract changed")
    if contract["electron_energy"]["explicit_source"] != 0.0:
        raise AssertionError("H05 explicit energy-source convention changed")
    db = DATABASE.read_text()
    required = (
        "reaction H05_Om_O_to_O2_electron volume power_law",
        "reactant Om 1",
        "reactant O 1",
        "product O2 1",
        "A 3e-16",
        "basis particle",
        "exponent 0",
    )
    for token in required:
        if token not in db:
            raise AssertionError(f"H05 database contract missing {token}")
    if "product e " in db or "species e " in db:
        raise AssertionError("heavy reaction database must not own the electron species")
    owner = (ROOT / "physics_app/src/materials/PhysicsReactionRateMaterial.C").read_text()
    if '"reaction_rate_" + reaction.name' not in owner or "addFunctorProperty<ADReal>" not in owner:
        raise AssertionError("canonical reaction-progress owner contract changed")
    eproj = (ROOT / "physics_app/src/fvkernels/PhysicsFVElectronReactionSource.C").read_text()
    if "return -physical_number_source / _n_ref;" not in eproj:
        raise AssertionError("normalized electron projection semantics changed")
    self_test()
    print("STAGE5_H05_IMPLEMENTATION_P0_PASS")


def preflight(path):
    subprocess.run([sys.executable, str(ROOT / "bin/physics.py"), "preflight", str(path)], cwd=ROOT, check=True)


def run(executable, evidence_out=None, repository_sha=None, build_base_ref=None):
    static_gate()
    exe = Path(executable).resolve()
    if not exe.is_file():
        raise SystemExit(f"Physics executable does not exist: {exe}")
    with tempfile.TemporaryDirectory(prefix="stage5-h05-") as tmp:
        work = Path(tmp)
        inp = work / "stage5_h05_runtime.i"
        inp.write_text(runtime_input())
        preflight(inp)
        p2 = subprocess.run([str(exe), "--check-input", "-i", inp.name], cwd=work, text=True, capture_output=True)
        if p2.returncode:
            raise AssertionError(f"H05 P2 failed\n{p2.stdout}\n{p2.stderr}")
        p3 = subprocess.run([str(exe), "-i", inp.name], cwd=work, text=True, capture_output=True)
        if p3.returncode:
            raise AssertionError(f"H05 P3 failed\n{p3.stdout}\n{p3.stderr}")
        rows = list(csv.DictReader((work / "stage5_h05_runtime_out.csv").open(newline="")))
        result = validate(rows)

    evidence = {
        "schema_version": 1,
        "stage": "STAGE_5",
        "slice": "S5-E_H05",
        "decision": "LOCAL_RUNTIME_ACCURACY",
        "result": "PASS",
        "integrated_physics_accuracy": "NOT_ESTABLISHED",
        "repository_sha": repository_sha,
        "build_base_ref": build_base_ref,
        "executable": str(exe),
        "executable_sha256": hashlib.sha256(exe.read_bytes()).hexdigest(),
        "model_convention": "electron particle production with zero explicit H05 electron-energy source",
        "runtime": result,
        "negative_controls": "PASS",
        "upstream_regressions": "enforced by governed science workflow",
    }
    if evidence_out:
        Path(evidence_out).write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(f"STAGE5_H05_LOCAL_RUNTIME_PASS R={result['final']['R_H05_mol_m3_s']:.12g} "
          f"n_e_hat={result['final']['n_e_hat']:.12g} mean_en={result['final']['mean_energy_eV']:.12g}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--static", action="store_true")
    p.add_argument("--executable")
    p.add_argument("--evidence-out")
    p.add_argument("--repository-sha")
    p.add_argument("--build-base-ref")
    a = p.parse_args()
    if a.self_test:
        self_test()
    elif a.static:
        static_gate()
    elif a.executable:
        run(a.executable, a.evidence_out, a.repository_sha, a.build_base_ref)
    else:
        p.error("choose --self-test, --static, or --executable")


if __name__ == "__main__":
    main()
