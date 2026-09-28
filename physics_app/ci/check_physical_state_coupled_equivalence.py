#!/usr/bin/env python3
"""Runtime A/B equivalence gate for normalized versus physical electron states.

The two cases have identical physical electron number/energy density profiles, ion
inventory, lookup table, mesh, Poisson equation, and solver settings.  Only the
electron state representation differs.  The checker compares the actual MOOSE
cellwise outputs for electron state, mean energy, reaction progress, charge
density, Poisson source, potential, and the electric field reconstructed from
the potential samples.
"""

import argparse
import csv
import math
import shutil
from pathlib import Path

N_A = 6.02214076e23
N_E0 = 1.0e16
MEAN_E0_EV = 5.73276
M_ION = 0.032
RHO = 1.0
ION_NUMBER_DENSITY = N_E0
ION_MASS_FRACTION = ION_NUMBER_DENSITY * M_ION / (RHO * N_A)
NX = 24
XMIN = 0.0
XMAX = 1.0

FIELDS = (
    "n_e_state_aux",
    "n_epsilon_state_aux",
    "n_e_physical_aux",
    "n_epsilon_physical_aux",
    "mean_energy_aux",
    "charge_density_aux",
    "poisson_source_aux",
    "phi",
)


def _input(*, physical: bool) -> str:
    if physical:
        ne_expr = f"{N_E0:.17g}*(0.95+0.10*x)"
        ee_expr = f"{N_E0 * MEAN_E0_EV:.17g}*(1.05-0.10*x)"
        mean_expr = "ee/ne"
        ne_bridge_expr = "ne"
        ee_bridge_expr = "ee"
    else:
        ne_expr = "0.95+0.10*x"
        ee_expr = "1.05-0.10*x"
        mean_expr = f"{MEAN_E0_EV:.17g}*ee/ne"
        ne_bridge_expr = f"{N_E0:.17g}*ne"
        ee_bridge_expr = f"{N_E0 * MEAN_E0_EV:.17g}*ee"

    return f"""[Mesh]
  [mesh]
    type = GeneratedMeshGenerator
    dim = 1
    nx = {NX}
    xmin = {XMIN:.17g}
    xmax = {XMAX:.17g}
  []
[]

[Variables]
  [phi]
    type = MooseVariableFVReal
    initial_condition = 0
  []
[]

[AuxVariables]
  [n_e_state_aux]
    order = CONSTANT
    family = MONOMIAL
  []
  [n_epsilon_state_aux]
    order = CONSTANT
    family = MONOMIAL
  []
  [n_e_physical_aux]
    order = CONSTANT
    family = MONOMIAL
  []
  [n_epsilon_physical_aux]
    order = CONSTANT
    family = MONOMIAL
  []
  [mean_energy_aux]
    order = CONSTANT
    family = MONOMIAL
  []
  [charge_density_aux]
    order = CONSTANT
    family = MONOMIAL
  []
  [poisson_source_aux]
    order = CONSTANT
    family = MONOMIAL
  []
[]

[FunctorMaterials]
  [electron_number_state]
    type = ADParsedFunctorMaterial
    property_name = n_e_state
    expression = '{ne_expr}'
  []
  [electron_energy_state]
    type = ADParsedFunctorMaterial
    property_name = n_epsilon_state
    expression = '{ee_expr}'
  []
  [electron_number_physical]
    type = ADParsedFunctorMaterial
    property_name = n_e_physical
    functor_names = 'n_e_state'
    functor_symbols = 'ne'
    expression = '{ne_bridge_expr}'
  []
  [electron_energy_physical]
    type = ADParsedFunctorMaterial
    property_name = n_epsilon_physical
    functor_names = 'n_epsilon_state'
    functor_symbols = 'ee'
    expression = '{ee_bridge_expr}'
  []
  [constants]
    type = ADGenericFunctorMaterial
    prop_names = 'rho_const w_ion_const relative_permittivity'
    prop_values = '{RHO:.17g} {ION_MASS_FRACTION:.17g} 1.0'
  []
  [mean_energy]
    type = ADParsedFunctorMaterial
    property_name = mean_energy_probe
    functor_names = 'n_e_state n_epsilon_state'
    functor_symbols = 'ne ee'
    expression = '{mean_expr}'
  []
  [charge]
    type = QPXPlasmaChargeDensityMaterial
    density = rho_const
    electron_density = n_e_physical
    ion_ids = 'ion'
    ion_mass_fractions = 'w_ion_const'
    ion_molar_masses = '{M_ION:.17g}'
    ion_charges = '1'
  []
[]

[AuxKernels]
  [sample_ne_state]
    type = FunctorAux
    variable = n_e_state_aux
    functor = n_e_state
    execute_on = 'TIMESTEP_END'
  []
  [sample_ee_state]
    type = FunctorAux
    variable = n_epsilon_state_aux
    functor = n_epsilon_state
    execute_on = 'TIMESTEP_END'
  []
  [sample_ne_physical]
    type = FunctorAux
    variable = n_e_physical_aux
    functor = n_e_physical
    execute_on = 'TIMESTEP_END'
  []
  [sample_ee_physical]
    type = FunctorAux
    variable = n_epsilon_physical_aux
    functor = n_epsilon_physical
    execute_on = 'TIMESTEP_END'
  []
  [sample_mean]
    type = FunctorAux
    variable = mean_energy_aux
    functor = mean_energy_probe
    execute_on = 'TIMESTEP_END'
  []
  [sample_charge]
    type = FunctorAux
    variable = charge_density_aux
    functor = charge_density
    execute_on = 'TIMESTEP_END'
  []
  [sample_poisson]
    type = FunctorAux
    variable = poisson_source_aux
    functor = poisson_charge_source
    execute_on = 'TIMESTEP_END'
  []
[]

[FVKernels]
  [phi_diffusion]
    type = FVDiffusion
    variable = phi
    coeff = relative_permittivity
  []
  [phi_charge_source]
    type = FVCoupledForce
    variable = phi
    v = poisson_charge_source
  []
[]

[FVBCs]
  [phi_left]
    type = FVDirichletBC
    variable = phi
    boundary = left
    value = 0
  []
  [phi_right]
    type = FVDirichletBC
    variable = phi
    boundary = right
    value = 0
  []
[]

[VectorPostprocessors]
  [equivalence_samples]
    type = ElementValueSampler
    variable = 'phi n_e_state_aux n_epsilon_state_aux n_e_physical_aux n_epsilon_physical_aux mean_energy_aux charge_density_aux poisson_source_aux'
    sort_by = id
    execute_on = 'TIMESTEP_END'
  []
[]

[Executioner]
  type = Steady
  solve_type = NEWTON
  nl_abs_tol = 1e-9
  nl_rel_tol = 1e-12
  nl_max_its = 20
  l_tol = 1e-13
  l_max_its = 200
[]

[Outputs]
  csv = true
[]
"""


def prepare(root: Path) -> None:
    if root.exists():
        shutil.rmtree(root)
    for name, physical in (("normalized", False), ("physical", True)):
        case = root / name
        case.mkdir(parents=True)
        (case / "input.i").write_text(_input(physical=physical))


def _sample_csv(case: Path) -> Path:
    matches = sorted(case.glob("*equivalence_samples*.csv"))
    if not matches:
        raise AssertionError(f"{case}: missing ElementValueSampler CSV")
    return matches[-1]


def _rows(case: Path):
    with _sample_csv(case).open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != NX:
        raise AssertionError(f"{case}: expected {NX} sampled cells, got {len(rows)}")
    def num(row, key):
        value = float(row[key])
        if not math.isfinite(value):
            raise AssertionError(f"{case}: non-finite {key}")
        return value
    parsed = []
    for row in rows:
        parsed.append({key: num(row, key) for key in ("x",) + FIELDS})
    parsed.sort(key=lambda r: r["x"])
    return parsed


def _close(a, b, *, rel, abs_, label):
    if not math.isclose(a, b, rel_tol=rel, abs_tol=abs_):
        raise AssertionError(f"{label}: {a:.17g} != {b:.17g}")


def _electric_field(rows):
    x = [r["x"] for r in rows]
    phi = [r["phi"] for r in rows]
    out = []
    for i in range(len(rows)):
        if i == 0:
            grad = (phi[1] - phi[0]) / (x[1] - x[0])
        elif i == len(rows) - 1:
            grad = (phi[-1] - phi[-2]) / (x[-1] - x[-2])
        else:
            grad = (phi[i + 1] - phi[i - 1]) / (x[i + 1] - x[i - 1])
        out.append(-grad)
    return out


def compare(root: Path):
    old = _rows(root / "normalized")
    new = _rows(root / "physical")
    for i, (a, b) in enumerate(zip(old, new)):
        _close(a["x"], b["x"], rel=0.0, abs_=1e-14, label=f"cell {i} x")

        # Raw-state representation map.
        _close(
            N_E0 * a["n_e_state_aux"],
            b["n_e_state_aux"],
            rel=2e-12,
            abs_=2.0,
            label=f"cell {i} raw electron density map",
        )
        _close(
            N_E0 * MEAN_E0_EV * a["n_epsilon_state_aux"],
            b["n_epsilon_state_aux"],
            rel=2e-12,
            abs_=4.0,
            label=f"cell {i} raw electron energy map",
        )

        # Physical observables that must not change.
        for key, rel, abs_ in (
            ("n_e_physical_aux", 2e-12, 2.0),
            ("n_epsilon_physical_aux", 2e-12, 4.0),
            ("mean_energy_aux", 2e-12, 1e-11),
            ("charge_density_aux", 5e-11, 1e-16),
            ("poisson_source_aux", 5e-11, 1e-3),
            ("phi", 2e-9, 1e-6),
        ):
            _close(a[key], b[key], rel=rel, abs_=abs_, label=f"cell {i} {key}")

    e_old = _electric_field(old)
    e_new = _electric_field(new)
    for i, (a, b) in enumerate(zip(e_old, e_new)):
        _close(a, b, rel=3e-9, abs_=2e-5, label=f"cell {i} electric field")

    phi_scale = max(max(abs(r["phi"]) for r in old), 1.0)
    e_scale = max(max(abs(v) for v in e_old), 1.0)
    phi_l2 = math.sqrt(sum((a["phi"] - b["phi"]) ** 2 for a, b in zip(old, new)) / len(old))
    e_l2 = math.sqrt(sum((a - b) ** 2 for a, b in zip(e_old, e_new)) / len(e_old))
    result = {
        "cells": len(old),
        "relative_phi_l2": phi_l2 / phi_scale,
        "relative_E_l2": e_l2 / e_scale,
        "phi_max_abs_difference_V": max(abs(a["phi"] - b["phi"]) for a, b in zip(old, new)),
        "E_max_abs_difference_V_per_m": max(abs(a - b) for a, b in zip(e_old, e_new)),
    }
    print(
        "PHYSICAL_STATE_COUPLED_EQUIVALENCE_PASS "
        f"cells={result['cells']} "
        f"rel_phi_l2={result['relative_phi_l2']:.3e} "
        f"rel_E_l2={result['relative_E_l2']:.3e} "
        f"max_dphi={result['phi_max_abs_difference_V']:.3e} "
        f"max_dE={result['E_max_abs_difference_V_per_m']:.3e}"
    )
    return result


def self_test():
    with __import__("tempfile").TemporaryDirectory(prefix="physical-state-equivalence-") as tmp:
        root = Path(tmp)
        prepare(root)
        normalized = (root / "normalized" / "input.i").read_text()
        physical = (root / "physical" / "input.i").read_text()
        assert f"expression = '{MEAN_E0_EV:.17g}*ee/ne'" in normalized
        assert f"expression = '{N_E0:.17g}*ne'" in normalized
        assert "expression = 'ee/ne'" in physical
        assert "expression = 'ne'" in physical
        for text in (normalized, physical):
            for token in (
                "type = QPXPlasmaChargeDensityMaterial",
                "type = FVDiffusion",
                "v = poisson_charge_source",
                "type = ElementValueSampler",
            ):
                assert token in text
    print("PHYSICAL_STATE_COUPLED_EQUIVALENCE_SELFTEST_PASS")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--prepare", type=Path)
    parser.add_argument("--compare", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
    if args.prepare:
        prepare(args.prepare)
        print(f"PHYSICAL_STATE_COUPLED_EQUIVALENCE_PREPARED {args.prepare}")
    if args.compare:
        compare(args.compare)
    if not (args.self_test or args.prepare or args.compare):
        parser.error("choose --self-test, --prepare DIR, or --compare DIR")


if __name__ == "__main__":
    main()
