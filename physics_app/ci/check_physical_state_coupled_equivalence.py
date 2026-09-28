#!/usr/bin/env python3
"""Coupled normalized-vs-physical electron-state equivalence discriminator.

Builds two mathematically equivalent 1-D plasma electrostatic cases:
  * legacy normalized electron state with explicit physical-density bridges
  * direct physical electron number/energy density state

The cases share the same physical charge density, electron mean energy, transport
closure, reaction progress, and Poisson equation. The runtime comparison is
cell-by-cell for potential, electric-field proxy (-grad(phi)), electron state,
mean energy, mobility, reaction progress, and charge density.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
import tempfile
from pathlib import Path

N_A = 6.02214076e23
N_E0 = 1.0e16
MEAN_E0_EV = 5.73276
DOMAIN_M = 1.0e-3
NX = 8
RHO = 1.0
M_ION = 0.032
N_ION = 1.1e16
W_ION = N_ION * M_ION / (RHO * N_A)

TRANSPORT_TABLE = """1.0 2.0e24 3.0e24
5.73276 3.0e24 4.5e24
10.0 4.0e24 6.0e24
"""

RATE_TABLE = """1.0 1.0e8
5.73276 2.0e8
10.0 3.0e8
"""

FIELDS = (
    "potential_sample",
    "grad_phi_x",
    "n_e_sample",
    "n_epsilon_sample",
    "mean_energy_sample",
    "mobility_sample",
    "reaction_rate_sample",
    "charge_density_sample",
    "poisson_source_sample",
)

REL_TOL = {
    "potential_sample": 2.0e-9,
    "grad_phi_x": 2.0e-9,
    "n_e_sample": 2.0e-12,
    "n_epsilon_sample": 2.0e-12,
    "mean_energy_sample": 2.0e-12,
    "mobility_sample": 2.0e-12,
    "reaction_rate_sample": 2.0e-12,
    "charge_density_sample": 2.0e-12,
    "poisson_source_sample": 2.0e-12,
}

ABS_TOL = {
    "potential_sample": 1.0e-10,
    "grad_phi_x": 1.0e-7,
    "n_e_sample": 10.0,
    "n_epsilon_sample": 100.0,
    "mean_energy_sample": 1.0e-11,
    "mobility_sample": 1.0e-20,
    "reaction_rate_sample": 1.0e-12,
    "charge_density_sample": 1.0e-18,
    "poisson_source_sample": 1.0e-6,
}


def _state_sections(state_form: str) -> str:
    if state_form == "normalized":
        return f"""
  [electron_number_state]
    type = ADParsedFunctorMaterial
    property_name = n_e_hat
    expression = '1.0 + 0.2*x/{DOMAIN_M:.17g}'
  []
  [electron_energy_state]
    type = ADParsedFunctorMaterial
    property_name = n_epsilon_hat
    expression = '1.0 + 0.1*x/{DOMAIN_M:.17g}'
  []
  [electron_number_bridge]
    type = ADParsedFunctorMaterial
    property_name = n_e_physical
    functor_names = 'n_e_hat'
    functor_symbols = 'nehat'
    expression = '{N_E0:.17g}*nehat'
  []
  [electron_energy_bridge]
    type = ADParsedFunctorMaterial
    property_name = n_epsilon_physical
    functor_names = 'n_epsilon_hat'
    functor_symbols = 'epshat'
    expression = '{N_E0 * MEAN_E0_EV:.17g}*epshat'
  []
  [electron_closure]
    type = PhysicsElectronClosureMaterial
    state_form = normalized
    normalized_electron_density = n_e_hat
    normalized_electron_energy_density = n_epsilon_hat
    electron_energy_reference_eV = {MEAN_E0_EV:.17g}
    gas_pressure = gas_pressure
    gas_temperature = gas_temperature
    transport_table_file = transport_table.txt
    lookup_bounds_policy = error
  []
"""
    if state_form == "physical":
        return f"""
  [electron_number_state]
    type = ADParsedFunctorMaterial
    property_name = n_e_physical
    expression = '{N_E0:.17g}*(1.0 + 0.2*x/{DOMAIN_M:.17g})'
  []
  [electron_energy_state]
    type = ADParsedFunctorMaterial
    property_name = n_epsilon_physical
    expression = '{N_E0 * MEAN_E0_EV:.17g}*(1.0 + 0.1*x/{DOMAIN_M:.17g})'
  []
  [electron_closure]
    type = PhysicsElectronClosureMaterial
    state_form = physical_eV
    electron_number_density = n_e_physical
    electron_energy_density = n_epsilon_physical
    gas_pressure = gas_pressure
    gas_temperature = gas_temperature
    transport_table_file = transport_table.txt
    lookup_bounds_policy = error
  []
"""
    raise ValueError(state_form)


def runtime_input(state_form: str) -> str:
    return f"""[Mesh]
  type = GeneratedMesh
  dim = 1
  nx = {NX}
  xmin = 0.0
  xmax = {DOMAIN_M:.17g}
[]

[Variables]
  [potential]
    type = MooseVariableFVReal
    initial_condition = 0.0
  []
[]

[AuxVariables]
  [grad_phi]
    order = CONSTANT
    family = MONOMIAL_VEC
  []
  [grad_phi_x]
    order = CONSTANT
    family = MONOMIAL
  []
  [potential_sample]
    order = CONSTANT
    family = MONOMIAL
  []
  [n_e_sample]
    order = CONSTANT
    family = MONOMIAL
  []
  [n_epsilon_sample]
    order = CONSTANT
    family = MONOMIAL
  []
  [mean_energy_sample]
    order = CONSTANT
    family = MONOMIAL
  []
  [mobility_sample]
    order = CONSTANT
    family = MONOMIAL
  []
  [reaction_rate_sample]
    order = CONSTANT
    family = MONOMIAL
  []
  [charge_density_sample]
    order = CONSTANT
    family = MONOMIAL
  []
  [poisson_source_sample]
    order = CONSTANT
    family = MONOMIAL
  []
[]

[FunctorMaterials]
  [constants]
    type = ADGenericFunctorMaterial
    prop_names = 'one gas_pressure gas_temperature target_molar_concentration mixture_density ion_mass_fraction'
    prop_values = '1.0 100.0 300.0 0.025 {RHO:.17g} {W_ION:.17g}'
  []
{_state_sections(state_form)}
  [reaction]
    type = PhysicsElectronImpactRateMaterial
    rate_table_file = rate_table.txt
    mean_energy = electron_mean_energy_eV
    electron_number_density = n_e_physical
    target_molar_concentration = target_molar_concentration
    reaction_progress = R_test
  []
  [charge]
    type = PhysicsPlasmaChargeDensityMaterial
    density = mixture_density
    electron_density = n_e_physical
    ion_ids = 'ion'
    ion_mass_fractions = 'ion_mass_fraction'
    ion_molar_masses = '{M_ION:.17g}'
    ion_charges = '1'
  []
[]

[FVKernels]
  [poisson_diffusion]
    type = FVDiffusion
    variable = potential
    coeff = one
  []
  [poisson_charge]
    type = FVCoupledForce
    variable = potential
    v = poisson_charge_source
    coef = 1.0
  []
[]

[FVBCs]
  [left_ground]
    type = FVDirichletBC
    variable = potential
    boundary = left
    value = 0.0
  []
  [right_ground]
    type = FVDirichletBC
    variable = potential
    boundary = right
    value = 0.0
  []
[]

[AuxKernels]
  [grad_phi]
    type = ADFunctorElementalGradientAux
    variable = grad_phi
    functor = potential
    execute_on = 'TIMESTEP_END'
  []
  [grad_phi_x]
    type = VectorVariableComponentAux
    variable = grad_phi_x
    vector_variable = grad_phi
    component = x
    execute_on = 'TIMESTEP_END'
  []
  [potential_copy]
    type = FunctorAux
    variable = potential_sample
    functor = potential
    execute_on = 'TIMESTEP_END'
  []
  [n_e_copy]
    type = FunctorAux
    variable = n_e_sample
    functor = n_e_physical
    execute_on = 'TIMESTEP_END'
  []
  [n_epsilon_copy]
    type = FunctorAux
    variable = n_epsilon_sample
    functor = n_epsilon_physical
    execute_on = 'TIMESTEP_END'
  []
  [mean_energy_copy]
    type = FunctorAux
    variable = mean_energy_sample
    functor = electron_mean_energy_eV
    execute_on = 'TIMESTEP_END'
  []
  [mobility_copy]
    type = FunctorAux
    variable = mobility_sample
    functor = electron_mobility
    execute_on = 'TIMESTEP_END'
  []
  [reaction_copy]
    type = FunctorAux
    variable = reaction_rate_sample
    functor = R_test
    execute_on = 'TIMESTEP_END'
  []
  [charge_copy]
    type = FunctorAux
    variable = charge_density_sample
    functor = charge_density
    execute_on = 'TIMESTEP_END'
  []
  [poisson_source_copy]
    type = FunctorAux
    variable = poisson_source_sample
    functor = poisson_charge_source
    execute_on = 'TIMESTEP_END'
  []
[]

[VectorPostprocessors]
  [field_samples]
    type = ElementValueSampler
    variable = 'potential_sample grad_phi_x n_e_sample n_epsilon_sample mean_energy_sample mobility_sample reaction_rate_sample charge_density_sample poisson_source_sample'
    sort_by = id
    execute_on = 'TIMESTEP_END'
  []
[]

[Executioner]
  type = Steady
  solve_type = NEWTON
  nl_rel_tol = 1.0e-11
  nl_abs_tol = 1.0e-12
  nl_max_its = 20
[]

[Outputs]
  csv = true
  exodus = false
[]
"""


def _find_sample_csv(case_dir: Path) -> Path:
    matches = sorted(case_dir.glob("*field_samples*.csv"))
    if matches:
        return matches[-1]
    for path in sorted(case_dir.glob("*.csv")):
        try:
            header = path.read_text(encoding="utf-8").splitlines()[0]
        except (OSError, IndexError):
            continue
        if all(name in header for name in ("potential_sample", "n_e_sample", "charge_density_sample")):
            return path
    raise AssertionError(f"no ElementValueSampler CSV found in {case_dir}")


def _read_samples(path: Path) -> list[dict[str, float]]:
    with path.open(newline="") as handle:
        raw = list(csv.DictReader(handle))
    rows: list[dict[str, float]] = []
    for row in raw:
        parsed: dict[str, float] = {}
        for key in ("id", "x", *FIELDS):
            if key not in row or row[key] == "":
                continue
            value = float(row[key])
            if not math.isfinite(value):
                raise AssertionError(f"{path}: non-finite {key}")
            parsed[key] = value
        if all(name in parsed for name in FIELDS):
            rows.append(parsed)
    if len(rows) != NX:
        raise AssertionError(f"{path}: expected {NX} sampled cells, got {len(rows)}")
    rows.sort(key=lambda r: r.get("id", r.get("x", 0.0)))
    return rows


def _run_case(executable: Path, root: Path, state_form: str) -> list[dict[str, float]]:
    case_dir = root / state_form
    case_dir.mkdir()
    (case_dir / "input.i").write_text(runtime_input(state_form), encoding="utf-8")
    (case_dir / "transport_table.txt").write_text(TRANSPORT_TABLE, encoding="utf-8")
    (case_dir / "rate_table.txt").write_text(RATE_TABLE, encoding="utf-8")

    for args in (("--check-input", "-i", "input.i"), ("-i", "input.i")):
        proc = subprocess.run(
            [str(executable), *args],
            cwd=case_dir,
            text=True,
            capture_output=True,
        )
        if proc.returncode:
            raise AssertionError(
                f"{state_form} case failed: {' '.join(args)}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
    return _read_samples(_find_sample_csv(case_dir))


def _norm(values: list[float]) -> float:
    return math.sqrt(sum(v * v for v in values))


def compare(normalized: list[dict[str, float]], physical: list[dict[str, float]]) -> dict:
    if len(normalized) != len(physical):
        raise AssertionError("sample count mismatch")

    metrics = {}
    for field in FIELDS:
        old = [row[field] for row in normalized]
        new = [row[field] for row in physical]
        diffs = [b - a for a, b in zip(old, new)]
        max_abs = max(abs(v) for v in diffs)
        denom = max(_norm(old), 1.0e-300)
        rel_l2 = _norm(diffs) / denom
        metrics[field] = {"max_abs": max_abs, "relative_l2": rel_l2}
        for idx, (a, b) in enumerate(zip(old, new)):
            if not math.isclose(a, b, rel_tol=REL_TOL[field], abs_tol=ABS_TOL[field]):
                raise AssertionError(
                    f"{field} mismatch at cell {idx}: normalized-path={a:.17g}, physical-path={b:.17g}"
                )

    old_x = [r.get("x") for r in normalized]
    new_x = [r.get("x") for r in physical]
    if old_x != new_x:
        raise AssertionError("sample coordinates differ")

    potential = [r["potential_sample"] for r in physical]
    grad = [r["grad_phi_x"] for r in physical]
    charge = [r["charge_density_sample"] for r in physical]
    rate = [r["reaction_rate_sample"] for r in physical]
    mean = [r["mean_energy_sample"] for r in physical]

    if max(abs(v) for v in potential) <= 1.0e-8:
        raise AssertionError("Poisson discriminator is degenerate: potential is effectively zero")
    if max(abs(v) for v in grad) <= 1.0e-5:
        raise AssertionError("Poisson discriminator is degenerate: electric field is effectively zero")
    if not (min(charge) < 0.0 < max(charge)):
        raise AssertionError("charge profile must span both signs")
    if not (min(rate) > 0.0 and max(rate) > min(rate)):
        raise AssertionError("reaction progress must be positive and spatially varying")
    if not (min(mean) > 1.0 and max(mean) < 10.0 and max(mean) > min(mean)):
        raise AssertionError("mean-energy profile must be non-degenerate and inside lookup bounds")

    electric_old = [-r["grad_phi_x"] for r in normalized]
    electric_new = [-r["grad_phi_x"] for r in physical]
    e_diff = [b - a for a, b in zip(electric_old, electric_new)]
    metrics["electric_field_x"] = {
        "max_abs": max(abs(v) for v in e_diff),
        "relative_l2": _norm(e_diff) / max(_norm(electric_old), 1.0e-300),
    }
    return {
        "status": "PASS",
        "cells": NX,
        "metrics": metrics,
        "physical_ranges": {
            "potential_V": [min(potential), max(potential)],
            "electric_field_V_m": [min(electric_new), max(electric_new)],
            "charge_density_C_m3": [min(charge), max(charge)],
            "reaction_progress_mol_m3_s": [min(rate), max(rate)],
            "mean_energy_eV": [min(mean), max(mean)],
        },
    }


def self_test() -> None:
    normalized = runtime_input("normalized")
    physical = runtime_input("physical")
    for token in (
        "state_form = normalized",
        "normalized_electron_density = n_e_hat",
        f"expression = '{N_E0:.17g}*nehat'",
        "electron_density = n_e_physical",
        "v = poisson_charge_source",
        "type = ElementValueSampler",
    ):
        if token not in normalized:
            raise AssertionError(f"normalized fixture missing {token}")
    for token in (
        "state_form = physical_eV",
        "electron_number_density = n_e_physical",
        "electron_energy_density = n_epsilon_physical",
        "electron_density = n_e_physical",
        "v = poisson_charge_source",
        "type = ElementValueSampler",
    ):
        if token not in physical:
            raise AssertionError(f"physical fixture missing {token}")
    if "n_e_hat" in physical or "n_epsilon_hat" in physical:
        raise AssertionError("physical fixture leaked normalized state")
    print("PHYSICAL_STATE_COUPLED_EQUIVALENCE_SELFTEST_PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--executable")
    parser.add_argument("--evidence-out")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0
    if not args.executable:
        parser.error("--executable is required unless --self-test is used")

    executable = Path(args.executable).resolve()
    if not executable.is_file():
        raise SystemExit(f"Physics executable does not exist: {executable}")

    with tempfile.TemporaryDirectory(prefix="physical-coupled-equivalence-") as tmp:
        root = Path(tmp)
        normalized = _run_case(executable, root, "normalized")
        physical = _run_case(executable, root, "physical")
        evidence = compare(normalized, physical)

    evidence["executable"] = str(executable)
    if args.evidence_out:
        Path(args.evidence_out).write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    print(
        "PHYSICAL_STATE_COUPLED_EQUIVALENCE_PASS "
        f"phi_rel_l2={evidence['metrics']['potential_sample']['relative_l2']:.3e} "
        f"E_rel_l2={evidence['metrics']['electric_field_x']['relative_l2']:.3e} "
        f"ne_rel_l2={evidence['metrics']['n_e_sample']['relative_l2']:.3e} "
        f"rate_rel_l2={evidence['metrics']['reaction_rate_sample']['relative_l2']:.3e}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
