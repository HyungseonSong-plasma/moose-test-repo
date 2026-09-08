#!/usr/bin/env python3
from pathlib import Path
import csv, json, math, sys

KB = 1.380649e-23

def read_last(path: Path):
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise SystemExit(f"empty physical CSV: {path}")
    return rows[-1]

def val(row, key):
    if key not in row:
        raise SystemExit(f"missing CSV column {key}")
    x = float(row[key])
    if not math.isfinite(x):
        raise SystemExit(f"nonfinite {key}={row[key]!r}")
    return x

def relerr(a,b):
    return abs(a-b)/max(abs(b),1e-300)

def evaluate(row, exp):
    n0 = float(exp["n0"])
    N = float(exp["p"]) / (KB * float(exp["T"]))
    mu = float(exp["muN"]) / N
    diff = float(exp["DN"]) / N

    checks = []
    checks.append(("N", relerr(val(row,"neutral_number_density_avg"),N) <= 2e-10))
    checks.append(("mu", relerr(val(row,"electron_mobility_avg"),mu) <= 2e-10))
    checks.append(("D", relerr(val(row,"electron_diffusion_avg"),diff) <= 2e-10))

    nmin = val(row,"n_min")
    nmax = val(row,"n_max")
    navg = val(row,"n_avg")
    inv = val(row,"inventory")
    vol = val(row,"domain_volume")
    checks.append(("positive", nmin > 0.0 and nmax >= nmin))
    checks.append(("inventory", relerr(inv,n0*vol) <= float(exp["inventory_rel_tol"])))
    checks.append(("mean", relerr(navg,n0) <= max(float(exp["inventory_rel_tol"])*5.0,2e-8)))

    mode = exp["mode"]
    if mode == "diffusion":
        checks.append(("diffusion_smoothing", (nmax-nmin) < 0.39*n0))
    elif mode == "drift":
        left = val(row,"left_avg")
        right = val(row,"right_avg")
        s = int(exp["field_sign"])
        if s > 0:
            checks.append(("drift_sign", left > right))
        elif s < 0:
            checks.append(("drift_sign", left < right))
        else:
            checks.append(("zero_field", abs(left-right) <= 2e-8*n0))
    elif mode == "combined":
        left = val(row,"left_avg")
        right = val(row,"right_avg")
        checks.append(("combined_drift_signature", left > right))
        checks.append(("combined_nonuniform", (nmax-nmin) > 1e-8*n0))
    elif mode == "qvt":
        checks.append(("qvt_finite", nmax < 10.0*n0))
    else:
        raise SystemExit(f"unknown mode {mode}")

    return checks, {"N":N,"mu":mu,"D":diff,"nmin":nmin,"nmax":nmax,"navg":navg,"inv":inv,"vol":vol}

def self_test():
    exp={"mode":"drift","field_sign":1,"p":101325.0,"T":600.0,
         "muN":1.57e24,"DN":6.64e24,"n0":1e16,"inventory_rel_tol":1e-8}
    N=exp["p"]/(KB*exp["T"]); mu=exp["muN"]/N; d=exp["DN"]/N
    good={
      "neutral_number_density_avg":str(N),
      "electron_mobility_avg":str(mu),
      "electron_diffusion_avg":str(d),
      "n_min":"9e15","n_max":"1.1e16","n_avg":"1e16",
      "inventory":"1e16","domain_volume":"1",
      "left_avg":"1.01e16","right_avg":"9.9e15",
    }
    bad=dict(good); bad["electron_mobility_avg"]=str(mu*1.1)
    ok1=all(x for _,x in evaluate(good,exp)[0])
    ok2=all(x for _,x in evaluate(bad,exp)[0])
    ok=ok1 and not ok2
    print("R2_CASE_CHECKER_SELFTEST:", "PASS" if ok else "FAIL")
    print("R2_CASE_CHECKER_NEGATIVE_CONTROL:", "PASS" if not ok2 else "FAIL")
    return 0 if ok else 2

def main():
    if "--self-test" in sys.argv:
        return self_test()
    if len(sys.argv) != 3:
        raise SystemExit("usage: check_case.py physical.csv expected.json")
    row=read_last(Path(sys.argv[1]))
    exp=json.loads(Path(sys.argv[2]).read_text())
    if val(row,"time") <= 0.0:
        raise SystemExit("FAIL normalized CSV does not contain a physical timestep")
    checks,diag=evaluate(row,exp)
    failed=[name for name,ok in checks if not ok]
    if failed:
        print("R2_CASE_CHECK: FAIL")
        print("FAILED="+",".join(failed))
        for k,v in diag.items():
            print(f"{k.upper()}={v:.17e}")
        return 1
    print("R2_CASE_CHECK: PASS")
    print("MODE="+exp["mode"])
    for k,v in diag.items():
        print(f"{k.upper()}={v:.17e}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
