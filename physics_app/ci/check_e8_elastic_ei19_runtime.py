#!/usr/bin/env python3
"""Governed Stage-4 local runtime discriminators for EI02, EI17 and EI19."""

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
DATA_DIR = ROOT / "physics_app/data/electron_impact"

N_A = 6.02214076e23
ELECTRON_MASS_KG = 9.1093837139e-31
M_O2 = 31.998e-3
M_O = 15.999e-3
K_B_OVER_E_EV_PER_K = 8.617333262145e-5
N_REF = 1.0e16
EPSILON_REF_EV = 5.73276
C_TARGET = 0.1
DT = 1.0e-8
EI19_LOSS_EV = 4.192
LOOKUP_MIN_EV = 1.40991
LOOKUP_MAX_EV = 22.1378
EI19_ENERGY_COEF = -(EI19_LOSS_EV * N_A / (N_REF * EPSILON_REF_EV))

ELASTIC = {
    "O2": {
        "table": "o2_elastic.txt",
        "progress": "R_elastic_O2",
        "molar_mass": M_O2,
        "anchor_k": 5.53e10,
    },
    "O": {
        "table": "o_elastic.txt",
        "progress": "R_elastic_O",
        "molar_mass": M_O,
        "anchor_k": 5.89e10,
    },
}
EI19 = {
    "table": "o_excitation_1s.txt",
    "progress": "R_excitation_O_4p192",
    "anchor_k": 1.09e8,
}
REGIMES = (
    ("HOT_ELECTRON", 600.0, "sink"),
    ("THERMAL_EQUALITY", 44350.611537665, "zero"),
    ("REVERSED_ORDERING", 60000.0, "source"),
)
TABLE_BLOBS = {
    "o2_elastic.txt": "3f4b19e8f04184e38fa92b08b502a37ff3755ccb",
    "o_elastic.txt": "de9d718cf197d129db5d02fc3141c92969eca860",
    "o_excitation_1s.txt": "5ab8f6ba4c26c981c13d006364217fbadd07f603",
}


def _close(a, b, *, rel=7e-6, abs_=1e-10, label="value"):
    if not math.isclose(a, b, rel_tol=rel, abs_tol=abs_):
        raise AssertionError(f"{label}: {a:.17g} != {b:.17g}")


def _num(row, key):
    value = float(row[key])
    if not math.isfinite(value):
        raise AssertionError(f"non-finite {key}")
    return value


def _read_table(path):
    rows = []
    for raw in Path(path).read_text().splitlines():
        if raw.strip():
            x, y = map(float, raw.split())
            rows.append((x, y))
    if len(rows) != 100:
        raise AssertionError(f"{path}: expected 100 source rows")
    if any(b[0] <= a[0] for a, b in zip(rows, rows[1:])):
        raise AssertionError(f"{path}: non-increasing mean-energy grid")
    return rows


def _interp_strict(table, mean_energy):
    if not LOOKUP_MIN_EV <= mean_energy <= LOOKUP_MAX_EV:
        raise AssertionError(f"mean energy outside strict lookup range: {mean_energy}")
    if mean_energy == table[0][0]:
        return table[0][1]
    if mean_energy == table[-1][0]:
        return table[-1][1]
    for (x0, y0), (x1, y1) in zip(table, table[1:]):
        if x0 <= mean_energy <= x1:
            return y0 + (mean_energy - x0) * (y1 - y0) / (x1 - x0)
    raise AssertionError("strict interpolation bracket failure")


def _elastic_expected(spec, tgas):
    k_raw = spec["anchor_k"]
    rate = k_raw * (N_REF / N_A) * C_TARGET
    particle_mass = spec["molar_mass"] / N_A
    delta_e = (3.0 * ELECTRON_MASS_KG / particle_mass) * (
        (2.0 / 3.0) * EPSILON_REF_EV - K_B_OVER_E_EV_PER_K * tgas
    )
    source_hat = -delta_e * N_A * rate / (N_REF * EPSILON_REF_EV)
    return rate, delta_e, source_hat


def _ei19_expected():
    rate = EI19["anchor_k"] * (N_REF / N_A) * C_TARGET
    rhs = EI19_ENERGY_COEF * rate
    return rate, rhs


def _elastic_input(spec, tgas, mean_energy=EPSILON_REF_EV):
    particle_mass = spec["molar_mass"] / N_A
    normalized_factor = (
        (3.0 * ELECTRON_MASS_KG / particle_mass) * N_A / (N_REF * EPSILON_REF_EV)
    )
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
  [n_epsilon]
    type = MooseVariableFVReal
    initial_condition = 1.0
  []
[]

[FunctorMaterials]
  [controlled_state]
    type = ADGenericFunctorMaterial
    prop_names = 'mean_en_solved n_e_physical c_target T_gas'
    prop_values = '{mean_energy:.17g} {N_REF:.17g} {C_TARGET:.17g} {tgas:.17g}'
  []
  [reaction_rate]
    type = PhysicsElectronImpactRateMaterial
    rate_table_file = {spec["table"]}
    mean_energy = mean_en_solved
    electron_number_density = n_e_physical
    target_molar_concentration = c_target
    reaction_progress = {spec["progress"]}
  []
  [elastic_energy_source]
    type = ADParsedFunctorMaterial
    property_name = S_elastic_hat
    functor_names = 'mean_en_solved T_gas {spec["progress"]}'
    functor_symbols = 'meanE tgas rprog'
    expression = '-{normalized_factor:.17g}*(0.66666666666666663*meanE-{K_B_OVER_E_EV_PER_K:.17g}*tgas)*rprog'
  []
[]

[FVKernels]
  [energy_time]
    type = FVTimeKernel
    variable = n_epsilon
  []
  [elastic_energy_transfer]
    type = FVCoupledForce
    variable = n_epsilon
    v = S_elastic_hat
    coef = 1
  []
[]

[Postprocessors]
  [n_epsilon_hat_avg]
    type = ElementAverageFunctorPostprocessor
    functor = n_epsilon
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [mean_en_avg]
    type = ElementAverageFunctorPostprocessor
    functor = mean_en_solved
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [T_gas_avg]
    type = ElementAverageFunctorPostprocessor
    functor = T_gas
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [R_avg]
    type = ElementAverageFunctorPostprocessor
    functor = {spec["progress"]}
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [S_hat_avg]
    type = ElementAverageFunctorPostprocessor
    functor = S_elastic_hat
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


def _ei19_input(mean_energy=EPSILON_REF_EV):
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
  [n_epsilon]
    type = MooseVariableFVReal
    initial_condition = 1.0
  []
[]

[FunctorMaterials]
  [controlled_state]
    type = ADGenericFunctorMaterial
    prop_names = 'mean_en_solved n_e_physical c_target'
    prop_values = '{mean_energy:.17g} {N_REF:.17g} {C_TARGET:.17g}'
  []
  [reaction_rate]
    type = PhysicsElectronImpactRateMaterial
    rate_table_file = {EI19["table"]}
    mean_energy = mean_en_solved
    electron_number_density = n_e_physical
    target_molar_concentration = c_target
    reaction_progress = {EI19["progress"]}
  []
[]

[FVKernels]
  [energy_time]
    type = FVTimeKernel
    variable = n_epsilon
  []
  [ei19_energy_loss]
    type = FVCoupledForce
    variable = n_epsilon
    v = {EI19["progress"]}
    coef = {EI19_ENERGY_COEF:.17g}
  []
[]

[Postprocessors]
  [n_epsilon_hat_avg]
    type = ElementAverageFunctorPostprocessor
    functor = n_epsilon
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [mean_en_avg]
    type = ElementAverageFunctorPostprocessor
    functor = mean_en_solved
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [R_avg]
    type = ElementAverageFunctorPostprocessor
    functor = {EI19["progress"]}
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


def validate_elastic_rows(rows, species, regime_id, tgas):
    if len(rows) < 2:
        raise AssertionError("elastic case expected initial and final rows")
    spec = ELASTIC[species]
    initial, final = rows[0], rows[-1]
    ep_i = _num(initial, "n_epsilon_hat_avg")
    ep_f = _num(final, "n_epsilon_hat_avg")
    mean_i = _num(initial, "mean_en_avg")
    mean_f = _num(final, "mean_en_avg")
    t_i = _num(initial, "T_gas_avg")
    t_f = _num(final, "T_gas_avg")
    r_i = _num(initial, "R_avg")
    r_f = _num(final, "R_avg")
    s_f = _num(final, "S_hat_avg")

    expected_r, delta_e, expected_s = _elastic_expected(spec, tgas)
    _close(mean_i, EPSILON_REF_EV, rel=0, abs_=1e-12, label=f"{species}/{regime_id} mean initial")
    _close(mean_f, EPSILON_REF_EV, rel=0, abs_=1e-12, label=f"{species}/{regime_id} mean final")
    _close(t_i, tgas, rel=0, abs_=1e-9, label=f"{species}/{regime_id} Tgas initial")
    _close(t_f, tgas, rel=0, abs_=1e-9, label=f"{species}/{regime_id} Tgas final")
    _close(r_i, expected_r, rel=5e-7, abs_=1e-12, label=f"{species}/{regime_id} rate initial")
    _close(r_f, expected_r, rel=5e-7, abs_=1e-12, label=f"{species}/{regime_id} rate final")
    _close(r_f, r_i, rel=0, abs_=1e-10, label=f"{species}/{regime_id} rate reuse")
    _close(s_f, expected_s, rel=7e-6, abs_=1e-7, label=f"{species}/{regime_id} source")
    _close((ep_f - ep_i) / DT, expected_s, rel=7e-6, abs_=1e-6, label=f"{species}/{regime_id} BE closure")

    if regime_id == "HOT_ELECTRON":
        if not (delta_e > 0 and expected_s < 0 and ep_f < ep_i):
            raise AssertionError(f"{species}: hot-electron sink direction failure")
    elif regime_id == "THERMAL_EQUALITY":
        if not (abs(delta_e) < 1e-15 and abs(expected_s) < 1e-6 and abs(ep_f - ep_i) < 1e-12):
            raise AssertionError(f"{species}: thermal-equality zero failure")
    elif regime_id == "REVERSED_ORDERING":
        if not (delta_e < 0 and expected_s > 0 and ep_f > ep_i):
            raise AssertionError(f"{species}: reversed-ordering source direction failure")
    else:
        raise AssertionError(f"unknown regime {regime_id}")

    return {
        "Tgas_K": tgas,
        "mean_en_solved_eV": mean_f,
        "R_mol_m3_s": r_f,
        "delta_epsilon_eV_per_event": delta_e,
        "normalized_source_per_s": expected_s,
        "observed_dn_epsilon_hat_dt_per_s": (ep_f - ep_i) / DT,
        "final_n_epsilon_hat": ep_f,
    }


def validate_elastic_identity(results):
    for species, by_regime in results.items():
        rates = [by_regime[name]["R_mol_m3_s"] for name, _, _ in REGIMES]
        if max(rates) - min(rates) > 1e-10:
            raise AssertionError(f"{species}: canonical elastic rate changed across Tgas-only regimes")


def validate_ei19_rows(rows):
    if len(rows) < 2:
        raise AssertionError("EI19 case expected initial and final rows")
    initial, final = rows[0], rows[-1]
    ep_i = _num(initial, "n_epsilon_hat_avg")
    ep_f = _num(final, "n_epsilon_hat_avg")
    mean_i = _num(initial, "mean_en_avg")
    mean_f = _num(final, "mean_en_avg")
    r_i = _num(initial, "R_avg")
    r_f = _num(final, "R_avg")
    expected_r, rhs = _ei19_expected()

    _close(mean_i, EPSILON_REF_EV, rel=0, abs_=1e-12, label="EI19 mean initial")
    _close(mean_f, EPSILON_REF_EV, rel=0, abs_=1e-12, label="EI19 mean final")
    _close(r_i, expected_r, rel=5e-7, abs_=1e-12, label="EI19 rate initial")
    _close(r_f, expected_r, rel=5e-7, abs_=1e-12, label="EI19 rate final")
    _close((ep_f - ep_i) / DT, rhs, rel=7e-6, abs_=1e-6, label="EI19 energy BE closure")
    if not (r_f > 0 and rhs < 0 and 0 < ep_f < ep_i):
        raise AssertionError("EI19 energy-only sink direction failure")

    return {
        "mean_en_solved_eV": mean_f,
        "lookup_k_m3_mol_s": EI19["anchor_k"],
        "R_mol_m3_s": r_f,
        "energy_loss_eV_per_event": EI19_LOSS_EV,
        "standard_moose_object": "FVCoupledForce",
        "coef": EI19_ENERGY_COEF,
        "normalized_rhs_per_s": rhs,
        "observed_dn_epsilon_hat_dt_per_s": (ep_f - ep_i) / DT,
        "final_n_epsilon_hat": ep_f,
        "particle_or_heavy_projection": "NONE",
    }


def _synthetic_elastic_rows(species, regime_id, tgas, *, rate_scale=1.0, source_scale=1.0):
    spec = ELASTIC[species]
    rate, _, source = _elastic_expected(spec, tgas)
    rate *= rate_scale
    source *= source_scale
    final_ep = 1.0 + DT * source
    base = {
        "mean_en_avg": EPSILON_REF_EV,
        "T_gas_avg": tgas,
        "R_avg": rate,
        "S_hat_avg": source,
    }
    initial = dict(base, n_epsilon_hat_avg=1.0)
    final = dict(base, n_epsilon_hat_avg=final_ep)
    return [initial, final]


def _synthetic_ei19_rows(*, rate_scale=1.0, rhs_scale=1.0):
    rate, rhs = _ei19_expected()
    rate *= rate_scale
    rhs *= rhs_scale
    base = {"mean_en_avg": EPSILON_REF_EV, "R_avg": rate}
    return [
        dict(base, n_epsilon_hat_avg=1.0),
        dict(base, n_epsilon_hat_avg=1.0 + DT * rhs),
    ]


def _expect_failure(fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except AssertionError:
        return
    raise AssertionError("negative mutation unexpectedly passed")


def runtime_checker_self_test():
    results = {}
    for species in ELASTIC:
        results[species] = {}
        for regime_id, tgas, _ in REGIMES:
            rows = _synthetic_elastic_rows(species, regime_id, tgas)
            results[species][regime_id] = validate_elastic_rows(rows, species, regime_id, tgas)
    validate_elastic_identity(results)

    _expect_failure(
        validate_elastic_rows,
        _synthetic_elastic_rows("O2", "HOT_ELECTRON", 600.0, source_scale=-1.0),
        "O2",
        "HOT_ELECTRON",
        600.0,
    )
    _expect_failure(
        validate_elastic_rows,
        _synthetic_elastic_rows("O2", "HOT_ELECTRON", 600.0, source_scale=2.0),
        "O2",
        "HOT_ELECTRON",
        600.0,
    )
    _expect_failure(
        validate_elastic_rows,
        _synthetic_elastic_rows("O", "REVERSED_ORDERING", 60000.0, rate_scale=1.1),
        "O",
        "REVERSED_ORDERING",
        60000.0,
    )
    bad_identity = {
        species: {regime: dict(vector) for regime, vector in by_regime.items()}
        for species, by_regime in results.items()
    }
    bad_identity["O2"]["REVERSED_ORDERING"]["R_mol_m3_s"] *= 1.01
    _expect_failure(validate_elastic_identity, bad_identity)

    validate_ei19_rows(_synthetic_ei19_rows())
    _expect_failure(validate_ei19_rows, _synthetic_ei19_rows(rhs_scale=-1.0))
    _expect_failure(validate_ei19_rows, _synthetic_ei19_rows(rhs_scale=4.0 / EI19_LOSS_EV))
    _expect_failure(validate_ei19_rows, _synthetic_ei19_rows(rate_scale=1.1))

    sample_table = [(LOOKUP_MIN_EV, 1.0), (EPSILON_REF_EV, 2.0), (LOOKUP_MAX_EV, 3.0)]
    _close(_interp_strict(sample_table, EPSILON_REF_EV), 2.0, rel=0, abs_=0, label="self-test lookup anchor")
    _expect_failure(_interp_strict, sample_table, LOOKUP_MIN_EV - 0.1)
    _expect_failure(_interp_strict, sample_table, LOOKUP_MAX_EV + 0.1)

    for species, spec in ELASTIC.items():
        text = _elastic_input(spec, 600.0)
        if "type = ADParsedFunctorMaterial" not in text or "type = FVCoupledForce" not in text:
            raise AssertionError(f"{species}: standard-MOOSE elastic composition missing")
        if "v = S_elastic_hat" not in text or "coef = 1" not in text:
            raise AssertionError(f"{species}: elastic projection wiring changed")
        if "meanE tgas rprog" not in text:
            raise AssertionError(f"{species}: parser aliases changed")
        if any(alias in {"x", "y", "z", "t", "pi", "e"} for alias in ("meanE", "tgas", "rprog")):
            raise AssertionError("reserved parsed-functor symbol")

    ei19_text = _ei19_input()
    if "type = FVCoupledForce" not in ei19_text or f"v = {EI19['progress']}" not in ei19_text:
        raise AssertionError("EI19 standard-MOOSE projection missing")
    if ei19_text.count(f"v = {EI19['progress']}") != 1:
        raise AssertionError("EI19 energy path must consume canonical progress exactly once")
    for forbidden in (
        "PhysicsFVElectronReactionEnergySource",
        "PhysicsFVElectronReactionSource",
        "PhysicsFVSpeciesReactionSource",
        "o_excitation_1d.txt",
        "o_ionization.txt",
    ):
        if forbidden in ei19_text:
            raise AssertionError(f"EI19 forbidden/deferred projection present: {forbidden}")

    print("E8_ELASTIC_EI19_RUNTIME_CHECKER_SELFTEST_PASS")


def _sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _preflight(input_path):
    subprocess.run(
        [sys.executable, str(ROOT / "bin/physics.py"), "preflight", str(input_path)],
        cwd=ROOT,
        check=True,
    )


def _execute_case(executable, work_root, case_name, input_text, table_name, *, expect_strict_failure=False):
    case_dir = work_root / case_name
    case_dir.mkdir()
    shutil.copy2(DATA_DIR / table_name, case_dir / table_name)
    input_path = case_dir / f"{case_name}.i"
    input_path.write_text(input_text)

    _preflight(input_path)

    check_cmd = [str(executable), "--check-input", "-i", input_path.name]
    p2 = subprocess.run(check_cmd, cwd=case_dir, text=True, capture_output=True)
    if expect_strict_failure:
        if p2.returncode != 0:
            output = p2.stdout + p2.stderr
        else:
            p3 = subprocess.run(
                [str(executable), "-i", input_path.name],
                cwd=case_dir,
                text=True,
                capture_output=True,
            )
            if p3.returncode == 0:
                raise AssertionError(f"{case_name}: out-of-range negative control unexpectedly ran")
            output = p3.stdout + p3.stderr
        if "outside lookup range" not in output or "strict Stage-4 policy forbids clamp/floor" not in output:
            raise AssertionError(f"{case_name}: strict bounds failure signature missing")
        return None

    if p2.returncode != 0:
        raise AssertionError(f"{case_name}: P2 check-input failed\n{p2.stdout}\n{p2.stderr}")
    p3 = subprocess.run(
        [str(executable), "-i", input_path.name],
        cwd=case_dir,
        text=True,
        capture_output=True,
    )
    if p3.returncode != 0:
        raise AssertionError(f"{case_name}: P3 runtime failed\n{p3.stdout}\n{p3.stderr}")

    csv_path = case_dir / f"{case_name}_out.csv"
    if not csv_path.is_file():
        raise AssertionError(f"{case_name}: expected CSV missing")
    return list(csv.DictReader(csv_path.open(newline="")))


def run_controlled_executable(executable, evidence_out=None, repository_sha=None, build_base_ref=None):
    executable = Path(executable).resolve()
    if not executable.is_file():
        raise SystemExit(f"Physics executable does not exist: {executable}")

    for filename in TABLE_BLOBS:
        table = _read_table(DATA_DIR / filename)
        anchor = _interp_strict(table, EPSILON_REF_EV)
        expected = (
            ELASTIC["O2"]["anchor_k"]
            if filename == "o2_elastic.txt"
            else ELASTIC["O"]["anchor_k"]
            if filename == "o_elastic.txt"
            else EI19["anchor_k"]
        )
        _close(anchor, expected, rel=0, abs_=0, label=f"{filename} frozen anchor")

    with tempfile.TemporaryDirectory(prefix="e8-elastic-ei19-") as tmp:
        work = Path(tmp)
        elastic_results = {}
        for species, spec in ELASTIC.items():
            elastic_results[species] = {}
            for regime_id, tgas, _ in REGIMES:
                case_name = f"e8_{species.lower()}_elastic_{regime_id.lower()}"
                rows = _execute_case(
                    executable,
                    work,
                    case_name,
                    _elastic_input(spec, tgas),
                    spec["table"],
                )
                elastic_results[species][regime_id] = validate_elastic_rows(
                    rows, species, regime_id, tgas
                )
        validate_elastic_identity(elastic_results)

        ei19_rows = _execute_case(
            executable,
            work,
            "e8_ei19_o_excitation_4p192",
            _ei19_input(),
            EI19["table"],
        )
        ei19_result = validate_ei19_rows(ei19_rows)

        _execute_case(
            executable,
            work,
            "e8_strict_bound_below",
            _ei19_input(LOOKUP_MIN_EV - 0.1),
            EI19["table"],
            expect_strict_failure=True,
        )
        _execute_case(
            executable,
            work,
            "e8_strict_bound_above",
            _ei19_input(LOOKUP_MAX_EV + 0.1),
            EI19["table"],
            expect_strict_failure=True,
        )

    evidence = {
        "claim": "Stage-4 bounded local runtime discriminator for EI02/EI17 elastic and EI19 energy-only projection",
        "acceptance_layer": "LOCAL_RUNTIME_ACCURACY",
        "integrated_physics_accuracy": "NOT_ESTABLISHED",
        "runtime_mode": "direct_executable",
        "runtime_executable": str(executable),
        "runtime_executable_sha256": _sha256(executable),
        "source_table_git_blobs": TABLE_BLOBS,
        "controlled_mean_energy_eV": EPSILON_REF_EV,
        "controlled_target_concentration_mol_m3": C_TARGET,
        "elastic": elastic_results,
        "ei19": ei19_result,
        "strict_bounds_negative_controls": {
            "below_1p40991_eV": "PASS_REJECTED",
            "above_22p1378_eV": "PASS_REJECTED",
        },
        "projection_ownership": {
            "elastic": "ADParsedFunctorMaterial -> standard MOOSE FVCoupledForce",
            "ei19": "standard MOOSE FVCoupledForce",
            "custom_energy_projector_instantiated": False,
            "ei19_particle_or_heavy_projection": "NONE",
        },
    }
    if repository_sha:
        evidence["repository_sha"] = repository_sha
    if build_base_ref:
        evidence["build_base_ref"] = build_base_ref
    if evidence_out:
        Path(evidence_out).write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")

    print(
        "E8_ELASTIC_RUNTIME_VECTOR "
        f"R_O2={elastic_results['O2']['HOT_ELECTRON']['R_mol_m3_s']:.12g} "
        f"R_O={elastic_results['O']['HOT_ELECTRON']['R_mol_m3_s']:.12g}"
    )
    print(
        "E8_EI19_RUNTIME_VECTOR "
        f"R={ei19_result['R_mol_m3_s']:.12g} "
        f"n_epsilon_hat={ei19_result['final_n_epsilon_hat']:.12g}"
    )
    print("E8_ELASTIC_EI19_LOCAL_RUNTIME_PASS")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--executable")
    parser.add_argument("--evidence-out")
    parser.add_argument("--repository-sha")
    parser.add_argument("--build-base-ref")
    args = parser.parse_args()

    if args.self_test:
        runtime_checker_self_test()
    elif args.executable:
        run_controlled_executable(
            args.executable,
            args.evidence_out,
            args.repository_sha,
            args.build_base_ref,
        )
    else:
        raise SystemExit("--self-test or --executable is required")


if __name__ == "__main__":
    main()
