#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

SPECIES = ("O2s", "O2p", "O", "Om", "Op", "Os")


def read_last(path: Path) -> dict[str, str]:
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise AssertionError(f"empty physical CSV: {path}")
    return rows[-1]


def number(row: dict[str, str], key: str) -> float:
    value = float(row[key])
    if not math.isfinite(value):
        raise AssertionError(f"non-finite {key}={value}")
    return value


def relerr(value: float, reference: float) -> float:
    return abs(value - reference) / max(abs(reference), 1.0e-300)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        raise SystemExit("usage: check.py <physical.csv> <expected.json>")
    final = read_last(Path(argv[0]))
    expected = json.loads(Path(argv[1]).read_text())

    assert number(final, "time") > 1.0e-15

    n0 = float(expected["n0"])
    inv = number(final, "n_e_inventory")
    volume = number(final, "domain_volume")
    inv_rel = relerr(inv, n0 * volume)
    assert inv_rel <= float(expected["inventory_rel_tol"]), inv_rel

    ne_min = number(final, "n_e_min")
    ne_max = number(final, "n_e_max")
    ne_avg = number(final, "n_e_avg")
    assert ne_min >= 0.0 and ne_max >= ne_min
    assert relerr(ne_avg, n0) <= max(float(expected["inventory_rel_tol"]) * 5.0, 2.0e-8)
    assert number(final, "electron_mobility_avg") > 0.0
    assert number(final, "electron_diffusion_avg") > 0.0
    assert number(final, "electron_pressure_avg") > 0.0
    assert number(final, "electron_gas_temperature_avg") > 0.0

    sum_tol = float(expected["sum_w_tol"])
    assert abs(number(final, "sum_w_min") - 1.0) <= sum_tol
    assert abs(number(final, "sum_w_max") - 1.0) <= sum_tol
    bound_tol = float(expected["species_bound_tol"])
    for species in SPECIES:
        low = number(final, f"w_{species}_min")
        high = number(final, f"w_{species}_max")
        assert low >= -bound_tol, (species, low)
        assert high <= 1.0 + bound_tol, (species, high)
        assert high >= low, (species, low, high)

    print(f"ISSUE91_R3_CASE: PASS inventory_rel={inv_rel:.6e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
