#!/usr/bin/env python3
"""Physics invariants for the reusable 2-D ICP electron diffusion baseline."""
from __future__ import annotations

import csv
import math
from pathlib import Path

MEAN_ENERGY_EV = 5.73276
INITIAL_NE_M3 = 1.0e16
GAS_PRESSURE_PA = 1.333223684
GAS_TEMPERATURE_K = 300.0
BOLTZMANN_J_K = 1.380649e-23
ELEMENTARY_CHARGE_C = 1.602176634e-19
ELECTRON_MASS_KG = 9.1093837139e-31
AVOGADRO_PER_MOL = 6.02214076e23
TOTAL_THERMAL_WALL_AREA_M2 = 0.9023470915199818
EXPECTED_DT_S = 1.0e-9

path = Path("electron_diffusion.csv")
if not path.is_file():
    raise SystemExit(f"missing runtime CSV: {path}")

with path.open(newline="") as handle:
    rows = list(csv.DictReader(handle))

if len(rows) != 5:
    raise SystemExit(f"expected initialization + four physical timesteps; got {len(rows)} rows")

required = {
    "time",
    "electron_inventory_mol",
    "electron_density_avg",
    "electron_density_min",
    "electron_density_max",
    "mean_energy_avg_eV",
    "electron_diffusion_avg",
    "electron_wall_particle_rate",
}
missing = required - set(rows[0])
if missing:
    raise SystemExit(f"missing expected columns: {sorted(missing)}")

def f(row, key):
    value = float(row[key])
    if not math.isfinite(value):
        raise SystemExit(f"non-finite {key}: {value}")
    return value

times = [f(row, "time") for row in rows]
expected_times = [0.0, 1.0e-9, 2.0e-9, 3.0e-9, 4.0e-9]
if any(abs(a - b) > 1.0e-15 for a, b in zip(times, expected_times)):
    raise SystemExit(f"unexpected runtime time grid: {times}")

energies = [f(row, "mean_energy_avg_eV") for row in rows]
if max(abs(value - MEAN_ENERGY_EV) for value in energies) > 1.0e-9:
    raise SystemExit(f"fixed mean-energy invariant failed: {energies}")

diffusivities = [f(row, "electron_diffusion_avg") for row in rows]
if min(diffusivities) <= 0.0:
    raise SystemExit(f"table-derived electron diffusion must remain positive: {diffusivities}")
spread = max(diffusivities) - min(diffusivities)
if spread > 1.0e-10 * max(diffusivities):
    raise SystemExit(
        "fixed-energy/table-derived diffusivity should be spatially/time constant: "
        f"{diffusivities}"
    )

table = Path("electron_moments.txt")
if not table.is_file():
    raise SystemExit(f"missing transport table: {table}")
reduced_diffusion = None
for raw in table.read_text().splitlines():
    fields = raw.split()
    if len(fields) < 3:
        continue
    try:
        energy, _reduced_mobility, candidate = map(float, fields[:3])
    except ValueError:
        continue
    if abs(energy - MEAN_ENERGY_EV) < 1.0e-12:
        reduced_diffusion = candidate
        break
if reduced_diffusion is None:
    raise SystemExit(f"transport table has no exact {MEAN_ENERGY_EV} eV row")

neutral_density = GAS_PRESSURE_PA / (BOLTZMANN_J_K * GAS_TEMPERATURE_K)
expected_diffusion = reduced_diffusion / neutral_density
if abs(diffusivities[-1] - expected_diffusion) > 1.0e-10 * expected_diffusion:
    raise SystemExit(
        f"table-derived diffusion mismatch: runtime={diffusivities[-1]} "
        f"expected={expected_diffusion}"
    )

mins = [f(row, "electron_density_min") for row in rows]
maxs = [f(row, "electron_density_max") for row in rows]
if min(mins) <= 0.0:
    raise SystemExit(f"electron density became non-positive: {mins}")
if max(maxs) > INITIAL_NE_M3 * (1.0 + 1.0e-8):
    raise SystemExit(f"diffusion + wall loss produced a density overshoot: {maxs}")

inventories = [f(row, "electron_inventory_mol") for row in rows]
if inventories[-1] >= inventories[0]:
    raise SystemExit(
        f"thermal wall loss must reduce total electron inventory: "
        f"first={inventories[0]} last={inventories[-1]}"
    )

all_wall_rates = [f(row, "electron_wall_particle_rate") for row in rows]
if not any(abs(value) > 0.0 for value in all_wall_rates[1:]):
    raise SystemExit(f"thermal wall-loss flux was identically zero: {all_wall_rates}")

electron_temperature_eV = (2.0 / 3.0) * MEAN_ENERGY_EV
mean_speed_m_s = math.sqrt(
    8.0 * ELEMENTARY_CHARGE_C * electron_temperature_eV
    / (math.pi * ELECTRON_MASS_KG)
)
expected_initial_wall_rate = (
    0.25 * INITIAL_NE_M3 * mean_speed_m_s / AVOGADRO_PER_MOL
    * TOTAL_THERMAL_WALL_AREA_M2
)
if abs(all_wall_rates[0] - expected_initial_wall_rate) > 1.0e-10 * expected_initial_wall_rate:
    raise SystemExit(
        f"thermal wall-loss law mismatch: runtime={all_wall_rates[0]} "
        f"expected={expected_initial_wall_rate}"
    )

balance_relative_errors = []
for index in range(1, len(rows)):
    dt = times[index] - times[index - 1]
    d_inventory_dt = (inventories[index] - inventories[index - 1]) / dt
    residual = d_inventory_dt + all_wall_rates[index]
    scale = max(abs(all_wall_rates[index]), 1.0e-300)
    balance_relative_errors.append(abs(residual) / scale)
if max(balance_relative_errors) > 1.0e-8:
    raise SystemExit(
        "electron inventory/wall-flux conservation failed: "
        f"relative errors={balance_relative_errors}"
    )

profiles = sorted(Path(".").glob("electron_diffusion_final_profile_*.csv"))
if not profiles:
    raise SystemExit("missing final element profile CSV")
with profiles[-1].open(newline="") as handle:
    profile = list(csv.DictReader(handle))

def profile_values(predicate):
    values = []
    for row in profile:
        r = float(row["x"])
        z = float(row["y"])
        if predicate(r, z):
            values.append(float(row["electron_density_out"]))
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

print("2D_ICP_ELECTRON_DIFFUSION_BASELINE=PASS")
print(f"ROWS={len(rows)}")
print(f"INITIAL_INVENTORY_MOL={inventories[0]:.17g}")
print(f"FINAL_INVENTORY_MOL={inventories[-1]:.17g}")
print(f"FINAL_NE_MIN_M3={mins[-1]:.17g}")
print(f"FINAL_NE_MAX_M3={maxs[-1]:.17g}")
print(f"DIFFUSION_M2_S={diffusivities[-1]:.17g}")
print(f"EXPECTED_DIFFUSION_M2_S={expected_diffusion:.17g}")
print(f"INITIAL_WALL_RATE_MOL_S={all_wall_rates[0]:.17g}")
print(f"EXPECTED_INITIAL_WALL_RATE_MOL_S={expected_initial_wall_rate:.17g}")
print(f"MAX_INVENTORY_BALANCE_REL_ERROR={max(balance_relative_errors):.17g}")
print(f"INTERIOR_NE_RATIO={interior_mean / INITIAL_NE_M3:.17g}")
print(f"OUTER_WALL_NE_RATIO={outer_wall_mean / INITIAL_NE_M3:.17g}")
print(f"WAFER_WALL_NE_RATIO={wafer_wall_mean / INITIAL_NE_M3:.17g}")
print(f"MEAN_ENERGY_EV={energies[-1]:.17g}")
