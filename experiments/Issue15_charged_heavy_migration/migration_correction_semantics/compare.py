#!/usr/bin/env python3
from pathlib import Path
import csv, copy, json, math, sys

HERE=Path(__file__).resolve().parent
CASES=[
 "migration_off",
 "migration_on_Eplus",
 "migration_on_Eminus",
 "migration_on_zminus",
 "migration_on_mu2",
 "correction_off",
]

INITIAL={
 "left_ion":0.275,
 "right_ion":0.325,
 "left_neutral":0.725,
 "right_neutral":0.675,
}

def last(case):
    p=HERE/case/"input_out.physical.csv"
    with p.open(newline="") as f:
        rows=list(csv.DictReader(f))
    if not rows:
        raise ValueError(f"empty {p}")
    r=rows[-1]
    return {k:float(v) for k,v in r.items()}

def closure_error(r):
    return max(abs(r["sum_w_min"]-1.0),abs(r["sum_w_max"]-1.0))

def evaluate(data):
    off=data["migration_off"]
    plus=data["migration_on_Eplus"]
    minus=data["migration_on_Eminus"]
    zminus=data["migration_on_zminus"]
    mu2=data["migration_on_mu2"]
    corr_off=data["correction_off"]

    # OFF: electric field exists, but with drift/correction kernels absent no species motion.
    off_delta=max(abs(off[k]-INITIAL[k]) for k in INITIAL)
    if off_delta > 1e-9:
        return False,f"migration OFF changed species: max_delta={off_delta}"

    dplus=plus["left_ion"]-INITIAL["left_ion"]
    dminus=minus["left_ion"]-INITIAL["left_ion"]
    dzminus=zminus["left_ion"]-INITIAL["left_ion"]
    dmu2=mu2["left_ion"]-INITIAL["left_ion"]
    dcorr=corr_off["left_ion"]-INITIAL["left_ion"]

    # +z, +E drives ion from left to right; reversing either E or z flips the sign.
    if not (dplus < -1e-6):
        return False,f"+z,+E migration sign wrong: dleft={dplus}"
    if not (dminus > 1e-6):
        return False,f"E reversal did not flip sign: dleft={dminus}"
    if not (dzminus > 1e-6):
        return False,f"charge reversal did not flip sign: dleft={dzminus}"

    # z reversal and E reversal should be equivalent for the same |z mu E|.
    equiv=abs(dminus-dzminus)/max(abs(dminus),abs(dzminus),1e-30)
    if equiv > 5e-3:
        return False,f"E-sign and z-sign reversal mismatch: rel={equiv}"

    # Mobility scaling: one implicit step at small CFL should be close to linear.
    ratio=abs(dmu2/dplus)
    if not (1.90 <= ratio <= 2.10):
        return False,f"mobility scaling not linear enough: ratio={ratio}"

    # Correction ON: local full-heavy closure is preserved to solver/discrete tolerance.
    for name in ["migration_on_Eplus","migration_on_Eminus","migration_on_zminus","migration_on_mu2"]:
        e=closure_error(data[name])
        if e > 2e-9:
            return False,f"{name} zero-net-heavy-mass-flux closure failed: {e}"

    # Neutral has no direct drift kernel; under correction ON it must move opposite ion.
    nplus=plus["left_neutral"]-INITIAL["left_neutral"]
    if not (nplus > 1e-6 and dplus < -1e-6):
        return False,f"neutral correction response not opposite ion: ion={dplus}, neutral={nplus}"

    # Correction OFF is the negative control: local sum(w) must visibly leave unity.
    corr_err=closure_error(corr_off)
    if corr_err < 1e-5:
        return False,f"correction-OFF negative control not detected: closure_err={corr_err}"

    # Direct ion migration remains active in correction-OFF.
    if not (dcorr < -1e-6):
        return False,f"correction-OFF direct migration inactive/wrong sign: {dcorr}"

    return True,{
      "off_max_delta":off_delta,
      "dleft_Eplus":dplus,
      "dleft_Eminus":dminus,
      "dleft_zminus":dzminus,
      "dleft_mu2":dmu2,
      "mu2_over_mu1":ratio,
      "Eminus_zminus_rel":equiv,
      "correction_on_closure_max":max(
          closure_error(data[n]) for n in
          ["migration_on_Eplus","migration_on_Eminus","migration_on_zminus","migration_on_mu2"]),
      "correction_off_closure_error":corr_err,
      "neutral_left_delta_Eplus":nplus,
    }

def synthetic():
    # Chosen to satisfy only the semantic relationships, not to mimic a particular solver.
    def row(li,ri,ln,rn,smin=1,smax=1):
        return dict(left_ion=li,right_ion=ri,left_neutral=ln,right_neutral=rn,
                    sum_w_min=smin,sum_w_max=smax)
    return {
      "migration_off":row(.275,.325,.725,.675),
      "migration_on_Eplus":row(.274,.326,.726,.674),
      "migration_on_Eminus":row(.276,.324,.724,.676),
      "migration_on_zminus":row(.276,.324,.724,.676),
      "migration_on_mu2":row(.273,.327,.727,.673),
      "correction_off":row(.274,.326,.725,.675,.999,.999),
    }

def self_test():
    good=synthetic()
    ok,_=evaluate(good)
    if not ok:
        print("R15_CROSS_CHECKER_SELFTEST: FAIL good")
        return 1

    muts=[]
    m=copy.deepcopy(good); m["migration_on_Eminus"]["left_ion"]=.274; muts.append(("E_sign",m))
    m=copy.deepcopy(good); m["migration_on_zminus"]["left_ion"]=.274; muts.append(("z_sign",m))
    m=copy.deepcopy(good); m["migration_on_mu2"]["left_ion"]=.2742; muts.append(("mu_scale",m))
    m=copy.deepcopy(good); m["migration_on_Eplus"]["sum_w_max"]=1.01; muts.append(("closure_on",m))
    m=copy.deepcopy(good); m["correction_off"]["sum_w_min"]=1; m["correction_off"]["sum_w_max"]=1; muts.append(("corr_off",m))
    for name,m in muts:
        passed,_=evaluate(m)
        if passed:
            print("R15_CROSS_CHECKER_SELFTEST: FAIL mutation escaped",name)
            return 1
    print("R15_CROSS_CHECKER_SELFTEST: PASS")
    print("R15_CROSS_CHECKER_NEGATIVE_CONTROLS: PASS")
    return 0

def main():
    if "--self-test" in sys.argv:
        return self_test()
    data={name:last(name) for name in CASES}
    ok,msg=evaluate(data)
    if not ok:
        print("R15_CROSS_CASE_INVARIANTS: FAIL")
        print(msg)
        return 1
    print("R15_CROSS_CASE_INVARIANTS: PASS")
    for k,v in msg.items():
        print(f"{k.upper()}={v:.17e}")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
