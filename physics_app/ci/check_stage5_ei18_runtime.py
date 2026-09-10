#!/usr/bin/env python3
"""Governed Stage-5 S5-A discriminator for EI18 O -> Os excitation."""

import argparse
import csv
import hashlib
import json
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "docs/development/2026-09-10_issue176_stage5_reaction_ownership_contract.json"
TABLE = ROOT / "physics_app/data/electron_impact/o_excitation_1d.txt"

N_A = 6.02214076e23
N_REF = 1.0e16
EPSILON_REF_EV = 5.73276
M_O = 0.016
RHO = 3.1998e-5
W_OS0 = 1.0e-3
DT = 1.0e-8
DELTA_E_EV = 1.968
LOOKUP_MIN_EV = 1.40991
LOOKUP_MAX_EV = 22.1378
ANCHORS = {1.40991: 1.54e8, 5.73276: 1.57e9, 22.1378: 1.86e9}
EXPECTED_GIT_BLOB = "c874552f6fa43aaf13456d3ee6804065652b4e65"
PROGRESS = "R_excitation_O_1p968"
ENERGY_COEF = -(DELTA_E_EV * N_A / (N_REF * EPSILON_REF_EV))


def _close(a, b, *, rel=8e-6, abs_=1e-12, label="value"):
    if not math.isclose(a, b, rel_tol=rel, abs_tol=abs_):
        raise AssertionError(f"{label}: {a:.17g} != {b:.17g}")


def _num(row, key):
    value = float(row[key])
    if not math.isfinite(value):
        raise AssertionError(f"non-finite {key}")
    return value


def _git_blob_sha(data):
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def _read_table_bytes(data):
    rows = []
    for line_no, raw in enumerate(data.decode().splitlines(), 1):
        if not raw.strip():
            continue
        fields = raw.split()
        if len(fields) != 2:
            raise AssertionError(f"table line {line_no}: expected two columns")
        x, y = map(float, fields)
        if not (math.isfinite(x) and math.isfinite(y)) or y < 0:
            raise AssertionError(f"table line {line_no}: invalid value")
        rows.append((x, y))
    if len(rows) != 100:
        raise AssertionError(f"EI18 table expected 100 rows, got {len(rows)}")
    if any(b[0] <= a[0] for a, b in zip(rows, rows[1:])):
        raise AssertionError("EI18 mean-energy grid is not strictly increasing")
    if rows[0][0] != LOOKUP_MIN_EV or rows[-1][0] != LOOKUP_MAX_EV:
        raise AssertionError("EI18 strict lookup domain changed")
    values = dict(rows)
    for x, expected in ANCHORS.items():
        if values.get(x) != expected:
            raise AssertionError(f"EI18 frozen anchor mismatch at {x} eV")
    return rows


def _interp_strict(table, mean_energy):
    if mean_energy < table[0][0] or mean_energy > table[-1][0]:
        raise AssertionError(f"mean energy outside strict lookup range: {mean_energy}")
    if mean_energy == table[0][0]:
        return table[0][1]
    if mean_energy == table[-1][0]:
        return table[-1][1]
    for (x0, y0), (x1, y1) in zip(table, table[1:]):
        if x0 <= mean_energy <= x1:
            return y0 + (mean_energy - x0) * (y1 - y0) / (x1 - x0)
    raise AssertionError("strict interpolation bracket failure")


def _runtime_input(mean_energy=EPSILON_REF_EV):
    n_epsilon0 = mean_energy / EPSILON_REF_EV
    return f"""[Mesh]
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
    initial_condition = {n_epsilon0:.17g}
  []
  [w_Os]
    type = MooseVariableFVReal
    initial_condition = {W_OS0:.17g}
  []
[]

[FunctorMaterials]
  [constants]
    type = ADGenericFunctorMaterial
    prop_names = 'rho_const'
    prop_values = '{RHO:.17g}'
  []
  [o_constraint]
    type = ADParsedFunctorMaterial
    property_name = w_O_constraint
    functor_names = 'w_Os'
    functor_symbols = 'wos'
    expression = '1.0-wos'
  []
  [electron_number_density]
    type = ADParsedFunctorMaterial
    property_name = n_e_physical
    functor_names = 'n_e'
    functor_symbols = 'nehat'
    expression = '{N_REF:.17g}*nehat'
  []
  [o_molar_concentration]
    type = ADParsedFunctorMaterial
    property_name = c_O
    functor_names = 'rho_const w_O_constraint'
    functor_symbols = 'dens wo'
    expression = 'dens*wo/{M_O:.17g}'
  []
  [mean_energy_bridge]
    type = PhysicsElectronMeanEnergyMaterial
    electron_energy_density = n_epsilon
    electron_density = n_e
    energy_reference_eV = {EPSILON_REF_EV:.17g}
  []
  [ei18_rate]
    type = PhysicsElectronImpactRateMaterial
    rate_table_file = o_excitation_1d.txt
    mean_energy = mean_en_solved
    electron_number_density = n_e_physical
    target_molar_concentration = c_O
    reaction_progress = {PROGRESS}
  []
  [o_mass_source]
    type = ADParsedFunctorMaterial
    property_name = O_ei18_mass_source
    functor_names = '{PROGRESS}'
    functor_symbols = 'rprog'
    expression = '-{M_O:.17g}*rprog'
  []
  [os_mass_source]
    type = ADParsedFunctorMaterial
    property_name = Os_ei18_mass_source
    functor_names = '{PROGRESS}'
    functor_symbols = 'rprog'
    expression = '{M_O:.17g}*rprog'
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
  [ei18_energy_loss]
    type = FVCoupledForce
    variable = n_epsilon
    v = {PROGRESS}
    coef = {ENERGY_COEF:.17g}
  []
  [w_Os_time]
    type = PhysicsFVMassFractionTimeDerivative
    variable = w_Os
    rho = rho_const
  []
  [w_Os_source]
    type = PhysicsFVSpeciesReactionSource
    variable = w_Os
    source = Os_ei18_mass_source
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
  [w_Os_avg]
    type = ElementAverageFunctorPostprocessor
    functor = w_Os
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [w_O_avg]
    type = ElementAverageFunctorPostprocessor
    functor = w_O_constraint
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [mean_en_solved_avg]
    type = ElementAverageFunctorPostprocessor
    functor = mean_en_solved
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [R_avg]
    type = ElementAverageFunctorPostprocessor
    functor = {PROGRESS}
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [O_source_avg]
    type = ElementAverageFunctorPostprocessor
    functor = O_ei18_mass_source
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Os_source_avg]
    type = ElementAverageFunctorPostprocessor
    functor = Os_ei18_mass_source
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


def validate_runtime_rows(rows, table):
    if len(rows) < 2:
        raise AssertionError("EI18 case expected INITIAL + TIMESTEP_END rows")
    i, f = rows[0], rows[-1]
    ne_i, ne_f = _num(i, "n_e_hat_avg"), _num(f, "n_e_hat_avg")
    ep_i, ep_f = _num(i, "n_epsilon_hat_avg"), _num(f, "n_epsilon_hat_avg")
    ws_i, ws_f = _num(i, "w_Os_avg"), _num(f, "w_Os_avg")
    wo_i, wo_f = _num(i, "w_O_avg"), _num(f, "w_O_avg")
    me_i, me_f = _num(i, "mean_en_solved_avg"), _num(f, "mean_en_solved_avg")
    r_f = _num(f, "R_avg")
    so_f = _num(f, "O_source_avg")
    sos_f = _num(f, "Os_source_avg")

    if not (ne_i > 0 and ep_i > 0 and 0 <= ws_i < ws_f < 1 and wo_i > wo_f > 0 and 0 < ep_f < ep_i):
        raise AssertionError("EI18 state direction/positivity failure")
    _close(ne_f, ne_i, rel=0, abs_=1e-12, label="EI18 zero electron-particle source")
    _close(wo_i + ws_i, 1.0, rel=0, abs_=2e-12, label="initial atomic heavy sum")
    _close(wo_f + ws_f, 1.0, rel=0, abs_=2e-12, label="final atomic heavy sum")
    _close(me_i, EPSILON_REF_EV * ep_i / ne_i, label="initial solved mean energy")
    _close(me_f, EPSILON_REF_EV * ep_f / ne_f, label="final solved mean energy")

    if not (r_f > 0 and so_f < 0 < sos_f):
        raise AssertionError("EI18 progress/source signs")
    _close(-so_f / M_O, r_f, label="O source / shared EI18 progress")
    _close(sos_f / M_O, r_f, label="Os source / shared EI18 progress")
    _close(so_f + sos_f, 0.0, rel=0, abs_=1e-12, label="EI18 heavy mass source closure")

    expected_r = _interp_strict(table, me_f) * (N_REF * ne_f / N_A) * (RHO * wo_f / M_O)
    _close(r_f, expected_r, rel=8e-6, abs_=1e-14, label="EI18 strict lookup progress")
    _close(RHO * (ws_f - ws_i) / DT, sos_f, rel=8e-6, abs_=1e-12, label="Os BE source closure")
    _close(RHO * (wo_f - wo_i) / DT, so_f, rel=8e-6, abs_=1e-12, label="constrained O BE source closure")

    rhs = ENERGY_COEF * r_f
    _close((ep_f - ep_i) / DT, rhs, rel=8e-6, abs_=1e-7, label="EI18 energy BE closure")
    oxygen_i = RHO * (wo_i + ws_i) / M_O
    oxygen_f = RHO * (wo_f + ws_f) / M_O
    _close(oxygen_f, oxygen_i, rel=2e-12, abs_=1e-14, label="oxygen atom inventory")

    return {
        "initial": {
            "n_e_hat": ne_i,
            "n_epsilon_hat": ep_i,
            "w_O": wo_i,
            "w_Os": ws_i,
            "mean_en_solved_eV": me_i,
        },
        "final": {
            "n_e_hat": ne_f,
            "n_epsilon_hat": ep_f,
            "w_O": wo_f,
            "w_Os": ws_f,
            "mean_en_solved_eV": me_f,
            "R_excitation_O_1p968_mol_m3_s": r_f,
            "O_source_kg_m3_s": so_f,
            "Os_source_kg_m3_s": sos_f,
        },
        "closure": {
            "heavy_mass_source_sum_kg_m3_s": so_f + sos_f,
            "oxygen_atom_molar_inventory_initial": oxygen_i,
            "oxygen_atom_molar_inventory_final": oxygen_f,
            "electron_particle_delta_hat": ne_f - ne_i,
            "energy_loss_eV_per_event": DELTA_E_EV,
            "standard_moose_object": "FVCoupledForce",
            "energy_coef": ENERGY_COEF,
            "normalized_energy_rhs_per_s": rhs,
            "observed_dn_epsilon_hat_dt_per_s": (ep_f - ep_i) / DT,
        },
    }


def _fixed_point_rows(table):
    r = _interp_strict(table, EPSILON_REF_EV) * (N_REF / N_A) * (RHO * (1 - W_OS0) / M_O)
    for _ in range(500):
        ws = W_OS0 + DT * M_O * r / RHO
        ep = 1.0 + DT * ENERGY_COEF * r
        mean = EPSILON_REF_EV * ep
        new = _interp_strict(table, mean) * (N_REF / N_A) * (RHO * (1 - ws) / M_O)
        if math.isclose(new, r, rel_tol=1e-14, abs_tol=1e-18):
            r = new
            break
        r = new
    ws = W_OS0 + DT * M_O * r / RHO
    ep = 1.0 + DT * ENERGY_COEF * r
    mean = EPSILON_REF_EV * ep
    r0 = _interp_strict(table, EPSILON_REF_EV) * (N_REF / N_A) * (RHO * (1 - W_OS0) / M_O)
    rows = [
        {
            "n_e_hat_avg": 1.0,
            "n_epsilon_hat_avg": 1.0,
            "w_Os_avg": W_OS0,
            "w_O_avg": 1.0 - W_OS0,
            "mean_en_solved_avg": EPSILON_REF_EV,
            "R_avg": r0,
            "O_source_avg": -M_O * r0,
            "Os_source_avg": M_O * r0,
        },
        {
            "n_e_hat_avg": 1.0,
            "n_epsilon_hat_avg": ep,
            "w_Os_avg": ws,
            "w_O_avg": 1.0 - ws,
            "mean_en_solved_avg": mean,
            "R_avg": r,
            "O_source_avg": -M_O * r,
            "Os_source_avg": M_O * r,
        },
    ]
    return rows


def _expect_failure(fn, *args):
    try:
        fn(*args)
    except AssertionError:
        return
    raise AssertionError("negative mutation unexpectedly passed")


def checker_self_test():
    table = [(LOOKUP_MIN_EV, ANCHORS[LOOKUP_MIN_EV]), (EPSILON_REF_EV, ANCHORS[EPSILON_REF_EV]), (LOOKUP_MAX_EV, ANCHORS[LOOKUP_MAX_EV])]
    rows = _fixed_point_rows(table)
    validate_runtime_rows(rows, table)

    mutations = []
    bad = [dict(row) for row in rows]
    bad[-1]["n_e_hat_avg"] *= 1.001
    mutations.append(bad)
    bad = [dict(row) for row in rows]
    bad[-1]["n_epsilon_hat_avg"] = 1.0 + abs(bad[-1]["n_epsilon_hat_avg"] - 1.0)
    mutations.append(bad)
    bad = [dict(row) for row in rows]
    bad[-1]["Os_source_avg"] *= 1.01
    mutations.append(bad)
    bad = [dict(row) for row in rows]
    bad[-1]["R_avg"] *= 1.01
    mutations.append(bad)
    bad = [dict(row) for row in rows]
    bad[-1]["w_Os_avg"] = -1e-6
    mutations.append(bad)
    for bad in mutations:
        _expect_failure(validate_runtime_rows, bad, table)

    _expect_failure(_interp_strict, table, LOOKUP_MIN_EV - 0.1)
    _expect_failure(_interp_strict, table, LOOKUP_MAX_EV + 0.1)

    text = _runtime_input()
    required = (
        "type = PhysicsElectronImpactRateMaterial",
        f"reaction_progress = {PROGRESS}",
        "type = PhysicsFVSpeciesReactionSource",
        "source = Os_ei18_mass_source",
        "type = FVCoupledForce",
        f"v = {PROGRESS}",
        "O_ei18_mass_source",
        "Os_ei18_mass_source",
        "functor_symbols = 'rprog'",
    )
    for token in required:
        if token not in text:
            raise AssertionError(f"runtime input missing {token}")
    if text.count("type = PhysicsElectronImpactRateMaterial") != 1:
        raise AssertionError("EI18 must have exactly one kinetic progress owner")
    if "PhysicsFVElectronReactionSource" in text:
        raise AssertionError("EI18 must not change electron particle inventory")
    for forbidden in ("R_ion_O", "o_ionization.txt", "13.618", "PhysicsFVElectronReactionEnergySource"):
        if forbidden in text:
            raise AssertionError(f"later/deprecated Stage-5 surface activated: {forbidden}")
    for alias in ("wos", "nehat", "dens", "wo", "rprog"):
        if alias in {"x", "y", "z", "t", "pi", "e"}:
            raise AssertionError("reserved parser alias")
    print("STAGE5_EI18_RUNTIME_CHECKER_SELFTEST_PASS")


def static_gate():
    contract = json.loads(CONTRACT.read_text())
    if contract.get("status") != "CONTRACT_FROZEN" or contract.get("stage") != "STAGE_5_FULL_CHEMISTRY_REPRESENTATIVE_REAL_QVT":
        raise AssertionError("Stage-5 ownership contract is not frozen")
    reactions = {entry["id"]: entry for entry in contract["stage5_admitted_primary_channels"]}
    rxn = reactions["EI18_O_TO_OS"]
    if rxn["admission"] != "DATA_READY_FIRST_SLICE":
        raise AssertionError("EI18 is not frozen as first Stage-5 slice")
    if rxn["canonical_progress"] != PROGRESS or rxn["energy_loss_eV_per_event"] != DELTA_E_EV:
        raise AssertionError("EI18 progress/energy contract changed")
    if rxn["heavy_stoichiometry"] != {"O": -1, "Os": 1} or rxn["net_electron_particle_stoich"] != 0:
        raise AssertionError("EI18 stoichiometry changed")

    data = TABLE.read_bytes()
    if _git_blob_sha(data) != EXPECTED_GIT_BLOB:
        raise AssertionError(f"EI18 production table blob changed: {_git_blob_sha(data)}")
    _read_table_bytes(data)
    owner_source = (ROOT / "physics_app/src/materials/PhysicsElectronImpactRateMaterial.C").read_text()
    for token in (
        'addRequiredParam<std::string>("reaction_progress"',
        "return k_raw * (n_e / N_A) * c_target;",
        "strict Stage-4 policy forbids clamp/floor",
    ):
        if token not in owner_source:
            raise AssertionError(f"generic progress owner contract missing: {token}")
    checker_self_test()
    print("STAGE5_EI18_IMPLEMENTATION_P0_PASS")


def _preflight(input_path):
    subprocess.run([sys.executable, str(ROOT / "bin/physics.py"), "preflight", str(input_path)], cwd=ROOT, check=True)


def _execute_case(executable, work_root, case_name, mean_energy, *, expect_strict_failure=False):
    case_dir = work_root / case_name
    case_dir.mkdir()
    shutil.copy2(TABLE, case_dir / TABLE.name)
    input_path = case_dir / f"{case_name}.i"
    input_path.write_text(_runtime_input(mean_energy))
    _preflight(input_path)
    p2 = subprocess.run([str(executable), "--check-input", "-i", input_path.name], cwd=case_dir, text=True, capture_output=True)
    if expect_strict_failure:
        if p2.returncode != 0:
            output = p2.stdout + p2.stderr
        else:
            p3 = subprocess.run([str(executable), "-i", input_path.name], cwd=case_dir, text=True, capture_output=True)
            if p3.returncode == 0:
                raise AssertionError(f"{case_name}: out-of-range EI18 control unexpectedly ran")
            output = p3.stdout + p3.stderr
        if "outside lookup range" not in output or "strict Stage-4 policy forbids clamp/floor" not in output:
            raise AssertionError(f"{case_name}: strict lookup failure signature missing")
        return None
    if p2.returncode != 0:
        raise AssertionError(f"{case_name}: P2 failed\n{p2.stdout}\n{p2.stderr}")
    p3 = subprocess.run([str(executable), "-i", input_path.name], cwd=case_dir, text=True, capture_output=True)
    if p3.returncode != 0:
        raise AssertionError(f"{case_name}: P3 failed\n{p3.stdout}\n{p3.stderr}")
    csv_path = case_dir / f"{case_name}_out.csv"
    rows = list(csv.DictReader(csv_path.open(newline="")))
    return validate_runtime_rows(rows, _read_table_bytes(TABLE.read_bytes()))


def run_controlled_executable(executable, evidence_out=None, repository_sha=None, build_base_ref=None):
    static_gate()
    executable = Path(executable).resolve()
    if not executable.is_file():
        raise SystemExit(f"Physics executable does not exist: {executable}")
    with tempfile.TemporaryDirectory(prefix="stage5-ei18-") as tmp:
        work = Path(tmp)
        result = _execute_case(executable, work, "stage5_ei18_runtime", EPSILON_REF_EV)
        _execute_case(executable, work, "stage5_ei18_below_lookup", LOOKUP_MIN_EV - 0.01, expect_strict_failure=True)
        _execute_case(executable, work, "stage5_ei18_above_lookup", LOOKUP_MAX_EV + 0.01, expect_strict_failure=True)

    evidence = {
        "schema_version": 1,
        "stage": "STAGE_5",
        "slice": "S5-A_EI18",
        "decision": "LOCAL_RUNTIME_ACCURACY",
        "result": "PASS",
        "integrated_physics_accuracy": "NOT_ESTABLISHED",
        "repository_sha": repository_sha,
        "build_base_ref": build_base_ref,
        "executable": str(executable),
        "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        "production_table": {
            "path": str(TABLE.relative_to(ROOT)),
            "git_blob_sha": _git_blob_sha(TABLE.read_bytes()),
            "sha256": hashlib.sha256(TABLE.read_bytes()).hexdigest(),
            "rows": 100,
            "lookup_domain_eV": [LOOKUP_MIN_EV, LOOKUP_MAX_EV],
            "anchors_m3_per_mol_s": {str(k): v for k, v in ANCHORS.items()},
        },
        "runtime": result,
        "strict_bounds_negative_controls": "PASS",
        "upstream_regressions": "enforced by governed science workflow",
    }
    if evidence_out:
        Path(evidence_out).write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(
        "STAGE5_EI18_LOCAL_RUNTIME_PASS "
        f"R={result['final']['R_excitation_O_1p968_mol_m3_s']:.12g} "
        f"mean_en={result['final']['mean_en_solved_eV']:.12g}"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--static", action="store_true")
    parser.add_argument("--executable")
    parser.add_argument("--evidence-out")
    parser.add_argument("--repository-sha")
    parser.add_argument("--build-base-ref")
    args = parser.parse_args()

    if args.self_test:
        checker_self_test()
        return
    if args.static:
        static_gate()
        return
    if args.executable:
        run_controlled_executable(args.executable, args.evidence_out, args.repository_sha, args.build_base_ref)
        return
    parser.error("choose --self-test, --static, or --executable")


if __name__ == "__main__":
    main()
