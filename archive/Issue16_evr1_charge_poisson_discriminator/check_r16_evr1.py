#!/usr/bin/env python3
import argparse, csv, math, tempfile
from pathlib import Path

S_TARGET = 80.0
PEAK_TARGET = S_TARGET / 8.0
AVG_TARGET = S_TARGET / 12.0
REL_TOL = 2.0e-3
ZERO_TOL = 1.0e-8
SIGN_TOL = 1.0e-9

EXPECTED = {
    "positive_charge": +1,
    "negative_ion": -1,
    "balanced_charge": 0,
    "electron_only": -1,
}

def last_row(path):
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise RuntimeError(f"no CSV rows: {path}")
    r = rows[-1]
    return {k: float(r[k]) for k in ("phi_avg","phi_min","phi_max")}

def relerr(a,b):
    return abs(a-b)/max(abs(b),1e-300)

def check_one(name, row, verbose=True):
    s = EXPECTED[name]
    ok = True
    if s == 0:
        metrics = {
            "avg_abs": abs(row["phi_avg"]),
            "min_abs": abs(row["phi_min"]),
            "max_abs": abs(row["phi_max"]),
        }
        ok = max(metrics.values()) <= ZERO_TOL
    elif s > 0:
        metrics = {
            "peak_relerr": relerr(row["phi_max"], PEAK_TARGET),
            "avg_relerr": relerr(row["phi_avg"], AVG_TARGET),
            "min_sign_margin": row["phi_min"],
        }
        ok = (metrics["peak_relerr"] <= REL_TOL and
              metrics["avg_relerr"] <= REL_TOL and
              row["phi_max"] > 0 and row["phi_avg"] > 0 and
              row["phi_min"] >= -SIGN_TOL)
    else:
        metrics = {
            "peak_relerr": relerr(row["phi_min"], -PEAK_TARGET),
            "avg_relerr": relerr(row["phi_avg"], -AVG_TARGET),
            "max_sign_margin": row["phi_max"],
        }
        ok = (metrics["peak_relerr"] <= REL_TOL and
              metrics["avg_relerr"] <= REL_TOL and
              row["phi_min"] < 0 and row["phi_avg"] < 0 and
              row["phi_max"] <= SIGN_TOL)
    if verbose:
        print(f"{name}_METRICS=" + ",".join(f"{k}={v:.17e}" for k,v in metrics.items()))
        print(f"{name}_CHECK: " + ("PASS" if ok else "FAIL"))
    return ok

def cross(rows, verbose=True):
    p=rows["positive_charge"]
    n=rows["negative_ion"]
    e=rows["electron_only"]
    b=rows["balanced_charge"]
    metrics = {
        "pos_neg_peak_sym": relerr(p["phi_max"], -n["phi_min"]),
        "pos_neg_avg_sym": relerr(p["phi_avg"], -n["phi_avg"]),
        "neg_electron_peak_sym": relerr(n["phi_min"], e["phi_min"]),
        "neg_electron_avg_sym": relerr(n["phi_avg"], e["phi_avg"]),
        "balanced_abs": max(abs(b["phi_avg"]),abs(b["phi_min"]),abs(b["phi_max"])),
    }
    ok=(metrics["pos_neg_peak_sym"] <= REL_TOL and
        metrics["pos_neg_avg_sym"] <= REL_TOL and
        metrics["neg_electron_peak_sym"] <= REL_TOL and
        metrics["neg_electron_avg_sym"] <= REL_TOL and
        metrics["balanced_abs"] <= ZERO_TOL)
    if verbose:
        print("R16_CROSS_METRICS=" + ",".join(f"{k}={v:.17e}" for k,v in metrics.items()))
        print("R16_CROSS_CASE_INVARIANTS: " + ("PASS" if ok else "FAIL"))
    return ok

def write_csv(path, avg, mn, mx):
    path.write_text(f"time,phi_avg,phi_min,phi_max\n1,{avg},{mn},{mx}\n")

def selftest():
    with tempfile.TemporaryDirectory() as td:
        td=Path(td)
        good = {
            "positive_charge": {"phi_avg":AVG_TARGET,"phi_min":0.01,"phi_max":PEAK_TARGET},
            "negative_ion": {"phi_avg":-AVG_TARGET,"phi_min":-PEAK_TARGET,"phi_max":-0.01},
            "balanced_charge": {"phi_avg":0.0,"phi_min":0.0,"phi_max":0.0},
            "electron_only": {"phi_avg":-AVG_TARGET,"phi_min":-PEAK_TARGET,"phi_max":-0.01},
        }
        good_ok = all(check_one(k,v,False) for k,v in good.items()) and cross(good,False)
        bad = {k:dict(v) for k,v in good.items()}
        bad["negative_ion"]["phi_min"] = +PEAK_TARGET
        bad["negative_ion"]["phi_avg"] = +AVG_TARGET
        bad_detected = (not check_one("negative_ion",bad["negative_ion"],False)) and (not cross(bad,False))
        bad_zero = {k:dict(v) for k,v in good.items()}
        bad_zero["balanced_charge"]["phi_max"] = 1e-3
        zero_detected = not check_one("balanced_charge",bad_zero["balanced_charge"],False)
        ok=good_ok and bad_detected and zero_detected
        print("R16_CHECKER_SELFTEST: " + ("PASS" if ok else "FAIL"))
        return 0 if ok else 1

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--self-test",action="store_true")
    ap.add_argument("--result-root")
    a=ap.parse_args()
    if a.self_test:
        return selftest()
    if not a.result_root:
        ap.error("--result-root required")
    root=Path(a.result_root)
    rows={}
    overall=True
    for name in EXPECTED:
        p=root/name/"input_out.csv"
        try:
            rows[name]=last_row(p)
            overall &= check_one(name,rows[name])
        except Exception as ex:
            print(f"{name}_CHECK: FAIL ({ex})")
            overall=False
    if len(rows)==len(EXPECTED):
        overall &= cross(rows)
    else:
        print("R16_CROSS_CASE_INVARIANTS: FAIL (missing case output)")
        overall=False
    return 0 if overall else 1

if __name__=="__main__":
    raise SystemExit(main())
