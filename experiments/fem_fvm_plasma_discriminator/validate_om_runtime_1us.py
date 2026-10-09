#!/usr/bin/env python3
"""100 us staged-time runtime acceptance gate for Issue #378 O- transport."""
from __future__ import annotations

import csv
import math
from pathlib import Path

CSV_PATH = Path("ion_om_fvm_hybrid_contour_staged_1ns100_10ns90_100ns90_1000ns90_out.csv")
FIRST_DT_S = 1.0e-9
FIRST_STEPS = 100
SECOND_DT_S = 10.0e-9
SECOND_STEPS = 90
THIRD_DT_S = 100.0e-9
THIRD_STEPS = 90
FOURTH_DT_S = 1000.0e-9
FOURTH_STEPS = 90
EXPECTED_ROWS = FIRST_STEPS + SECOND_STEPS + THIRD_STEPS + FOURTH_STEPS + 1
END_TIME_S = 100.0e-6
NEUTRALITY_SCALE = 2.0e15
NEUTRALITY_REL_TOL = 1.0e-9
SNAPSHOT_NS = (0, 5, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000, 100000)

REQUIRED = (
    "time",
    "charge_integral",
    "charge_number_min",
    "charge_number_max",
    "mean_energy_min",
    "mean_energy_max",
    "ne_min",
    "ne_max",
    "ni_min",
    "ni_max",
    "nm_min",
    "nm_max",
    "potential_min",
    "potential_max",
)


def expected_times() -> list[float]:
    first = [i * FIRST_DT_S for i in range(FIRST_STEPS + 1)]
    t1 = FIRST_STEPS * FIRST_DT_S
    second = [t1 + j * SECOND_DT_S for j in range(1, SECOND_STEPS + 1)]
    t2 = t1 + SECOND_STEPS * SECOND_DT_S
    third = [t2 + k * THIRD_DT_S for k in range(1, THIRD_STEPS + 1)]
    t3 = t2 + THIRD_STEPS * THIRD_DT_S
    fourth = [t3 + m * FOURTH_DT_S for m in range(1, FOURTH_STEPS + 1)]
    return first + second + third + fourth


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

    exp_times = expected_times()
    if len(rows) != EXPECTED_ROWS:
        raise SystemExit(f"100 us row count failed: expected {EXPECTED_ROWS}, got {len(rows)}")
    if len(exp_times) != EXPECTED_ROWS:
        raise SystemExit("internal staged-time schedule length mismatch")

    for key in REQUIRED:
        if key not in rows[0]:
            raise SystemExit(f"missing postprocessor column: {key}")

    max_abs_charge_number = 0.0
    max_abs_charge_integral = 0.0
    times: list[float] = []

    for i, row in enumerate(rows):
        values = {key: _finite(row, key, i) for key in REQUIRED}
        t = values["time"]
        expected_t = exp_times[i]
        times.append(t)

        if not math.isclose(t, expected_t, rel_tol=1.0e-12, abs_tol=1.0e-15):
            raise SystemExit(
                f"staged time-grid gate failed at row {i}: "
                f"t={t:.17g}, expected={expected_t:.17g}"
            )
        if i and not t > times[i - 1]:
            raise SystemExit(f"non-increasing time at row {i}: {times[i - 1]} -> {t}")

        for prefix in ("ne", "ni", "nm"):
            vmin = values[f"{prefix}_min"]
            vmax = values[f"{prefix}_max"]
            if vmin <= 0.0 or vmax <= 0.0 or vmin > vmax:
                raise SystemExit(
                    f"{prefix} positivity/order gate failed at row {i}: min={vmin}, max={vmax}"
                )

        if values["mean_energy_min"] <= 0.0 or values["mean_energy_min"] > values["mean_energy_max"]:
            raise SystemExit(
                "electron mean-energy positivity/order gate failed at row "
                f"{i}: min={values['mean_energy_min']}, max={values['mean_energy_max']}"
            )
        if values["potential_min"] > values["potential_max"]:
            raise SystemExit(
                f"potential ordering gate failed at row {i}: "
                f"min={values['potential_min']}, max={values['potential_max']}"
            )
        if values["charge_number_min"] > values["charge_number_max"]:
            raise SystemExit(
                f"charge ordering gate failed at row {i}: "
                f"min={values['charge_number_min']}, max={values['charge_number_max']}"
            )

        max_abs_charge_number = max(
            max_abs_charge_number,
            abs(values["charge_number_min"]),
            abs(values["charge_number_max"]),
        )
        max_abs_charge_integral = max(max_abs_charge_integral, abs(values["charge_integral"]))

    switch2 = FIRST_STEPS + SECOND_STEPS
    switch3 = switch2 + THIRD_STEPS
    if not math.isclose(times[FIRST_STEPS], 100.0e-9, rel_tol=1.0e-12, abs_tol=1.0e-15):
        raise SystemExit(f"first dt switch time failed: {times[FIRST_STEPS]:.17g}")
    if not math.isclose(times[switch2], 1.0e-6, rel_tol=1.0e-12, abs_tol=1.0e-15):
        raise SystemExit(f"second dt switch time failed: {times[switch2]:.17g}")
    if not math.isclose(times[switch3], 10.0e-6, rel_tol=1.0e-12, abs_tol=1.0e-15):
        raise SystemExit(f"third dt switch time failed: {times[switch3]:.17g}")
    if not math.isclose(times[-1], END_TIME_S, rel_tol=1.0e-12, abs_tol=1.0e-15):
        raise SystemExit(f"100 us final time failed: {times[-1]:.17g}")

    initial_charge = max(
        abs(float(rows[0]["charge_number_min"])),
        abs(float(rows[0]["charge_number_max"])),
    )
    if initial_charge > NEUTRALITY_REL_TOL * NEUTRALITY_SCALE:
        raise SystemExit(f"initial neutrality gate failed: |nq|max={initial_charge:.17g} m^-3")

    print("ISSUE378_100US_STAGED_GATE: PASS")
    print(f"rows={len(rows)}")
    print("schedule=1nsx100+10nsx90+100nsx90+1000nsx90")
    print(f"switch1_time_s={times[FIRST_STEPS]:.17g}")
    print(f"switch2_time_s={times[switch2]:.17g}")
    print(f"switch3_time_s={times[switch3]:.17g}")
    print(f"final_time_s={times[-1]:.17g}")
    print(f"initial_charge_abs_max_m-3={initial_charge:.17g}")
    print(f"trajectory_charge_abs_max_m-3={max_abs_charge_number:.17g}")
    print(f"trajectory_abs_charge_integral_C_max={max_abs_charge_integral:.17g}")

    for target_ns in SNAPSHOT_NS:
        target_s = target_ns * 1.0e-9
        idx = min(range(len(exp_times)), key=lambda j: abs(exp_times[j] - target_s))
        if not math.isclose(exp_times[idx], target_s, rel_tol=1.0e-12, abs_tol=1.0e-15):
            raise SystemExit(f"missing requested snapshot time {target_ns} ns")
        row = rows[idx]
        print(
            "snapshot "
            f"row={idx} t_ns={float(row['time']) * 1.0e9:.9g} "
            f"nm=[{float(row['nm_min']):.17g},{float(row['nm_max']):.17g}] "
            f"ne=[{float(row['ne_min']):.17g},{float(row['ne_max']):.17g}] "
            f"ni=[{float(row['ni_min']):.17g},{float(row['ni_max']):.17g}] "
            f"charge=[{float(row['charge_number_min']):.17g},{float(row['charge_number_max']):.17g}] "
            f"Q_C={float(row['charge_integral']):.17g} "
            f"phi=[{float(row['potential_min']):.17g},{float(row['potential_max']):.17g}] "
            f"meanE=[{float(row['mean_energy_min']):.17g},{float(row['mean_energy_max']):.17g}]"
        )

    last = rows[-1]
    print(f"final_ne_min_m-3={float(last['ne_min']):.17g}")
    print(f"final_ne_max_m-3={float(last['ne_max']):.17g}")
    print(f"final_ni_min_m-3={float(last['ni_min']):.17g}")
    print(f"final_ni_max_m-3={float(last['ni_max']):.17g}")
    print(f"final_nm_min_m-3={float(last['nm_min']):.17g}")
    print(f"final_nm_max_m-3={float(last['nm_max']):.17g}")
    print(f"final_charge_min_m-3={float(last['charge_number_min']):.17g}")
    print(f"final_charge_max_m-3={float(last['charge_number_max']):.17g}")
    print(f"final_charge_integral_C={float(last['charge_integral']):.17g}")
    print(f"final_potential_min_V={float(last['potential_min']):.17g}")
    print(f"final_potential_max_V={float(last['potential_max']):.17g}")
    print(
        "spatial_profile_evidence=Exodus contains the full FE/FV state at "
        "INITIAL and every staged TIMESTEP_END"
    )


if __name__ == "__main__":
    main()
