#!/usr/bin/env python3
"""Physics invariants for the reusable 2-D ICP electron diffusion + energy baseline."""
from __future__ import annotations

import bisect
import csv
import math
import os
from pathlib import Path

INITIAL_MEAN_ENERGY_EV = 5.73276
INITIAL_NE_M3 = 1.0e16
GAS_PRESSURE_PA = 1.333223684
GAS_TEMPERATURE_K = 300.0
BOLTZMANN_J_K = 1.380649e-23
ELEMENTARY_CHARGE_C = 1.602176634e-19
ELECTRON_MASS_KG = 9.1093837139e-31
AVOGADRO_PER_MOL = 6.02214076e23
TOTAL_THERMAL_WALL_AREA_M2 = 0.9023470915199818
EXPECTED_DT_S = float(os.environ.get("EXPECTED_DT_S", "1.0e-9"))
EXPECTED_STEPS = int(os.environ.get("EXPECTED_STEPS", "4"))
EXPECTED_END_TIME_S = float(os.environ.get("EXPECTED_END_TIME_S", "4.0e-9"))
EXPECTED_ENERGY_PER_PARTICLE_TE_FACTOR = float(
    os.environ.get("EXPECTED_ENERGY_PER_PARTICLE_TE_FACTOR", "2.0")
)

path = Path("electron_diffusion.csv")
if not path.is_file():
    raise SystemExit(f"missing runtime CSV: {path}")

with path.open(newline="") as handle:
    rows = list(csv.DictReader(handle))

expected_rows = EXPECTED_STEPS + 1
if len(rows) != expected_rows:
    raise SystemExit(
        f"expected initialization + {EXPECTED_STEPS} physical timesteps; "
        f"got {len(rows)} rows"
    )

required = {
    "time",
    "electron_inventory_mol",
    "electron_energy_inventory_eV_mol",
    "electron_density_avg",
    "electron_density_min",
    "electron_density_max",
    "mean_energy_avg_eV",
    "mean_energy_min_eV",
    "mean_energy_max_eV",
    "electron_diffusion_avg",
    "electron_wall_particle_rate",
    "electron_wall_energy_rate_eV_mol_s",
}
missing = required - set(rows[0])
if missing:
    raise SystemExit(f"missing expected columns: {sorted(missing)}")


def f(row, key):
    value = float(row[key])
    if not math.isfinite(value):
        raise SystemExit(f"non-finite {key}: {value}")
    return value


def relative_error(actual, expected):
    return abs(actual - expected) / max(abs(expected), 1.0e-300)


times = [f(row, "time") for row in rows]
expected_times = [index * EXPECTED_DT_S for index in range(expected_rows)]
if abs(expected_times[-1] - EXPECTED_END_TIME_S) > 1.0e-15:
    raise SystemExit(
        "checker configuration is inconsistent: "
        f"steps*dt={expected_times[-1]} end={EXPECTED_END_TIME_S}"
    )
if any(abs(a - b) > 1.0e-15 for a, b in zip(times, expected_times)):
    raise SystemExit(
        f"unexpected runtime time grid for dt={EXPECTED_DT_S}: {times}"
    )

energies = [f(row, "mean_energy_avg_eV") for row in rows]
energy_mins = [f(row, "mean_energy_min_eV") for row in rows]
energy_maxs = [f(row, "mean_energy_max_eV") for row in rows]
if min(energy_mins) <= 0.0:
    raise SystemExit(f"mean electron energy became non-positive: {energy_mins}")

table = Path("electron_moments.txt")
if not table.is_file():
    raise SystemExit(f"missing transport table: {table}")

table_rows = []
for raw in table.read_text().splitlines():
    fields = raw.split()
    if len(fields) < 3:
        continue
    try:
        energy, reduced_mobility, reduced_diffusion = map(float, fields[:3])
    except ValueError:
        continue
    table_rows.append((energy, reduced_mobility, reduced_diffusion))
if len(table_rows) < 2:
    raise SystemExit("transport table does not contain enough numeric rows")

table_rows.sort()
table_energy = [row[0] for row in table_rows]
table_reduced_diffusion = [row[2] for row in table_rows]
if min(energy_mins) < table_energy[0] or max(energy_maxs) > table_energy[-1]:
    raise SystemExit(
        "solved mean energy left strict transport-table bounds: "
        f"runtime=[{min(energy_mins)}, {max(energy_maxs)}] "
        f"table=[{table_energy[0]}, {table_energy[-1]}]"
    )


def interp_reduced_diffusion(mean_energy_eV):
    if mean_energy_eV < table_energy[0] or mean_energy_eV > table_energy[-1]:
        raise SystemExit(f"mean energy outside lookup table: {mean_energy_eV}")
    if mean_energy_eV == table_energy[0]:
        return table_reduced_diffusion[0]
    if mean_energy_eV == table_energy[-1]:
        return table_reduced_diffusion[-1]
    upper = bisect.bisect_right(table_energy, mean_energy_eV)
    lower = upper - 1
    x0, x1 = table_energy[lower], table_energy[upper]
    y0, y1 = table_reduced_diffusion[lower], table_reduced_diffusion[upper]
    return y0 + (mean_energy_eV - x0) * (y1 - y0) / (x1 - x0)


neutral_density = GAS_PRESSURE_PA / (BOLTZMANN_J_K * GAS_TEMPERATURE_K)
initial_expected_diffusion = (
    interp_reduced_diffusion(INITIAL_MEAN_ENERGY_EV) / neutral_density
)
diffusivities = [f(row, "electron_diffusion_avg") for row in rows]
if min(diffusivities) <= 0.0:
    raise SystemExit(
        f"table-derived electron diffusion must remain positive: {diffusivities}"
    )
if relative_error(diffusivities[0], initial_expected_diffusion) > 1.0e-10:
    raise SystemExit(
        "initial table-derived diffusion mismatch: "
        f"runtime={diffusivities[0]} expected={initial_expected_diffusion}"
    )

mins = [f(row, "electron_density_min") for row in rows]
maxs = [f(row, "electron_density_max") for row in rows]
if min(mins) <= 0.0:
    raise SystemExit(f"electron density became non-positive: {mins}")
if max(maxs) > INITIAL_NE_M3 * (1.0 + 1.0e-8):
    raise SystemExit(f"diffusion + wall loss produced a density overshoot: {maxs}")

particle_inventories = [f(row, "electron_inventory_mol") for row in rows]
energy_inventories = [f(row, "electron_energy_inventory_eV_mol") for row in rows]
if particle_inventories[-1] >= particle_inventories[0]:
    raise SystemExit(
        "thermal wall loss must reduce total electron inventory: "
        f"first={particle_inventories[0]} last={particle_inventories[-1]}"
    )
if energy_inventories[-1] >= energy_inventories[0]:
    raise SystemExit(
        "thermal energy wall loss must reduce total electron-energy inventory: "
        f"first={energy_inventories[0]} last={energy_inventories[-1]}"
    )

particle_wall_rates = [f(row, "electron_wall_particle_rate") for row in rows]
energy_wall_rates = [f(row, "electron_wall_energy_rate_eV_mol_s") for row in rows]
if not any(abs(value) > 0.0 for value in particle_wall_rates[1:]):
    raise SystemExit(f"thermal particle wall-loss flux was zero: {particle_wall_rates}")
if not any(abs(value) > 0.0 for value in energy_wall_rates[1:]):
    raise SystemExit(f"thermal energy wall-loss flux was zero: {energy_wall_rates}")

electron_temperature_eV = (2.0 / 3.0) * INITIAL_MEAN_ENERGY_EV
mean_speed_m_s = math.sqrt(
    8.0
    * ELEMENTARY_CHARGE_C
    * electron_temperature_eV
    / (math.pi * ELECTRON_MASS_KG)
)
expected_initial_particle_wall_rate = (
    0.25
    * INITIAL_NE_M3
    * mean_speed_m_s
    / AVOGADRO_PER_MOL
    * TOTAL_THERMAL_WALL_AREA_M2
)
if (
    relative_error(
        particle_wall_rates[0], expected_initial_particle_wall_rate
    )
    > 1.0e-10
):
    raise SystemExit(
        "thermal particle wall-loss law mismatch: "
        f"runtime={particle_wall_rates[0]} "
        f"expected={expected_initial_particle_wall_rate}"
    )

expected_initial_energy_wall_rate = (
    expected_initial_particle_wall_rate
    * EXPECTED_ENERGY_PER_PARTICLE_TE_FACTOR
    * electron_temperature_eV
)
if relative_error(energy_wall_rates[0], expected_initial_energy_wall_rate) > 1.0e-10:
    raise SystemExit(
        "thermal energy wall-loss law mismatch: "
        f"runtime={energy_wall_rates[0]} "
        f"expected={expected_initial_energy_wall_rate}"
    )

particle_balance_relative_errors = []
energy_balance_relative_errors = []
for index in range(1, len(rows)):
    dt = times[index] - times[index - 1]

    d_particle_dt = (
        particle_inventories[index] - particle_inventories[index - 1]
    ) / dt
    particle_residual = d_particle_dt + particle_wall_rates[index]
    particle_scale = max(abs(particle_wall_rates[index]), 1.0e-300)
    particle_balance_relative_errors.append(
        abs(particle_residual) / particle_scale
    )

    d_energy_dt = (
        energy_inventories[index] - energy_inventories[index - 1]
    ) / dt
    energy_residual = d_energy_dt + energy_wall_rates[index]
    energy_scale = max(abs(energy_wall_rates[index]), 1.0e-300)
    energy_balance_relative_errors.append(abs(energy_residual) / energy_scale)

if max(particle_balance_relative_errors) > 1.0e-8:
    raise SystemExit(
        "electron inventory/wall-flux conservation failed: "
        f"relative errors={particle_balance_relative_errors}"
    )
if max(energy_balance_relative_errors) > 1.0e-8:
    raise SystemExit(
        "electron-energy inventory/wall-flux conservation failed: "
        f"relative errors={energy_balance_relative_errors}"
    )

profiles = sorted(Path(".").glob("electron_diffusion_final_profile_*.csv"))
if not profiles:
    raise SystemExit("missing final element profile CSV")
with profiles[-1].open(newline="") as handle:
    profile = list(csv.DictReader(handle))
if not profile:
    raise SystemExit("final element profile is empty")

lookup_relative_errors = []
temperature_relation_errors = []
profile_energies = []
profile_temperatures = []
profile_diffusivities = []
for row in profile:
    mean_energy = float(row["mean_energy_out"])
    electron_temperature_eV = float(row["electron_temperature_eV"])
    diffusion = float(row["diffusion_out"])
    if not math.isfinite(mean_energy) or mean_energy <= 0.0:
        raise SystemExit(f"invalid profile mean energy: {mean_energy}")
    if not math.isfinite(electron_temperature_eV) or electron_temperature_eV <= 0.0:
        raise SystemExit(f"invalid profile electron temperature: {electron_temperature_eV}")
    if not math.isfinite(diffusion) or diffusion <= 0.0:
        raise SystemExit(f"invalid profile diffusivity: {diffusion}")
    expected_temperature_eV = (2.0 / 3.0) * mean_energy
    temperature_relation_errors.append(
        relative_error(electron_temperature_eV, expected_temperature_eV)
    )
    expected = interp_reduced_diffusion(mean_energy) / neutral_density
    lookup_relative_errors.append(relative_error(diffusion, expected))
    profile_energies.append(mean_energy)
    profile_temperatures.append(electron_temperature_eV)
    profile_diffusivities.append(diffusion)

if max(temperature_relation_errors) > 1.0e-12:
    raise SystemExit(
        "mean-energy -> electron-temperature conversion mismatch: "
        f"max_relative_error={max(temperature_relation_errors)}"
    )

if max(lookup_relative_errors) > 1.0e-9:
    raise SystemExit(
        "local mean-energy -> diffusivity lookup mismatch: "
        f"max_relative_error={max(lookup_relative_errors)}"
    )

if max(profile_energies) - min(profile_energies) <= 1.0e-8:
    raise SystemExit(
        "solved mean-energy field did not develop a resolvable spatial response: "
        f"range=[{min(profile_energies)}, {max(profile_energies)}]"
    )
if max(profile_diffusivities) - min(profile_diffusivities) <= 1.0e-8:
    raise SystemExit(
        "energy-dependent diffusivity did not develop a resolvable spatial response: "
        f"range=[{min(profile_diffusivities)}, {max(profile_diffusivities)}]"
    )


def profile_values(predicate):
    values = []
    for row in profile:
        r = float(row["x"])
        z = float(row["y"])
        if predicate(r, z):
            values.append(float(row["electron_density"]))
    if not values:
        raise SystemExit("profile-region selection produced no elements")
    return values


interior = profile_values(lambda r, z: 0.04 < r < 0.18 and 0.15 < z < 0.27)
outer_wall = profile_values(lambda r, z: r > 0.228 and 0.12 < z < 0.25)
wafer_wall = profile_values(lambda r, z: r < 0.12 and 0.099 < z < 0.108)

interior_mean = sum(interior) / len(interior)
outer_wall_mean = sum(outer_wall) / len(outer_wall)
wafer_wall_mean = sum(wafer_wall) / len(wafer_wall)
if interior_mean < 0.999 * INITIAL_NE_M3:
    raise SystemExit(f"interior depleted unexpectedly: mean={interior_mean}")
if outer_wall_mean > 0.98 * INITIAL_NE_M3:
    raise SystemExit(f"outer-wall thermal depletion missing: mean={outer_wall_mean}")
if wafer_wall_mean > 0.97 * INITIAL_NE_M3:
    raise SystemExit(f"wafer thermal depletion missing: mean={wafer_wall_mean}")

print("2D_ICP_ELECTRON_DIFFUSION_ENERGY_BASELINE=PASS")
print(f"ROWS={len(rows)}")
print(f"INITIAL_PARTICLE_INVENTORY_MOL={particle_inventories[0]:.17g}")
print(f"FINAL_PARTICLE_INVENTORY_MOL={particle_inventories[-1]:.17g}")
print(f"INITIAL_ENERGY_INVENTORY_EV_MOL={energy_inventories[0]:.17g}")
print(f"FINAL_ENERGY_INVENTORY_EV_MOL={energy_inventories[-1]:.17g}")
print(f"FINAL_NE_MIN_M3={mins[-1]:.17g}")
print(f"FINAL_NE_MAX_M3={maxs[-1]:.17g}")
print(f"FINAL_MEAN_ENERGY_AVG_EV={energies[-1]:.17g}")
print(f"FINAL_MEAN_ENERGY_MIN_EV={energy_mins[-1]:.17g}")
print(f"FINAL_MEAN_ENERGY_MAX_EV={energy_maxs[-1]:.17g}")
print(f"PROFILE_TE_MIN_EV={min(profile_temperatures):.17g}")
print(f"PROFILE_TE_MAX_EV={max(profile_temperatures):.17g}")
print(f"MAX_MEAN_ENERGY_TO_TE_REL_ERROR={max(temperature_relation_errors):.17g}")
print(f"INITIAL_DIFFUSION_M2_S={diffusivities[0]:.17g}")
print(f"FINAL_DIFFUSION_AVG_M2_S={diffusivities[-1]:.17g}")
print(f"PROFILE_DIFFUSION_MIN_M2_S={min(profile_diffusivities):.17g}")
print(f"PROFILE_DIFFUSION_MAX_M2_S={max(profile_diffusivities):.17g}")
print(f"MAX_LOCAL_LOOKUP_REL_ERROR={max(lookup_relative_errors):.17g}")
print(f"INITIAL_PARTICLE_WALL_RATE_MOL_S={particle_wall_rates[0]:.17g}")
print(f"INITIAL_ENERGY_WALL_RATE_EV_MOL_S={energy_wall_rates[0]:.17g}")
print(f"ENERGY_PER_PARTICLE_TE_FACTOR={EXPECTED_ENERGY_PER_PARTICLE_TE_FACTOR:.17g}")
print(
    "MAX_PARTICLE_BALANCE_REL_ERROR="
    f"{max(particle_balance_relative_errors):.17g}"
)
print(
    "MAX_ENERGY_BALANCE_REL_ERROR="
    f"{max(energy_balance_relative_errors):.17g}"
)
print(f"INTERIOR_NE_RATIO={interior_mean / INITIAL_NE_M3:.17g}")
print(f"OUTER_WALL_NE_RATIO={outer_wall_mean / INITIAL_NE_M3:.17g}")
print(f"WAFER_WALL_NE_RATIO={wafer_wall_mean / INITIAL_NE_M3:.17g}")
