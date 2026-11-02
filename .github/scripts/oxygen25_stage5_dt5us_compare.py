#!/usr/bin/env python3
"""Evidence-only 1000W 10us-vs-5us adaptive dt sensitivity analysis.

This comparison never certifies 100us dtmax or starts Stage6. The raw RF
power and PID output are evaluated alongside all four neutral densities.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import json
import math
from pathlib import Path
import statistics
import tempfile

FIELDS = {
    "O2(X)": "n_O2_X_avg",
    "O2(a1Delta)": "n_O2_a_avg",
    "O(3P)": "n_O_3P_avg",
    "O(1D)": "n_O_1D_avg",
}
RF = "P_rf_raw_W_t6"
DRIVE = "rf_drive_scale_t6"
START_S = 1e-4
END_S = 1e-3
LATE_S = 5e-4
TARGET_W = 1000.0
CONTROL_RUN = 41358545575
UPSTREAM_RUN = 41310708653


def read_native(path: Path) -> list[dict[str, float]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"time", RF, DRIVE, *FIELDS.values()}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f"missing native monitor(s): {sorted(required - set(reader.fieldnames or []))}")
        rows = [{key: float(row[key]) for key in required} for row in reader]
    if len(rows) < 100:
        raise ValueError("insufficient native history")
    t = [r["time"] for r in rows]
    if any(not math.isfinite(x) for r in rows for x in r.values()):
        raise ValueError("nonfinite native monitor")
    if any(b <= a for a, b in zip(t, t[1:])):
        raise ValueError("native time not strictly increasing")
    if not math.isclose(t[0], 0, abs_tol=1e-15) or not math.isclose(t[-1], END_S, abs_tol=1e-15):
        raise ValueError("native run does not span 0–1ms")
    # At t=0 the native MOOSE RF postprocessor is initialized to zero and
    # the controller drive can precede its TIMESTEP_END clamp (7.495598).
    # This is NOT a post-start zero-power or out-of-range-drive allowance.
    if rows[0][RF] < 0 or rows[0][DRIVE] <= 0 or any(
            rows[0][f] < 0 for f in FIELDS.values()):
        raise ValueError("invalid native initial monitor")
    if any(r[RF] <= 0 or not 0 < r[DRIVE] <= 3.0 + 1e-6 or
           any(r[f] < 0 for f in FIELDS.values()) for r in rows[1:]):
        raise ValueError("negative/zero post-start RF, invalid drive or negative neutral")
    return rows


def sample(rows: list[dict[str, float]], time: float, key: str) -> float:
    times = [r["time"] for r in rows]
    idx = bisect.bisect_left(times, time)
    if idx == len(times):
        raise ValueError("sample past end")
    if idx == 0 or math.isclose(times[idx], time, rel_tol=0, abs_tol=1e-16):
        return rows[idx][key]
    lo, hi = rows[idx-1], rows[idx]
    w = (time - lo["time"]) / (hi["time"] - lo["time"])
    return lo[key] + w * (hi[key] - lo[key])


def stats(rows: list[dict[str, float]]) -> dict:
    late = [r for r in rows if r["time"] >= LATE_S - 1e-15]
    if len(late) < 10:
        raise ValueError("insufficient late-time resolution")
    rf = [r[RF] for r in late]
    drive = [r[DRIVE] for r in late]
    return {
        "late_sample_count": len(late),
        "late_rf_min_W": min(rf),
        "late_rf_max_W": max(rf),
        "late_rf_mean_W": statistics.mean(rf),
        "late_rf_peak_to_peak_percent_nominal": 100*(max(rf)-min(rf))/TARGET_W,
        "late_rf_rms_error_percent_nominal": 100*math.sqrt(
            statistics.mean([(v-TARGET_W)**2 for v in rf]))/TARGET_W,
        "late_drive_min": min(drive),
        "late_drive_max": max(drive),
        "late_drive_upper_saturation_count": sum(v >= 3.0-1e-8 for v in drive),
        "late_drive_upper_saturation_fraction": sum(v >= 3.0-1e-8 for v in drive)/len(drive),
        "neutral": {
            label: neutral_stats(late, field) for label,field in FIELDS.items()
        },
    }


def neutral_stats(late: list[dict[str, float]], field: str) -> dict:
    values = [r[field] for r in late]
    # Keep a separate absolute scale for derivative-sign filtering.
    # 1e-7 of the late-window density maximum suppresses numerical roundoff
    # without hiding the previously observed 0.06–0.117% decreases.
    tol = max(values)*1e-7
    increments = [b-a for a,b in zip(values, values[1:])]
    signs = [1 if v > tol else -1 if v < -tol else 0 for v in increments]
    nonzero = [s for s in signs if s]
    reversals = sum(a != b for a,b in zip(nonzero, nonzero[1:]))
    drops = []
    peak = values[0]
    peak_time = late[0]["time"]
    trough = peak
    trough_time = peak_time
    falling = False
    for row in late[1:]:
        v,t = row[field],row["time"]
        if v < peak-tol:
            if not falling:
                falling=True
                trough=v
                trough_time=t
            elif v < trough:
                trough,trough_time=v,t
        else:
            if falling and peak > 0:
                drops.append({"peak_us":peak_time*1e6,
                              "trough_us":trough_time*1e6,
                              "relative_drop_percent":100*(peak-trough)/peak})
            if v >= peak:
                peak,peak_time=v,t
                falling=False
    if falling and peak > 0:
        drops.append({"peak_us":peak_time*1e6,
                      "trough_us":trough_time*1e6,
                      "relative_drop_percent":100*(peak-trough)/peak})
    return {
        "positive_steps": signs.count(1),
        "negative_steps": signs.count(-1),
        "sign_reversals": reversals,
        "largest_peak_to_trough_drop_percent": max(
            [d["relative_drop_percent"] for d in drops], default=0),
        "peak_to_trough_events": drops,
    }


def compare(control: list[dict[str,float]], trial: list[dict[str,float]]) -> tuple[dict,list[dict]]:
    a,b=stats(control),stats(trial)
    trace=[]
    for row in control:
        t=row["time"]
        if t < START_S - 1e-15:
            continue
        r={"time_s":t}
        for key in (RF,DRIVE,*FIELDS.values()):
            r["control_"+key]=row[key]
            r["trial_"+key]=sample(trial,t,key)
        trace.append(r)
    if len(trace)<30:
        raise ValueError("insufficient aligned comparison")
    changes={}
    for label,key in FIELDS.items():
        v0=control[-1][key]
        v1=trial[-1][key]
        if v0<=0:
            raise ValueError(f"cannot compare zero endpoint density {label}")
        changes[label]=100*(v1/v0-1)
    result={
        "scientific_decision":"HOLD_STAGE6",
        "stage6_dtmax_100us_certified":False,
        "control_run_id":CONTROL_RUN,
        "control_dtmax_ns":10000,
        "trial_dtmax_ns":5000,
        "power_w":1000,
        "start_ns":100000,
        "end_ns":1000000,
        "upstream_run_id":UPSTREAM_RUN,
        "rf_feedback_and_chemistry_unchanged":True,
        "control":a,
        "trial":b,
        "rf_peak_to_peak_reduction_percent":100*(
            1-b["late_rf_peak_to_peak_percent_nominal"]/
            a["late_rf_peak_to_peak_percent_nominal"]),
        "endpoint_density_trial_minus_control_percent":changes,
        "aligned_trace_rows":len(trace),
        "limitations":"One refinement does not establish timestep convergence, steady state or physical validity. No Stage6 10ms authorization.",
    }
    return result,trace


def self_test() -> None:
    with tempfile.TemporaryDirectory() as td:
        p=Path(td)/"native.csv"
        times=[i/100000 for i in range(101)]
        with p.open("w",newline="") as f:
            writer=csv.DictWriter(f,fieldnames=["time",RF,DRIVE,*FIELDS.values()])
            writer.writeheader()
            for i,t in enumerate(times):
                writer.writerow({"time":t,RF:1000+200*math.sin(i*0.1),
                                 DRIVE:2.5,**{key:1e18*(1+i/100)
                                  for key in FIELDS.values()}})
        rows=read_native(p)
        assert len(rows)==101
        # Regression: the actual native t=0 RF=0 and unclamped initial drive
        # must be accepted, while an identical state at t>0 must be rejected.
        lines=p.read_text().splitlines()
        header=lines[0].split(",")
        initial=lines[1].split(",")
        initial[header.index(RF)]="0"
        initial[header.index(DRIVE)]="7.4955980963788"
        lines[1]=",".join(initial)
        p.write_text("\\n".join(lines)+"\\n")
        rows=read_native(p)
        assert rows[0][RF]==0 and rows[0][DRIVE]>3.0
        bad=lines[:]
        post=bad[2].split(",")
        post[header.index(RF)]="0"
        bad[2]=",".join(post)
        broken=Path(td)/"bad_post_start.csv"
        broken.write_text("\\n".join(bad)+"\\n")
        try: read_native(broken)
        except ValueError: pass
        else: raise AssertionError("post-start zero RF accepted")
        assert math.isclose(sample(rows,0.000505,"n_O2_a_avg"),1.505e18,rel_tol=1e-12)
        r,tr=compare(rows,rows)
        assert abs(r["rf_peak_to_peak_reduction_percent"])<1e-10
        assert all(abs(v)<1e-10 for v in r["endpoint_density_trial_minus_control_percent"].values())
        assert len(tr)>30
        for bad in ("NaN","-3"):
            lines=p.read_text().splitlines()
            fields=lines[0].split(",")
            col=fields.index("n_O2_a_avg")
            data=lines[-1].split(",")
            data[col]=bad
            lines[-1]=",".join(data)
            broken=Path(td)/"bad.csv"
            broken.write_text("\n".join(lines)+"\n")
            try:read_native(broken)
            except ValueError:pass
            else:raise AssertionError("bad native density accepted")
    print("OXYGEN25_DT5US_SENSITIVITY_SELFTEST_PASS")


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--self-test",action="store_true")
    p.add_argument("--control-csv",type=Path)
    p.add_argument("--trial-csv",type=Path)
    p.add_argument("--output-json",type=Path)
    p.add_argument("--output-csv",type=Path)
    a=p.parse_args()
    if a.self_test:
        self_test()
        return
    if not all((a.control_csv,a.trial_csv,a.output_json,a.output_csv)):
        p.error("comparison requires --control-csv --trial-csv --output-json --output-csv")
    result,trace=compare(read_native(a.control_csv),read_native(a.trial_csv))
    a.output_json.parent.mkdir(parents=True,exist_ok=True)
    a.output_json.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    with a.output_csv.open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(trace[0]))
        writer.writeheader()
        writer.writerows(trace)
    print("OXYGEN25_DT5US_RF_AND_NEUTRAL_SENSITIVITY_DIAGNOSTICS",json.dumps({
        "control_pp_pct":result["control"]["late_rf_peak_to_peak_percent_nominal"],
        "trial_pp_pct":result["trial"]["late_rf_peak_to_peak_percent_nominal"],
        "trial_neutral_O2a_max_drop_pct":result["trial"]["neutral"]["O2(a1Delta)"]["largest_peak_to_trough_drop_percent"],
        "decision":result["scientific_decision"]},sort_keys=True),flush=True)


if __name__=="__main__":
    main()
