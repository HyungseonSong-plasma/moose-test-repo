#!/usr/bin/env python3
from pathlib import Path
import csv, json, math, sys

def read_last(path: Path):
    with path.open(newline="") as f:
        rows=list(csv.DictReader(f))
    if not rows:
        raise SystemExit(f"empty physical CSV: {path}")
    return rows[-1]

def val(r,k):
    if k not in r:
        raise SystemExit(f"missing CSV column {k}")
    x=float(r[k])
    if not math.isfinite(x):
        raise SystemExit(f"nonfinite {k}={r[k]!r}")
    return x

def self_test():
    good={
      "time":"0.01",
      "left_ion":"0.27","right_ion":"0.33",
      "left_neutral":"0.73","right_neutral":"0.67",
      "sum_w_min":"1.0","sum_w_max":"1.0",
      "ion_min":"0.2","ion_max":"0.4",
      "neutral_min":"0.6","neutral_max":"0.8",
    }
    bad=dict(good); bad["ion_min"]="-0.1"
    def evaluate(r, require_closure):
        vals=[val(r,k) for k in [
            "left_ion","right_ion","left_neutral","right_neutral",
            "sum_w_min","sum_w_max","ion_min","ion_max","neutral_min","neutral_max"]]
        if min(val(r,"ion_min"),val(r,"neutral_min")) < -1e-10:
            return False
        if max(val(r,"ion_max"),val(r,"neutral_max")) > 1.0+1e-10:
            return False
        if require_closure:
            if max(abs(val(r,"sum_w_min")-1),abs(val(r,"sum_w_max")-1)) > 1e-9:
                return False
        return True
    ok=evaluate(good,True) and not evaluate(bad,True)
    print("R15_CASE_CHECKER_SELFTEST:", "PASS" if ok else "FAIL")
    return 0 if ok else 1

def main():
    if "--self-test" in sys.argv:
        return self_test()
    if len(sys.argv)!=3:
        raise SystemExit("usage: check_case.py physical.csv case_expected.json")
    csv_path=Path(sys.argv[1])
    exp=json.loads(Path(sys.argv[2]).read_text())
    r=read_last(csv_path)

    if val(r,"time") <= 0:
        raise SystemExit("FAIL physical CSV contains nonphysical initialization row")

    for prefix in ("ion","neutral"):
        if val(r,f"{prefix}_min") < -1e-10 or val(r,f"{prefix}_max") > 1.0+1e-10:
            raise SystemExit(f"FAIL {prefix} out of [0,1] bounds")

    if exp["expect_closure"]:
        err=max(abs(val(r,"sum_w_min")-1.0),abs(val(r,"sum_w_max")-1.0))
        if err > exp["closure_tol"]:
            raise SystemExit(f"FAIL local heavy closure error={err}")

    print("R15_CASE_CHECK: PASS")
    print(f"CASE_ID={exp['case_id']}")
    for k in ["left_ion","right_ion","left_neutral","right_neutral",
              "sum_w_min","sum_w_max","ion_min","ion_max","neutral_min","neutral_max"]:
        print(f"{k.upper()}={val(r,k):.17e}")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
