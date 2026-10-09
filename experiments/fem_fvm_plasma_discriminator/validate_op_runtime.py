#!/usr/bin/env python3
"""300 ns runtime acceptance gate for Issue #331 Stage-A O+ drift-diffusion baseline."""
from __future__ import annotations

import csv
import math
from pathlib import Path

CSV_PATH = Path("ion_om_op_fvm_hybrid_contour_dt1ns_300steps_out.csv")
DT_S = 1.0e-9
EXPECTED_STEPS = 300
EXPECTED_ROWS = EXPECTED_STEPS + 1
END_TIME_S = DT_S * EXPECTED_STEPS
NEUTRALITY_SCALE = 2.0e15
NEUTRALITY_REL_TOL = 1.0e-9
SNAPSHOT_STEPS = (0, 5, 50, 100, 200, 300)

REQUIRED = ("time", "charge_integral", "charge_number_min", "charge_number_max", "mean_energy_min", "mean_energy_max", "ne_min", "ne_max", "ni_min", "ni_max", "nm_min", "nm_max", "nop_min", "nop_max", "potential_min", "potential_max")


def _finite(row: dict[str, str], key: str, index: int) -> float:
    try:
        value = float(row[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise SystemExit(f"invalid {key} at row {index}: {row.get(key)!r}") from exc
    if not math.isfinite(value):
        raise SystemExit(f"non-finite {key} at row {index}: {value}")
    return value


def main() -> None:
    if not CSV_PATH.exists():
        raise SystemExit(f"missing runtime CSV: {CSV_PATH}")
    with CSV_PATH.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != EXPECTED_ROWS:
        raise SystemExit(f"full-horizon row count failed: expected {EXPECTED_ROWS}, got {len(rows)}")
    for key in REQUIRED:
        if key not in rows[0]:
            raise SystemExit(f"missing postprocessor column: {key}")

    times = []
    max_abs_charge_number = 0.0
    max_abs_charge_integral = 0.0
    for i, row in enumerate(rows):
        values = {key: _finite(row, key, i) for key in REQUIRED}
        t = values["time"]
        times.append(t)
        expected_t = i * DT_S
        if not math.isclose(t, expected_t, rel_tol=1.0e-12, abs_tol=1.0e-15):
            raise SystemExit(f"time-grid gate failed at row {i}: t={t:.17g}, expected={expected_t:.17g}")
        if i and not t > times[i - 1]:
            raise SystemExit(f"non-increasing time at row {i}: {times[i - 1]} -> {t}")
        for prefix in ("ne", "ni", "nm", "nop"):
            vmin = values[f"{prefix}_min"]
            vmax = values[f"{prefix}_max"]
            if vmin <= 0.0 or vmax <= 0.0 or vmin > vmax:
                raise SystemExit(f"{prefix} positivity/order gate failed at row {i}: min={vmin}, max={vmax}")
        if values["mean_energy_min"] <= 0.0 or values["mean_energy_min"] > values["mean_energy_max"]:
            raise SystemExit(f"electron mean-energy positivity/order gate failed at row {i}: min={values['mean_energy_min']}, max={values['mean_energy_max']}")
        if values["potential_min"] > values["potential_max"]:
            raise SystemExit(f"potential ordering gate failed at row {i}: min={values['potential_min']}, max={values['potential_max']}")
        if values["charge_number_min"] > values["charge_number_max"]:
            raise SystemExit(f"charge ordering gate failed at row {i}: min={values['charge_number_min']}, max={values['charge_number_max']}")
        max_abs_charge_number = max(max_abs_charge_number, abs(values["charge_number_min"]), abs(values["charge_number_max"]))
        max_abs_charge_integral = max(max_abs_charge_integral, abs(values["charge_integral"]))

    if not math.isclose(times[-1], END_TIME_S, rel_tol=1.0e-12, abs_tol=1.0e-15):
        raise SystemExit(f"full-horizon final time failed: t={times[-1]:.17g}, expected={END_TIME_S:.17g}")
    initial_charge = max(abs(float(rows[0]["charge_number_min"])), abs(float(rows[0]["charge_number_max"])))
    if initial_charge > NEUTRALITY_REL_TOL * NEUTRALITY_SCALE:
        raise SystemExit(f"initial neutrality gate failed: |nq|max={initial_charge:.17g} m^-3")

    print("ISSUE331_STAGEA_OP_FULL_HORIZON_GATE: PASS")
    print(f"rows={len(rows)}")
    print(f"dt_s={DT_S:.17g}")
    print(f"final_time_s={times[-1]:.17g}")
    print(f"initial_charge_abs_max_m-3={initial_charge:.17g}")
    print(f"trajectory_charge_abs_max_m-3={max_abs_charge_number:.17g}")
    print(f"trajectory_abs_charge_integral_C_max={max_abs_charge_integral:.17g}")
    for step in SNAPSHOT_STEPS:
        row = rows[step]
        print("snapshot " f"step={step} t_ns={float(row['time']) * 1.0e9:.9g} " f"nm=[{float(row['nm_min']):.17g},{float(row['nm_max']):.17g}] " f"nop=[{float(row['nop_min']):.17g},{float(row['nop_max']):.17g}] " f"ne=[{float(row['ne_min']):.17g},{float(row['ne_max']):.17g}] " f"ni=[{float(row['ni_min']):.17g},{float(row['ni_max']):.17g}] " f"charge=[{float(row['charge_number_min']):.17g},{float(row['charge_number_max']):.17g}] " f"Q_C={float(row['charge_integral']):.17g} " f"phi=[{float(row['potential_min']):.17g},{float(row['potential_max']):.17g}] " f"meanE=[{float(row['mean_energy_min']):.17g},{float(row['mean_energy_max']):.17g}]")

    last = rows[-1]
    print(f"final_nop_min_m-3={float(last['nop_min']):.17g}")
    print(f"final_nop_max_m-3={float(last['nop_max']):.17g}")
    print(f"final_nm_min_m-3={float(last['nm_min']):.17g}")
    print(f"final_nm_max_m-3={float(last['nm_max']):.17g}")
    print(f"final_charge_min_m-3={float(last['charge_number_min']):.17g}")
    print(f"final_charge_max_m-3={float(last['charge_number_max']):.17g}")
    print(f"final_charge_integral_C={float(last['charge_integral']):.17g}")
    print(f"final_potential_min_V={float(last['potential_min']):.17g}")
    print(f"final_potential_max_V={float(last['potential_max']):.17g}")
    print("spatial_profile_evidence=Exodus contains the full FE/FV state at INITIAL and every TIMESTEP_END")


if __name__ == "__main__":
    main()
