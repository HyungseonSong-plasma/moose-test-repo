#!/usr/bin/env python3
"""Validate the #26 P5/E7 bounded real-QVT chemistry-OFF integration oracle."""

from __future__ import annotations

import csv
import math
import sys
from pathlib import Path

TABLE_MIN_EV = 1.40991
TABLE_MAX_EV = 22.1378
INVENTORY_REL_TOL = 2.0e-6
NONTRIVIAL_ABS_TOL = 1.0e-8

REQUIRED = (
    "n_e_inventory",
    "n_epsilon_inventory",
    "n_e_min",
    "n_e_max",
    "n_epsilon_min",
    "n_epsilon_max",
    "mean_en_solved_min",
    "mean_en_solved_max",
    "electron_diffusion_avg",
    "electron_energy_diffusion_avg",
)


def value(row: dict[str, str], key: str) -> float:
    try:
        result = float(row[key])
    except (KeyError, ValueError) as exc:
        raise AssertionError(f"missing/non-numeric CSV field {key!r}") from exc
    assert math.isfinite(result), f"non-finite {key}={result}"
    return result


def relative_error(final: float, initial: float) -> float:
    assert initial != 0.0
    return abs(final - initial) / abs(initial)


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "electron_energy_real_qvt_inventory_smoke_out.csv")
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))

    assert len(rows) >= 3, f"expected INITIAL plus two TIMESTEP_END rows, got {len(rows)}"
    missing = [name for name in REQUIRED if name not in rows[0]]
    assert not missing, f"missing required output columns: {missing}"

    for index, row in enumerate(rows):
        ne_min = value(row, "n_e_min")
        neps_min = value(row, "n_epsilon_min")
        mean_min = value(row, "mean_en_solved_min")
        mean_max = value(row, "mean_en_solved_max")
        d_particle = value(row, "electron_diffusion_avg")
        d_energy = value(row, "electron_energy_diffusion_avg")

        assert ne_min > 0.0, f"row {index}: n_e_hat must stay > 0, got {ne_min}"
        assert neps_min >= 0.0, f"row {index}: n_epsilon_hat must stay >= 0, got {neps_min}"
        assert mean_min >= TABLE_MIN_EV, (
            f"row {index}: mean_en_solved below real-QVT table: {mean_min} < {TABLE_MIN_EV}"
        )
        assert mean_max <= TABLE_MAX_EV, (
            f"row {index}: mean_en_solved above real-QVT table: {mean_max} > {TABLE_MAX_EV}"
        )
        assert d_particle > 0.0, f"row {index}: electron diffusion must be positive"
        assert d_energy > 0.0, f"row {index}: electron-energy diffusion must be positive"

    initial = rows[0]
    final = rows[-1]

    particle_inventory_error = relative_error(
        value(final, "n_e_inventory"), value(initial, "n_e_inventory")
    )
    energy_inventory_error = relative_error(
        value(final, "n_epsilon_inventory"), value(initial, "n_epsilon_inventory")
    )
    assert particle_inventory_error <= INVENTORY_REL_TOL, (
        f"particle inventory relative error {particle_inventory_error:.6e} exceeds {INVENTORY_REL_TOL:.6e}"
    )
    assert energy_inventory_error <= INVENTORY_REL_TOL, (
        f"energy inventory relative error {energy_inventory_error:.6e} exceeds {INVENTORY_REL_TOL:.6e}"
    )

    particle_range_initial = value(initial, "n_e_max") - value(initial, "n_e_min")
    particle_range_final = value(final, "n_e_max") - value(final, "n_e_min")
    energy_range_initial = value(initial, "n_epsilon_max") - value(initial, "n_epsilon_min")
    energy_range_final = value(final, "n_epsilon_max") - value(final, "n_epsilon_min")

    assert particle_range_initial > NONTRIVIAL_ABS_TOL
    assert energy_range_initial > NONTRIVIAL_ABS_TOL
    assert particle_range_final < particle_range_initial - NONTRIVIAL_ABS_TOL, (
        "particle state did not exhibit nontrivial diffusive smoothing: "
        f"{particle_range_initial} -> {particle_range_final}"
    )
    assert energy_range_final < energy_range_initial - NONTRIVIAL_ABS_TOL, (
        "energy state did not exhibit nontrivial diffusive smoothing: "
        f"{energy_range_initial} -> {energy_range_final}"
    )

    print(f"QPX_E7_PARTICLE_INVENTORY_RELERR={particle_inventory_error:.16e}")
    print(f"QPX_E7_ENERGY_INVENTORY_RELERR={energy_inventory_error:.16e}")
    print(
        "QPX_E7_MEAN_ENERGY_RANGE="
        f"{value(final, 'mean_en_solved_min'):.16e},"
        f"{value(final, 'mean_en_solved_max'):.16e}"
    )
    print("QPX_E7_REAL_QVT_CHEMISTRY_OFF_INVENTORY_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
