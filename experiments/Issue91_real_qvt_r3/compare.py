#!/usr/bin/env python3
from __future__ import annotations

import csv
import math
import sys
from pathlib import Path


def last_row(path: Path) -> dict[str, str]:
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise SystemExit(f"empty CSV: {path}")
    return rows[-1]


def value(row: dict[str, str], key: str) -> float:
    try:
        result = float(row[key])
    except (KeyError, ValueError) as exc:
        raise SystemExit(f"missing/non-numeric {key}") from exc
    if not math.isfinite(result):
        raise SystemExit(f"non-finite {key}")
    return result


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        raise SystemExit("usage: compare.py <r3_e0_physical.csv> <r3_econst_physical.csv>")
    zero = last_row(Path(argv[0]))
    field = last_row(Path(argv[1]))
    deltas = [
        abs(value(zero, "n_e_min") - value(field, "n_e_min")),
        abs(value(zero, "n_e_max") - value(field, "n_e_max")),
    ]
    scale = max(
        abs(value(zero, "n_e_min")),
        abs(value(zero, "n_e_max")),
        abs(value(field, "n_e_min")),
        abs(value(field, "n_e_max")),
        1.0,
    )
    relative = max(deltas) / scale
    if relative <= 1.0e-10:
        print(f"ISSUE91_R3_FIELD_RESPONSE: FAIL relative_delta={relative:.6e}")
        return 1
    print(f"ISSUE91_R3_FIELD_RESPONSE: PASS relative_delta={relative:.6e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
