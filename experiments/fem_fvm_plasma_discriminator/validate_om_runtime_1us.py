#!/usr/bin/env python3
"""1 us staged-time runtime acceptance gate for Issue #378 O- transport."""
from __future__ import annotations

import csv
import math
from pathlib import Path

CSV_PATH = Path("ion_om_fvm_hybrid_contour_staged_1ns100_5ns100_10ns40_out.csv")
FIRST_DT_S = 1.0e-9
FIRST_STEPS = 100
SECOND_DT_S = 5.0e-9
SECOND_STEPS = 100
THIRD_DT_S = 10.0e-9
THIRD_STEPS = 40
EXPECTED_ROWS = FIRST_STEPS + SECOND_STEPS + THIRD_STEPS + 1
END_TIME_S = 1.0e-6
NEUTRALITY_SCALE = 2.0e15
NEUTRALITY_REL_TOL = 1.0e-9
SNAPSHOT_NS = (0, 5, 50, 100, 200, 300, 500, 600, 800, 1000)

REQUIRED = (
    "time",
    "ne_min",
    "ne_max",
    "ni_min",
    "ni_max",
    "nm_min",
    "nm_max",
    "mean_energy_min",
    "mean_energy_max",
    "potential_min",
    "potential_max",
    "charge_number_min",
    "charge_number_max",
    "charge_integral",
)


def expected_times() -> list[float]:
    first = [i * FIRST_DT_S for i in range(FIRST_STEPS + 1)]
    t1 = FIRST_STEPS * FIRST_DT_S
    second = [t1 + j * SECOND_DT_S for j in range(1, SECOND_STEPS + 1)]
    t2 = t1 + SECOND_STEPS * SECOND_DT_S
    third = [t2 + k * THIRD_DT_S for k in range(1, THIRD_STEPS + 1)]
    return first + second + third


def _finite(row: dict[str, str], key: str, index: int) -> float:
    try:
        value = float(row[key])
    except (KeyError, ValueError) as exc:
        raise SystemExit(f"row {index}: invalid {key}: {exc}") from exc
    if not math.isfinite(value):
        raise SystemExit(f"row {index}: non-finite {key}={value}")
    return value


def main() -> None:
    if not CSV_PATH.exists():
        raise SystemExit(f"missing runtime CSV: {CSV_PATH}")

    with CSV_PATH.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise SystemExit("runtime CSV has no header")
        missing = [key for key in REQUIRED if key not in reader.fieldnames]
        if missing:
            raise SystemExit(f"runtime CSV missing columns: {missing}")
        rows = list(reader)

    exp_times = expected_times()
    if len(rows) != EXPECTED_ROWS:
        raise SystemExit(f"1 us row count failed: expected {EXPECTED_ROWS}, got {len(rows)}")
    if len(exp_times) != EXPECTED_ROWS:
        raise SystemExit("internal staged-time schedule length mismatch")

    times: list[float] = []
    max_abs_charge_number = 0.0
    max_abs_charge_integral = 0.0
    snapshots: dict[int, dict[str, float]] = {}

    for index, row in enumerate(rows):
        values = {key: _finite(row, key, index) for key in REQUIRED}
        t = values["time"]
        expected = exp_times[index]
        if not math.isclose(t, expected, rel_tol=1.0e-12, abs_tol=1.0e-15):
            raise SystemExit(
                f"row {index}: staged time mismatch: observed={t:.17g}, expected={expected:.17g}"
            )
        times.append(t)

        for prefix in ("ne", "ni", "nm"):
            lo = values[f"{prefix}_min"]
            hi = values[f"{prefix}_max"]
            if lo <= 0.0 or hi <= 0.0:
                raise SystemExit(f"row {index}: {prefix} lost strict positivity: min={lo}, max={hi}")
            if lo > hi:
                raise SystemExit(f"row {index}: {prefix} ordering failed: min={lo}, max={hi}")

        elo = values["mean_energy_min"]
        ehi = values["mean_energy_max"]
        if elo <= 0.0 or ehi <= 0.0 or elo > ehi:
            raise SystemExit(f"row {index}: mean electron energy invalid: min={elo}, max={ehi}")

        if values["potential_min"] > values["potential_max"]:
            raise SystemExit(f"row {index}: potential ordering failed")
        if values["charge_number_min"] > values["charge_number_max"]:
            raise SystemExit(f"row {index}: charge ordering failed")

        max_abs_charge_number = max(
            max_abs_charge_number,
            abs(values["charge_number_min"]),
            abs(values["charge_number_max"]),
        )
        max_abs_charge_integral = max(max_abs_charge_integral, abs(values["charge_integral"]))

        t_ns = int(round(t * 1.0e9))
        if t_ns in SNAPSHOT_NS:
            snapshots[t_ns] = values

    second_switch_index = FIRST_STEPS + SECOND_STEPS
    if not math.isclose(times[FIRST_STEPS], 100.0e-9, rel_tol=1.0e-12, abs_tol=1.0e-15):
        raise SystemExit(f"first dt switch time failed: {times[FIRST_STEPS]:.17g}")
    if not math.isclose(times[second_switch_index], 600.0e-9, rel_tol=1.0e-12, abs_tol=1.0e-15):
        raise SystemExit(f"second dt switch time failed: {times[second_switch_index]:.17g}")
    if not math.isclose(times[-1], END_TIME_S, rel_tol=1.0e-12, abs_tol=1.0e-15):
        raise SystemExit(f"1 us final time failed: {times[-1]:.17g}")

    initial_charge = max(
        abs(float(rows[0]["charge_number_min"])),
        abs(float(rows[0]["charge_number_max"])),
    )
    if initial_charge > NEUTRALITY_REL_TOL * NEUTRALITY_SCALE:
        raise SystemExit(f"initial neutrality gate failed: |nq|max={initial_charge:.17g} m^-3")

    print("ISSUE378_1US_STAGED_GATE: PASS")
    print(f"rows={len(rows)}")
    print("schedule=1nsx100+5nsx100+10nsx40")
    print(f"switch1_time_s={times[FIRST_STEPS]:.17g}")
    print(f"switch2_time_s={times[second_switch_index]:.17g}")
    print(f"final_time_s={times[-1]:.17g}")
    print(f"initial_charge_abs_max_m-3={initial_charge:.17g}")
    print(f"trajectory_charge_abs_max_m-3={max_abs_charge_number:.17g}")
    print(f"trajectory_abs_charge_integral_C_max={max_abs_charge_integral:.17g}")

    for t_ns in SNAPSHOT_NS:
        if t_ns not in snapshots:
            raise SystemExit(f"missing requested snapshot at {t_ns} ns")
        v = snapshots[t_ns]
        print(
            "snapshot "
            f"t_ns={t_ns} "
            f"ne=[{v['ne_min']:.17g},{v['ne_max']:.17g}] "
            f"ni=[{v['ni_min']:.17g},{v['ni_max']:.17g}] "
            f"nm=[{v['nm_min']:.17g},{v['nm_max']:.17g}] "
            f"charge=[{v['charge_number_min']:.17g},{v['charge_number_max']:.17g}] "
            f"Q_C={v['charge_integral']:.17g} "
            f"phi=[{v['potential_min']:.17g},{v['potential_max']:.17g}] "
            f"meanE=[{v['mean_energy_min']:.17g},{v['mean_energy_max']:.17g}]"
        )


if __name__ == "__main__":
    main()
