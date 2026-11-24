#!/usr/bin/env python3
"""Compare the PlasmaClosures electron closure at 100 Pa and 10 mTorr.

Also runs the frozen-heavy four-file Gummel fixture at the branch pressure to
confirm that the nested topology still constructs and executes.
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
CI = REPO / "physics_app" / "ci"
RESULTS = ROOT / "results"
P_100_PA = 100.0
P_10_MTORR_PA = 1.333223684


def diagnostic_input(pressure_pa: float) -> str:
    return f"""[Mesh]
  type = GeneratedMesh
  dim = 1
  nx = 2
  xmin = 0.0
  xmax = 1.0
[]

[Variables]
  [n_e]
    type = MooseVariableFVReal
    initial_condition = 1.0e16
  []
  [mean_en]
    type = MooseVariableFVReal
    initial_condition = 5.73276e16
  []
[]

[FunctorMaterials]
  [gas_state]
    type = ADGenericFunctorMaterial
    prop_names = 'p_gas T_g'
    prop_values = '{pressure_pa:.12g} 300.0'
  []
[]

[PlasmaClosures]
  [electron]
    role = electron
    electron_state_form = physical_eV
    electron_number_density = n_e
    electron_energy_density = mean_en
    gas_pressure = p_gas
    gas_temperature = T_g
    electron_transport_table_file = plasma_closures_transport_table.txt
  []
[]

[FVKernels]
  [n_time]
    type = FVTimeKernel
    variable = n_e
  []
  [energy_time]
    type = FVTimeKernel
    variable = mean_en
  []
[]

[Postprocessors]
  [mean_energy_eV]
    type = ElementAverageFunctorPostprocessor
    functor = electron_mean_energy_eV
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [electron_temperature_K]
    type = ElementAverageFunctorPostprocessor
    functor = electron_temperature_K
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [neutral_number_density_m3]
    type = ElementAverageFunctorPostprocessor
    functor = neutral_number_density
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [electron_mobility_m2_Vs]
    type = ElementAverageFunctorPostprocessor
    functor = electron_mobility
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [electron_diffusion_m2_s]
    type = ElementAverageFunctorPostprocessor
    functor = electron_diffusion
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [electron_energy_mobility_m2_Vs]
    type = ElementAverageFunctorPostprocessor
    functor = electron_energy_mobility
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [electron_energy_diffusion_m2_s]
    type = ElementAverageFunctorPostprocessor
    functor = electron_energy_diffusion
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]

[Executioner]
  type = Transient
  dt = 1.0e-8
  end_time = 1.0e-8
  solve_type = NEWTON
[]

[Outputs]
  csv = true
[]
"""


def run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True)


def read_last_csv(path: Path) -> dict[str, float]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise RuntimeError(f"no CSV rows in {path}")
    return {k: float(v) for k, v in rows[-1].items() if k != "time"}


def run_diagnostic(binary: Path, name: str, pressure_pa: float) -> dict[str, float]:
    case = RESULTS / name
    shutil.rmtree(case, ignore_errors=True)
    case.mkdir(parents=True)
    shutil.copy2(CI / "plasma_closures_transport_table.txt", case / "plasma_closures_transport_table.txt")
    (case / "input.i").write_text(diagnostic_input(pressure_pa), encoding="utf-8")
    run([str(binary), "--check-input", "-i", "input.i"], case)
    run([str(binary), "-i", "input.i"], case)
    values = read_last_csv(case / "input_out.csv")
    values["pressure_Pa"] = pressure_pa
    return values


def run_gummel_smoke(binary: Path) -> None:
    for name in (
        "gummel_plasma_closures_heavy_main.i",
        "gummel_plasma_closures_driver.i",
        "gummel_plasma_closures_heavy_electron.i",
        "gummel_plasma_closures_heavy_poisson.i",
    ):
        run([str(binary), "--check-input", "-i", name], CI)
    run([str(binary), "-i", "gummel_plasma_closures_heavy_main.i"], CI)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, required=True)
    args = parser.parse_args()
    binary = args.binary.resolve()
    if not binary.is_file():
        raise SystemExit(f"missing Physics executable: {binary}")

    RESULTS.mkdir(parents=True, exist_ok=True)
    baseline = run_diagnostic(binary, "pressure_100Pa", P_100_PA)
    mtorr = run_diagnostic(binary, "pressure_10mTorr", P_10_MTORR_PA)
    run_gummel_smoke(binary)

    keys = sorted(set(baseline) & set(mtorr))
    ratios = {
        key: (mtorr[key] / baseline[key] if baseline[key] != 0.0 else None)
        for key in keys
        if key != "pressure_Pa"
    }
    summary = {
        "baseline_100Pa": baseline,
        "pressure_10mTorr": mtorr,
        "ratio_10mTorr_over_100Pa": ratios,
        "gummel_10mTorr_runtime": "PASS",
    }
    out = RESULTS / "comparison.json"
    out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("ISSUE351_10MTORR_RESULT " + json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
