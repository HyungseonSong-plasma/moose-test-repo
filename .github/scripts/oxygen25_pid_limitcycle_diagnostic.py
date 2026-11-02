#!/usr/bin/env python3
"""Post-run RF feedback saturation, periodicity and response-lag evidence.

Diagnostic only. Correlation does not prove causation or timestep convergence.
Stage6 1–10ms remains HOLD. No native solver state is modified.
"""
from __future__ import annotations
import argparse
import csv
import json
import math
import statistics
from pathlib import Path

TARGET_W = 1000.0
RF = "P_rf_raw_W_t6"
DRIVE = "rf_drive_scale_t6"
CLAMP = 3.0
LATE_START = 0.0005
END = 0.001


def read_native(path: Path) -> list[dict[str, float]]:
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        required = {"time", RF, DRIVE}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("missing native monitors")
        rows = [{k: float(row[k]) for k in required} for row in reader]
    if len(rows) < 20 or any(not math.isfinite(v) for r in rows for v in r.values()):
        raise ValueError("missing/nonfinite native history")
    if any(b["time"] <= a["time"] for a, b in zip(rows, rows[1:])):
        raise ValueError("nonmonotonic native time")
    if not math.isclose(rows[-1]["time"], END, abs_tol=1e-15, rel_tol=0):
        raise ValueError("run has not reached 1ms")
    if any(r[RF] <= 0 or not 0 < r[DRIVE] <= CLAMP + 1e-6 for r in rows):
        raise ValueError("invalid RF or drive scale")
    return rows


def _cycles(t: list[float], power: list[float]) -> dict:
    # Local extrema filtered by >=10% of nominal RF power prominence.
    extrema = []
    for i in range(1, len(power)-1):
        if power[i] > power[i-1] and power[i] >= power[i+1]:
            extrema.append(("peak", i))
        elif power[i] < power[i-1] and power[i] <= power[i+1]:
            extrema.append(("trough", i))
    cleaned = []
    for kind, i in extrema:
        if cleaned and cleaned[-1][0] == kind:
            j = cleaned[-1][1]
            if (kind == "peak" and power[i] > power[j]) or (kind == "trough" and power[i] < power[j]):
                cleaned[-1] = (kind, i)
        else:
            cleaned.append((kind, i))
    pairs = [(i, j) for (a, i), (b, j) in zip(cleaned, cleaned[1:])
             if a == "peak" and b == "trough" and power[i] - power[j] >= 0.1 * TARGET_W]
    peak_times = [t[i] for i, _ in pairs]
    periods = [(b-a)*1e6 for a, b in zip(peak_times, peak_times[1:])]
    return {
        "prominent_peak_trough_count": len(pairs),
        "events": [{"peak_us": t[i]*1e6, "trough_us": t[j]*1e6,
                    "drop_w": power[i]-power[j]} for i, j in pairs],
        "peak_periods_us": periods,
        "median_period_us": statistics.median(periods) if len(periods) >= 2 else None,
        "period_status": "ESTIMATED" if len(periods) >= 2 else "INSUFFICIENT_CYCLES",
    }


def _corr(a: list[float], b: list[float]) -> float | None:
    if len(a) < 6:
        return None
    ma, mb = statistics.mean(a), statistics.mean(b)
    x, y = [v-ma for v in a], [v-mb for v in b]
    denom = math.sqrt(sum(v*v for v in x)*sum(v*v for v in y))
    return sum(u*v for u, v in zip(x, y))/denom if denom > 1e-24 else None


def diagnose(rows: list[dict[str, float]], dtmax_us: float) -> dict:
    late = [r for r in rows if LATE_START - 1e-15 <= r["time"] <= END + 1e-15]
    if len(late) < 12 or late[0]["time"] > LATE_START + dtmax_us*1e-6*1.1:
        raise ValueError("late native history insufficient")
    t, p, drive = ([r[key] for r in late] for key in ("time", RF, DRIVE))
    dt = [b-a for a, b in zip(t, t[1:])]
    if max(dt) > dtmax_us*1e-6*1.01:
        raise ValueError("native output spacing exceeds expected dtmax")
    sat = [v >= CLAMP-1e-8 for v in drive]
    saturated_time = sum(step for step, flag in zip(dt, sat[1:]) if flag)
    lagged = []
    for lag in range(min(8, len(p)-8)):
        errors, delta_drive = [], []
        for i in range(len(p)-lag-1):
            j = i+lag
            if sat[j] or sat[j+1]:
                continue
            errors.append(p[i]-TARGET_W)
            delta_drive.append(drive[j+1]-drive[j])
        lagged.append({"lag_samples": lag, "pairs": len(errors),
                       "correlation": _corr(errors, delta_drive)})
    usable = [r for r in lagged if r["correlation"] is not None]
    return {
        "scientific_decision": "HOLD_STAGE6",
        "power_target_w": TARGET_W,
        "dtmax_us": dtmax_us,
        "late_window_us": [500, 1000],
        "late_rows": len(late),
        "observed_dt_min_us": min(dt)*1e6,
        "observed_dt_max_us": max(dt)*1e6,
        "rf_min_w": min(p),
        "rf_max_w": max(p),
        "rf_mean_w": statistics.mean(p),
        "rf_peak_to_peak_percent_nominal": 100*(max(p)-min(p))/TARGET_W,
        "rf_rms_error_percent_nominal": 100*math.sqrt(
            statistics.mean((v-TARGET_W)**2 for v in p))/TARGET_W,
        "drive_min": min(drive),
        "drive_max": max(drive),
        "upper_clamp_sample_count": sum(sat),
        "upper_clamp_sample_fraction": sum(sat)/len(sat),
        "upper_clamp_time_fraction_estimate": saturated_time/(t[-1]-t[0]),
        "rf_oscillation": _cycles(t, p),
        "rf_error_vs_later_drive_increment_correlation": lagged,
        "strongest_abs_correlation": max(usable, key=lambda r: abs(r["correlation"])) if usable else None,
        "limitations": "No PID/Maxwell causality, timestep convergence, or Stage6 authorization follows from these diagnostics.",
    }


def self_test() -> None:
    rows = []
    for i in range(201):
        t = i*5e-6
        rf = 1000+300*math.sin(2*math.pi*t/80e-6)
        rows.append({"time": t, RF: rf, DRIVE: min(3.0, 2.9-0.0005*(rf-1000))})
    result = diagnose(rows, 5)
    assert result["scientific_decision"] == "HOLD_STAGE6"
    assert result["rf_oscillation"]["period_status"] == "ESTIMATED"
    assert abs(result["rf_oscillation"]["median_period_us"]-80) < 1e-6
    assert result["upper_clamp_sample_count"] > 0
    assert result["rf_peak_to_peak_percent_nominal"] > 50
    print("OXYGEN25_PID_LIMITCYCLE_DIAGNOSTIC_SELFTEST_PASS")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--csv", type=Path)
    p.add_argument("--output-json", type=Path)
    p.add_argument("--dtmax-us", type=float, choices=(5.0, 10.0))
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()
    if args.self_test:
        self_test()
        return
    if args.csv is None or args.output_json is None or args.dtmax_us is None:
        p.error("require --csv, --output-json, --dtmax-us")
    result = diagnose(read_native(args.csv), args.dtmax_us)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, indent=2, sort_keys=True)+"\n")
    print("OXYGEN25_PID_LIMITCYCLE_DIAGNOSTIC", json.dumps({
        "rf_pp_pct": result["rf_peak_to_peak_percent_nominal"],
        "saturation_fraction": result["upper_clamp_sample_fraction"],
        "period_us": result["rf_oscillation"]["median_period_us"],
        "decision": result["scientific_decision"],
    }), flush=True)


if __name__ == "__main__":
    main()
