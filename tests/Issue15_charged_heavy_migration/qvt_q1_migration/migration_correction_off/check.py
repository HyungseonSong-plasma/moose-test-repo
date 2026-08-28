#!/usr/bin/env python3
from pathlib import Path
import csv,json,math,sys
ALL=["O2","O2s","O2p","O","Om","Op","Os"]
def f(r,k):
    if k not in r: raise ValueError("missing "+k)
    x=float(r[k])
    if not math.isfinite(x): raise ValueError("nonfinite "+k)
    return x
def evaluate(rows,exp):
    if len(rows)<2: return False,"need >=2 physical rows"
    if any(f(r,"time")<=1e-12 for r in rows): return False,"initial row leaked"
    max_partition=max_closure=0.0
    for r in rows:
        max_closure=max(max_closure,abs(f(r,"sum_w_min")-1),abs(f(r,"sum_w_max")-1))
        sm=0.0
        for s in ALL:
            mn,mx=f(r,f"w_{s}_min"),f(r,f"w_{s}_max")
            if mn < -1e-8 or mx > 1+1e-8: return False,f"{s} bounds"
            if f(r,f"Dmix_{s}_avg")<=0: return False,f"{s} Dmix"
            m=f(r,f"mass_{s}"); xm=f(r,f"xmass_{s}")
            if m<=0 or not math.isfinite(xm): return False,f"{s} inventory"
            sm+=m
        mt=f(r,"mass_total")
        max_partition=max(max_partition,abs(sm-mt)/max(abs(mt),1e-30))
    if max_closure>exp["closure_tol"]: return False,f"closure {max_closure}"
    if max_partition>exp["partition_tol"]: return False,f"partition {max_partition}"
    return True,{"closure":max_closure,"partition":max_partition}
def self_test(exp):
    good={"time":"1e-4","sum_w_min":"1","sum_w_max":"1","mass_total":"7"}
    for i,s in enumerate(ALL):
        good[f"w_{s}_min"]="0.01"; good[f"w_{s}_max"]="0.9"; good[f"Dmix_{s}_avg"]="1e-3"
        good[f"mass_{s}"]="1"; good[f"xmass_{s}"]=str(.1+i*.01)
    ok,_=evaluate([good,dict(good,time="2e-4")],exp)
    bad=dict(good); bad["w_Om_min"]="-0.2"
    escaped,_=evaluate([good,bad],exp)
    passed=ok and not escaped
    print("R15_EVR2_CASE_CHECKER_SELFTEST:", "PASS" if passed else "FAIL")
    return 0 if passed else 1
def main():
    exp=json.loads(Path(sys.argv[-1]).read_text())
    if "--self-test" in sys.argv: return self_test(exp)
    with Path(sys.argv[1]).open(newline="") as fh: rows=list(csv.DictReader(fh))
    ok,msg=evaluate(rows,exp)
    if not ok: raise SystemExit("FAIL "+str(msg))
    print("R15_EVR2_CASE_CHECK: PASS")
    return 0
if __name__=="__main__": raise SystemExit(main())
