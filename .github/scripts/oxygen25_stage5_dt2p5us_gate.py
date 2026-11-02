#!/usr/bin/env python3
"""Fail-closed 1000W dtmax=2.5us continuation gate (100–500us only).

Compare same 400–500us physical-time window against the dtmax=5us native
MOOSE CSV, interpolated to a common 2.5us grid. This gate permits *only*
an independent 500us→1ms dtmax=2.5us experiment. Never authorizes the
separate 1ms→10ms dtmax=100us run, time-step convergence or PID tuning.
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
    "O2_X": "n_O2_X_avg",
    "O2_a1Delta": "n_O2_a_avg",
    "O_3P": "n_O_3P_avg",
    "O_1D": "n_O_1D_avg",
}
RF = "P_rf_raw_W_t6"
DRIVE = "rf_drive_scale_t6"
TARGET = 1000.0
LO, HI = 400e-6, 500e-6
GRID_INTERVAL = 2.5e-6
MIN_REDUCTION_PERCENT = 25.0
MATERIAL_NEUTRAL_DECLINE_PERCENT = 0.02
CONTROL_RUN_ID = 41379107857
TRIAL_STAGE4_RUN_ID = 41310708653
EPS = 1e-12


def read_native(path: Path, *, expected_end_s: float) -> list[dict[str, float]]:
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        required = {"time", RF, DRIVE, *FIELDS.values()}
        if not required.issubset(set(reader.fieldnames or [])):
            raise ValueError("missing required native monitor: " +
                             repr(sorted(required - set(reader.fieldnames or []))))
        rows = [{key: float(row[key]) for key in required} for row in reader]
    if len(rows) < 100:
        raise ValueError("native CSV has too few samples")
    for i, r in enumerate(rows):
        if not all(math.isfinite(value) for value in r.values()):
            raise ValueError("native monitor contains NaN/Inf")
        if any(r[key] < 0 for key in FIELDS.values()):
            raise ValueError("negative neutral density")
        if r[DRIVE] <= 0 or (i > 0 and r[RF] <= 0):
            raise ValueError("invalid post-initial RF power/drive")
    t = [r["time"] for r in rows]
    if not math.isclose(t[0], 0, rel_tol=0, abs_tol=1e-15):
        raise ValueError("native history must begin at zero")
    if not math.isclose(t[-1], expected_end_s, rel_tol=0, abs_tol=1e-15):
        raise ValueError("wrong native final physical time")
    if any(b <= a for a, b in zip(t, t[1:])):
        raise ValueError("nonmonotonic/repeated native time")
    if not any(t0 <= LO + EPS for t0 in t) or not any(t0 >= HI - EPS for t0 in t):
        raise ValueError("comparison interval not fully sampled")
    return rows


def linear_sample(rows: list[dict[str, float]], t: float, key: str) -> float:
    times = [r["time"] for r in rows]
    i = bisect.bisect_left(times, t)
    if i == 0:
        if abs(times[0]-t) > EPS:
            raise ValueError("left extrapolation forbidden")
        return rows[0][key]
    if i == len(rows):
        if abs(times[-1]-t) > EPS:
            raise ValueError("right extrapolation forbidden")
        return rows[-1][key]
    if abs(times[i]-t) <= EPS:
        return rows[i][key]
    x,y = rows[i-1],rows[i]
    w = (t-x["time"])/(y["time"]-x["time"])
    return (1-w)*x[key]+w*y[key]


def common_grid() -> list[float]:
    return [LO+i*GRID_INTERVAL for i in range(41)]


def neutral_diagnostics(values: list[float]) -> dict:
    scale = max(values)
    tol = max(scale*1e-7, 1e-20)
    increments = [b-a for a,b in zip(values, values[1:])]
    signs = [1 if delta>tol else -1 if delta < -tol else 0 for delta in increments]
    significant = [s for s in signs if s]
    reversals = sum(a != b for a,b in zip(significant, significant[1:]))
    # Maximum drawdown between consecutive observations: distinguishes noise
    # from a physically material density decline.
    high = values[0]
    max_drop = 0.0
    for x in values[1:]:
        high = max(x,high)
        if high > 0:
            max_drop = max(max_drop, 100*(high-x)/high)
    return {
        "negative_slope_steps": signs.count(-1),
        "slope_sign_reversals": reversals,
        "maximum_peak_to_trough_drop_percent": max_drop,
    }


def metrics(rows: list[dict[str, float]], grid: list[float]) -> dict:
    rf=[linear_sample(rows,t,RF) for t in grid]
    drv=[linear_sample(rows,t,DRIVE) for t in grid]
    exact=[r for r in rows if LO-EPS <= r["time"] <= HI+EPS]
    if len(exact) < 10:
        raise ValueError("too few measured points in comparison window")
    return {
        "physical_time_window_us": [400,500],
        "native_samples_in_window": len(exact),
        "aligned_grid_points": len(grid),
        "rf_min_W": min(rf),
        "rf_max_W": max(rf),
        "rf_peak_to_peak_W": max(rf)-min(rf),
        "rf_rms_error_W": math.sqrt(statistics.mean((x-TARGET)**2 for x in rf)),
        "pid_upper_saturation_fraction": sum(x[DRIVE]>=3.0-1e-8 for x in exact)/len(exact),
        "pid_upper_saturation_samples": sum(x[DRIVE]>=3.0-1e-8 for x in exact),
        "aligned_pid_upper_saturation_fraction": sum(x>=3.0-1e-8 for x in drv)/len(drv),
        "neutral": {
            name: neutral_diagnostics([linear_sample(rows,t,key) for t in grid])
            for name,key in FIELDS.items()
        },
    }


def analyse(control: list[dict[str,float]], trial: list[dict[str,float]]) -> dict:
    grid=common_grid()
    base=metrics(control,grid)
    test=metrics(trial,grid)
    def reduction(key):
        if base[key] <= 0:
            raise ValueError("baseline has no valid measured oscillation metric")
        return 100*(1-test[key]/base[key])
    pp_reduction = reduction("rf_peak_to_peak_W")
    rms_reduction = reduction("rf_rms_error_W")
    saturation_not_worse = (
        test["pid_upper_saturation_fraction"] <=
        base["pid_upper_saturation_fraction"] + 1/max(1,test["native_samples_in_window"])
    )
    neutral_not_worse={}
    for name in FIELDS:
        ctrl=base["neutral"][name]
        exp=test["neutral"][name]
        ctrl_drop=ctrl["maximum_peak_to_trough_drop_percent"]
        exp_drop=exp["maximum_peak_to_trough_drop_percent"]
        # No new material peak-to-trough drops; minor roundoff and
        # interpolation artifacts below 0.02% are treated as numerical noise.
        neutral_not_worse[name] = (
            exp_drop <= max(ctrl_drop,MATERIAL_NEUTRAL_DECLINE_PERCENT)
            and not (ctrl["slope_sign_reversals"]==0
                     and exp["slope_sign_reversals"]>=3
                     and exp_drop >= MATERIAL_NEUTRAL_DECLINE_PERCENT)
        )
    evidence_pass=all([
        pp_reduction>=MIN_REDUCTION_PERCENT,
        rms_reduction>=MIN_REDUCTION_PERCENT,
        saturation_not_worse,
        all(neutral_not_worse.values()),
    ])
    return {
        "scientific_decision": ("ALLOW_DT2P5US_500TO1000US_CONTINUATION"
                                if evidence_pass else "HOLD_DT2P5US_CONTINUATION"),
        "stage6_dtmax_100us_certified": False,
        "timestep_convergence_certified": False,
        "start_us": 100, "end_us": 500,
        "comparison_window_us": [400,500],
        "control_dtmax_us": 5.0,
        "trial_dtmax_us": 2.5,
        "control_run_id": CONTROL_RUN_ID,
        "upstream_stage4_run_id": TRIAL_STAGE4_RUN_ID,
        "acceptance_threshold_min_rf_pp_and_rms_reduction_percent": MIN_REDUCTION_PERCENT,
        "rf_peak_to_peak_reduction_percent": pp_reduction,
        "rf_rms_error_reduction_percent": rms_reduction,
        "pid_upper_saturation_not_worse": saturation_not_worse,
        "neutral_oscillation_not_worse_by_species": neutral_not_worse,
        "control_5us": base, "trial_2p5us": test,
        "limitations": ("Common 400–500us physical-time grid; RF waveform remains "
                        "sampled/interpolated, short window, so this permits only "
                        "dtmax2.5us continuation to 1ms, not physical convergence "
                        "or Stage6 10ms dtmax100us."),
    }


def self_test() -> None:
    assert len(common_grid())==41
    with tempfile.TemporaryDirectory() as tmp:
        d=Path(tmp)
        def generate(path: Path, step_us: float, amplitude: float) -> None:
            # Full 0–1ms control; truncated 0–500us trial; t0 RF zero is
            # a verified legitimate MOOSE pre-initialization diagnostic.
            end_us = 1000 if step_us == 5 else 500
            with path.open("w", newline="") as f:
                fields=["time", RF, DRIVE, *FIELDS.values()]
                writer=csv.DictWriter(f,fieldnames=fields)
                writer.writeheader()
                for i in range(int(end_us/step_us)+1):
                    t=i*step_us*1e-6
                    p=0.0 if i==0 else 1000+amplitude*math.sin(2*math.pi*t/40e-6)
                    writer.writerow({"time":t,RF:p,DRIVE:2.0,
                        **{key:1e17*(1+t/1e-3) for key in FIELDS.values()}})
        a,b=d/"base.csv",d/"trial.csv"
        generate(a,5,200)
        generate(b,2.5,75)
        base=read_native(a,expected_end_s=0.001)
        trial=read_native(b,expected_end_s=0.0005)
        yes=analyse(base,trial)
        assert yes["scientific_decision"]=="ALLOW_DT2P5US_500TO1000US_CONTINUATION"
        assert yes["rf_peak_to_peak_reduction_percent"]>25
        generate(b,2.5,225)
        no=analyse(base,read_native(b,expected_end_s=0.0005))
        assert no["scientific_decision"]=="HOLD_DT2P5US_CONTINUATION"
        txt=b.read_text()
        b.write_text(txt.replace("0.0,", "NaN,",1))
        try:
            read_native(b,expected_end_s=0.0005)
        except ValueError:
            pass
        else:
            raise AssertionError("nonfinite input was accepted")
    print("OXYGEN25_DT2P5US_100TO500US_GATE_SELFTEST_PASS")


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test",action="store_true")
    parser.add_argument("--control-csv",type=Path)
    parser.add_argument("--trial-csv",type=Path)
    parser.add_argument("--output-json",type=Path)
    args=parser.parse_args()
    if args.self_test:
        self_test()
        return
    if not (args.control_csv and args.trial_csv and args.output_json):
        parser.error("expected --control-csv --trial-csv --output-json")
    result=analyse(
        read_native(args.control_csv,expected_end_s=0.001),
        read_native(args.trial_csv,expected_end_s=0.0005),
    )
    args.output_json.parent.mkdir(parents=True,exist_ok=True)
    args.output_json.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("OXYGEN25_DT2P5US_SIGNIFICANT_RF_REDUCTION_GATE",
          json.dumps({k:result[k] for k in (
              "scientific_decision","rf_peak_to_peak_reduction_percent",
              "rf_rms_error_reduction_percent","pid_upper_saturation_not_worse",
              "neutral_oscillation_not_worse_by_species")},sort_keys=True),flush=True)


if __name__=="__main__":
    main()
