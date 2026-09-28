#!/usr/bin/env python3
"""A/B runtime gate for pure electron-energy state symbol migration.

Old case: primary electron-energy-density variable is named n_epsilon.
New case: the same physical variable is named mean_en.

Only the symbol changes. Equations, units, coefficients, mesh, BCs, initial
profiles, and solver settings are identical.
"""

import argparse
import csv
import math
import shutil
from pathlib import Path

N_E0 = 1.0e16
MEAN_E0_EV = 5.73276
E_CHARGE = 1.602176634e-19
EPS0 = 8.8541878128e-12
NX = 24
DT = 1.0e-6


def _input(energy_symbol: str) -> str:
    return f"""[Mesh]
  [mesh]
    type = GeneratedMeshGenerator
    dim = 1
    nx = {NX}
    xmin = 0
    xmax = 1
  []
[]

[Variables]
  [n_e]
    type = MooseVariableFVReal
    scaling = 1e-16
  []
  [{energy_symbol}]
    type = MooseVariableFVReal
    scaling = 1e-16
  []
  [phi]
    type = MooseVariableFVReal
    initial_condition = 0
  []
[]

[Functions]
  [n_profile]
    type = ParsedFunction
    expression = '{N_E0:.17g}*(0.95+0.10*x)'
  []
  [energy_profile]
    type = ParsedFunction
    expression = '{N_E0 * MEAN_E0_EV:.17g}*(1.05-0.10*x)'
  []
  [poisson_source_profile]
    type = ParsedFunction
    expression = '{E_CHARGE:.17g}*({N_E0:.17g}-{N_E0:.17g}*(0.95+0.10*x))/{EPS0:.17g}'
  []
[]

[ICs]
  [n_ic]
    type = FunctionIC
    variable = n_e
    function = n_profile
  []
  [energy_ic]
    type = FunctionIC
    variable = {energy_symbol}
    function = energy_profile
  []
[]

[FunctorMaterials]
  [constants]
    type = GenericFunctorMaterial
    prop_names = 'energy_diffusivity relative_permittivity'
    prop_values = '0.05 1.0'
  []
[]

[FVKernels]
  [n_time]
    type = FVTimeKernel
    variable = n_e
  []
  [energy_time]
    type = FVTimeKernel
    variable = {energy_symbol}
  []
  [energy_diffusion]
    type = FVDiffusion
    variable = {energy_symbol}
    coeff = energy_diffusivity
  []
  [phi_diffusion]
    type = FVDiffusion
    variable = phi
    coeff = relative_permittivity
  []
  [phi_source]
    type = FVCoupledForce
    variable = phi
    v = poisson_source_profile
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
  [symbol_samples]
    type = ElementValueSampler
    variable = 'n_e {energy_symbol} phi'
    sort_by = id
    execute_on = 'TIMESTEP_END'
  []
[]

[Executioner]
  type = Transient
  dt = {DT:.17g}
  end_time = {DT:.17g}
  solve_type = NEWTON
  automatic_scaling = false
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
    for name, symbol in (("old", "n_epsilon"), ("new", "mean_en")):
        case = root / name
        case.mkdir(parents=True)
        (case / "input.i").write_text(_input(symbol))


def _rows(case: Path, symbol: str):
    files = sorted(case.glob("*symbol_samples*.csv"))
    if not files:
        raise AssertionError(f"{case}: missing symbol_samples CSV")
    with files[-1].open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != NX:
        raise AssertionError(f"{case}: expected {NX} cells, got {len(rows)}")
    out = []
    for row in rows:
        x = float(row["x"])
        ne = float(row["n_e"])
        energy = float(row[symbol])
        phi = float(row["phi"])
        for key, value in (("x", x), ("n_e", ne), ("energy", energy), ("phi", phi)):
            if not math.isfinite(value):
                raise AssertionError(f"{case}: non-finite {key}")
        out.append(
            {
                "x": x,
                "n_e": ne,
                "energy": energy,
                "mean_energy": energy / ne,
                "charge_density": E_CHARGE * (N_E0 - ne),
                "poisson_source": E_CHARGE * (N_E0 - ne) / EPS0,
                "phi": phi,
            }
        )
    out.sort(key=lambda r: r["x"])
    return out


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
    old = _rows(root / "old", "n_epsilon")
    new = _rows(root / "new", "mean_en")
    for i, (a, b) in enumerate(zip(old, new)):
        for key, rel, abs_ in (
            ("x", 0.0, 1e-14),
            ("n_e", 2e-13, 2.0),
            ("energy", 2e-13, 8.0),
            ("mean_energy", 2e-13, 1e-12),
            ("charge_density", 2e-12, 1e-16),
            ("poisson_source", 2e-12, 1e-3),
            ("phi", 2e-10, 1e-7),
        ):
            _close(a[key], b[key], rel=rel, abs_=abs_, label=f"cell {i} {key}")

    e_old = _electric_field(old)
    e_new = _electric_field(new)
    for i, (a, b) in enumerate(zip(e_old, e_new)):
        _close(a, b, rel=3e-10, abs_=2e-6, label=f"cell {i} electric field")

    phi_scale = max(max(abs(r["phi"]) for r in old), 1.0)
    e_scale = max(max(abs(v) for v in e_old), 1.0)
    energy_scale = max(max(abs(r["energy"]) for r in old), 1.0)
    phi_l2 = math.sqrt(sum((a["phi"] - b["phi"]) ** 2 for a, b in zip(old, new)) / len(old))
    e_l2 = math.sqrt(sum((a - b) ** 2 for a, b in zip(e_old, e_new)) / len(old))
    energy_l2 = math.sqrt(sum((a["energy"] - b["energy"]) ** 2 for a, b in zip(old, new)) / len(old))

    print(
        "MEAN_EN_SYMBOL_EQUIVALENCE_PASS "
        f"cells={len(old)} "
        f"rel_energy_l2={energy_l2 / energy_scale:.3e} "
        f"rel_phi_l2={phi_l2 / phi_scale:.3e} "
        f"rel_E_l2={e_l2 / e_scale:.3e} "
        f"max_denergy={max(abs(a['energy']-b['energy']) for a,b in zip(old,new)):.3e} "
        f"max_dphi={max(abs(a['phi']-b['phi']) for a,b in zip(old,new)):.3e} "
        f"max_dE={max(abs(a-b) for a,b in zip(e_old,e_new)):.3e}"
    )


def self_test():
    old = _input("n_epsilon")
    new = _input("mean_en")
    assert "[n_epsilon]" in old
    assert "variable = n_epsilon" in old
    assert "[mean_en]" in new
    assert "variable = mean_en" in new
    assert old.replace("n_epsilon", "__ENERGY__") == new.replace("mean_en", "__ENERGY__")
    print("MEAN_EN_SYMBOL_EQUIVALENCE_SELFTEST_PASS")


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
        print(f"MEAN_EN_SYMBOL_EQUIVALENCE_PREPARED {args.prepare}")
    if args.compare:
        compare(args.compare)
    if not (args.self_test or args.prepare or args.compare):
        parser.error("choose --self-test, --prepare DIR, or --compare DIR")


if __name__ == "__main__":
    main()
