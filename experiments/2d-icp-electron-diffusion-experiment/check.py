#!/usr/bin/env python3
"""Invariant checker for the reusable 2-D ICP electron diffusion baseline."""
from __future__ import annotations

import csv
import math
from pathlib import Path

MEAN_ENERGY_EV = 5.73276
INITIAL_NE_M3 = 1.0e16

path = Path("electron_diffusion.csv")
if not path.is_file():
    raise SystemExit(f"missing runtime CSV: {path}")

with path.open(newline="") as handle:
    rows = list(csv.DictReader(handle))

if len(rows) < 2:
    raise SystemExit("expected initialization plus at least one physical timestep")

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
if any(b < a for a, b in zip(times, times[1:])):
    raise SystemExit("time is not monotone")

energies = [f(row, "mean_energy_avg_eV") for row in rows]
if max(abs(value - MEAN_ENERGY_EV) for value in energies) > 1.0e-9:
    raise SystemExit(f"fixed mean-energy invariant failed: {energies}")

diffusivities = [f(row, "electron_diffusion_avg") for row in rows]
if min(diffusivities) <= 0.0:
    raise SystemExit(f"table-derived electron diffusion must remain positive: {diffusivities}")
spread = max(diffusivities) - min(diffusivities)
if spread > 1.0e-10 * max(diffusivities):
    raise SystemExit(f"fixed-energy/table-derived diffusivity should be spatially/time constant: {diffusivities}")

mins = [f(row, "electron_density_min") for row in rows]
maxs = [f(row, "electron_density_max") for row in rows]
if min(mins) <= 0.0:
    raise SystemExit(f"electron density became non-positive: {mins}")
if max(maxs) > INITIAL_NE_M3 * (1.0 + 1.0e-8):
    raise SystemExit(f"diffusion + wall loss produced an unexpected density overshoot: {maxs}")

inventories = [f(row, "electron_inventory_mol") for row in rows]
if inventories[-1] >= inventories[0]:
    raise SystemExit(
        f"thermal wall loss must reduce total electron inventory: first={inventories[0]} last={inventories[-1]}"
    )

wall_rates = [f(row, "electron_wall_particle_rate") for row in rows[1:]]
if not any(abs(value) > 0.0 for value in wall_rates):
    raise SystemExit(f"thermal wall-loss flux was identically zero: {wall_rates}")

print("2D_ICP_ELECTRON_DIFFUSION_BASELINE=PASS")
print(f"ROWS={len(rows)}")
print(f"INITIAL_INVENTORY_MOL={inventories[0]:.17g}")
print(f"FINAL_INVENTORY_MOL={inventories[-1]:.17g}")
print(f"FINAL_NE_MIN_M3={mins[-1]:.17g}")
print(f"FINAL_NE_MAX_M3={maxs[-1]:.17g}")
print(f"DIFFUSION_M2_S={diffusivities[-1]:.17g}")
print(f"MEAN_ENERGY_EV={energies[-1]:.17g}")
