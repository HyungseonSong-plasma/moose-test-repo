#!/usr/bin/env python3
from __future__ import annotations
import argparse, csv, json, math, re
from pathlib import Path

PROFILE_KEYS = (
    "w_O2p", "w_Om", "w_Op", "potential_fast",
    "electron_density_fast", "mean_energy_fast",
    "heavy_charge_out", "net_charge_out",
)
TRAJ_KEYS = ("phi_avg", "phi_min", "phi_max")

def rows(path: Path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def latest_profile(case: Path) -> Path:
    hits=[]
    for p in case.glob("input_final_csv_parent_profile_*.csv"):
        m=re.search(r"_([0-9]+)\.csv$", p.name)
        if m:
            hits.append((int(m.group(1)),p))
    if not hits:
        raise RuntimeError(f"no final profile in {case}")
    return max(hits)[1]

def num(row,key):
    return float(row[key])

def profile(case: Path):
    rr=rows(latest_profile(case))
    rr.sort(key=lambda x:num(x,"x"))
    return rr

def einf(a,b,key):
    scale=max(max(abs(num(x,key)) for x in a),1e-30)
    return max(abs(num(x,key)-num(y,key)) for x,y in zip(a,b,strict=True))/scale

def efield_err(a,b):
    def e(rows_):
        return [
            -(num(rows_[i+1],"potential_fast")-num(rows_[i],"potential_fast"))/
              (num(rows_[i+1],"x")-num(rows_[i],"x"))
            for i in range(len(rows_)-1)
        ]
    ea,eb=e(a),e(b)
    return max(abs(x-y) for x,y in zip(ea,eb,strict=True))/max(max(abs(x) for x in ea),1e-30)

def trajectory(case: Path):
    return rows(case/"input_step_csv.csv")

def traj_compare(a,b):
    if len(a)!=len(b):
        return {"same_count":False,"baseline_points":len(a),"sibling_points":len(b)}
    out={"same_count":True,"baseline_points":len(a),"sibling_points":len(b)}
    out["time_max_abs_delta_s"]=max(abs(num(x,"time")-num(y,"time")) for x,y in zip(a,b,strict=True))
    for key in TRAJ_KEYS:
        if key in a[0] and key in b[0]:
            out[f"{key}_max_abs_delta"]=max(abs(num(x,key)-num(y,key)) for x,y in zip(a,b,strict=True))
    return out

def fp_history(path: Path):
    rr=rows(path)
    out=[]
    for r in rr:
        if "time" not in r or "fixed_point_iterations" not in r:
            continue
        t=float(r["time"])
        if t>0:
            out.append((t,int(round(float(r["fixed_point_iterations"])))))
    return out

def find_fp_csv(case: Path, sibling: bool):
    exact=case/("input_out_gummel_driver0_step_csv.csv" if sibling else "input_out_electron0_step_csv.csv")
    if exact.is_file():
        return exact
    # fallback helps diagnose output-prefix changes without guessing silently
    cand=list(case.glob("input_out_*0_step_csv.csv"))
    if len(cand)==1:
        return cand[0]
    raise RuntimeError(f"fixed-point CSV not found/ambiguous in {case}: {[p.name for p in cand]}")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--baseline",type=Path,required=True)
    ap.add_argument("--sibling",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    ap.add_argument("--profile-tol",type=float,default=1e-7)
    ap.add_argument("--trajectory-tol-v",type=float,default=1e-6)
    a=ap.parse_args()

    pa,pb=profile(a.baseline),profile(a.sibling)
    if len(pa)!=len(pb):
        raise SystemExit(f"profile point mismatch {len(pa)} != {len(pb)}")
    prof={k:einf(pa,pb,k) for k in PROFILE_KEYS}
    prof["electric_field_einf"]=efield_err(pa,pb)

    ta,tb=trajectory(a.baseline),trajectory(a.sibling)
    tr=traj_compare(ta,tb)

    fa=fp_history(find_fp_csv(a.baseline,False))
    fb=fp_history(find_fp_csv(a.sibling,True))
    fp={
        "same_history": fa==fb,
        "baseline_steps":len(fa),
        "sibling_steps":len(fb),
        "baseline_total":sum(v for _,v in fa),
        "sibling_total":sum(v for _,v in fb),
        "baseline_history":[v for _,v in fa],
        "sibling_history":[v for _,v in fb],
        "time_max_abs_delta_s": (
            max(abs(x[0]-y[0]) for x,y in zip(fa,fb,strict=True))
            if len(fa)==len(fb) and fa else None
        ),
    }

    max_profile=max(prof.values())
    traj_v=[v for k,v in tr.items() if k.endswith("_max_abs_delta") and isinstance(v,(int,float))]
    max_traj=max(traj_v) if traj_v else math.inf
    passed=(
        tr.get("same_count") is True
        and tr.get("time_max_abs_delta_s",math.inf)<=1e-18
        and fp["same_history"]
        and max_profile<=a.profile_tol
        and max_traj<=a.trajectory_tol_v
    )
    result={
        "classification":"GEN34_SIBLING_PARITY_PASS" if passed else "GEN34_SIBLING_PARITY_FAIL",
        "evidence_valid":passed,
        "profile_metrics":prof,
        "max_profile_metric":max_profile,
        "potential_trajectory":tr,
        "max_potential_trajectory_abs_delta_V":max_traj,
        "fixed_point":fp,
        "thresholds":{"profile_einf":a.profile_tol,"potential_trajectory_abs_V":a.trajectory_tol_v},
    }
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("GEN34_SIBLING_PARITY",json.dumps(result,sort_keys=True))
    raise SystemExit(0 if passed else 2)

if __name__=="__main__":
    main()
