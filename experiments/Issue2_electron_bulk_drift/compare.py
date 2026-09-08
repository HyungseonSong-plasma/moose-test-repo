#!/usr/bin/env python3
from pathlib import Path
import csv, math, sys

HERE=Path(__file__).resolve().parent
N0=1e16

def last(case):
    p=HERE/case/"input_out.physical.csv"
    with p.open(newline="") as f:
        rows=list(csv.DictReader(f))
    if not rows:
        raise RuntimeError(f"empty {p}")
    return {k:float(v) for k,v in rows[-1].items() if v not in ("",None)}

def evaluate(rows):
    plus=rows["drift_Eplus"]
    minus=rows["drift_Eminus"]
    zero=rows["drift_zero"]
    diff=rows["diffusion_only"]
    comb=rows["combined"]
    qvt=rows["qvt_prepoisson"]

    dp=plus["left_avg"]-plus["right_avg"]
    dm=minus["right_avg"]-minus["left_avg"]
    dz=abs(zero["left_avg"]-zero["right_avg"])
    sym=abs(dp-dm)/max(abs(dp),abs(dm),1.0)

    out={}
    out["plus_sign"]=dp > 0
    out["minus_sign"]=dm > 0
    out["reversal_symmetry"]=sym <= 2e-6
    out["zero_field_negative_control"]=dz <= 2e-8*N0
    out["diffusion_smoothing"]=(diff["n_max"]-diff["n_min"]) < 0.39*N0
    out["combined_direction"]=comb["left_avg"] > comb["right_avg"]
    out["combined_differs_from_diffusion"]=abs(comb["left_avg"]-comb["right_avg"]) > 1e-8*N0
    out["qvt_positive"]=qvt["n_min"] > 0 and math.isfinite(qvt["n_max"])
    return out, {"delta_plus":dp,"delta_minus":dm,"delta_zero":dz,"symmetry_rel":sym}

def self_test():
    def mk(l=1e16,r=1e16,nmin=9e15,nmax=1.1e16):
        return {"left_avg":l,"right_avg":r,"n_min":nmin,"n_max":nmax}
    rows={
      "drift_Eplus":mk(1.01e16,9.9e15),
      "drift_Eminus":mk(9.9e15,1.01e16),
      "drift_zero":mk(),
      "diffusion_only":mk(nmin=8.2e15,nmax=1.18e16),
      "combined":mk(1.001e16,9.99e15),
      "qvt_prepoisson":mk(),
    }
    good,_=evaluate(rows)
    bad={k:dict(v) for k,v in rows.items()}
    bad["drift_Eminus"]["left_avg"]=1.02e16
    bad["drift_Eminus"]["right_avg"]=9.8e15
    bad_eval,_=evaluate(bad)
    ok=all(good.values()) and not all(bad_eval.values())
    print("R2_CROSS_CHECKER_SELFTEST:", "PASS" if ok else "FAIL")
    print("R2_CROSS_CHECKER_NEGATIVE_CONTROL:", "PASS" if not all(bad_eval.values()) else "FAIL")
    return 0 if ok else 2

def main():
    if "--self-test" in sys.argv:
        return self_test()
    rows={name:last(name) for name in [
      "drift_Eplus","drift_Eminus","drift_zero","diffusion_only","combined","qvt_prepoisson"
    ]}
    checks,diag=evaluate(rows)
    failed=[k for k,v in checks.items() if not v]
    for k,v in checks.items():
        print(f"{k}: {'PASS' if v else 'FAIL'}")
    for k,v in diag.items():
        print(f"{k.upper()}={v:.17e}")
    if failed:
        print("R2_CROSS_CASE_INVARIANTS: FAIL")
        print("FAILED="+",".join(failed))
        return 1
    print("R2_CROSS_CASE_INVARIANTS: PASS")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
