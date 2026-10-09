#!/usr/bin/env python3
"""Runtime acceptance gate for the Issue #378 O- contour discriminator."""
from __future__ import annotations

import csv
import math
from pathlib import Path

CSV_PATH = Path("ion_om_fvm_hybrid_contour_dt1ns_300steps_out.csv")
NEUTRALITY_SCALE = 2.0e15
NEUTRALITY_REL_TOL = 1.0e-9


def main() -> None:
    if not CSV_PATH.exists():
        raise SystemExit(f"missing runtime CSV: {CSV_PATH}")

    with CSV_PATH.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    if len(rows) < 2:
        raise SystemExit(f"expected INITIAL + transient rows, got {len(rows)}")

    required = ("nm_min", "nm_max", "charge_number_min", "charge_number_max")
    for key in required:
        if key not in rows[0]:
            raise SystemExit(f"missing postprocessor column: {key}")
        for i, row in enumerate(rows):
            value = float(row[key])
            if not math.isfinite(value):
                raise SystemExit(f"non-finite {key} at row {i}: {value}")

    initial_charge = max(
        abs(float(rows[0]["charge_number_min"])),
        abs(float(rows[0]["charge_number_max"])),
    )
    if initial_charge > NEUTRALITY_REL_TOL * NEUTRALITY_SCALE:
        raise SystemExit(
            f"initial neutrality gate failed: |nq|max={initial_charge:.17g} m^-3"
        )

    for i, row in enumerate(rows):
        nmin = float(row["nm_min"])
        nmax = float(row["nm_max"])
        if nmin <= 0.0 or nmax <= 0.0 or nmin > nmax:
            raise SystemExit(
                f"O- positivity/order gate failed at row {i}: min={nmin}, max={nmax}"
            )

    last = rows[-1]
    print("ISSUE378_RUNTIME_GATE: PASS")
    print(f"rows={len(rows)}")
    print(f"initial_charge_abs_max_m-3={initial_charge:.17g}")
    print(f"final_nm_min_m-3={float(last['nm_min']):.17g}")
    print(f"final_nm_max_m-3={float(last['nm_max']):.17g}")
    print(f"final_charge_min_m-3={float(last['charge_number_min']):.17g}")
    print(f"final_charge_max_m-3={float(last['charge_number_max']):.17g}")


if __name__ == "__main__":
    main()
