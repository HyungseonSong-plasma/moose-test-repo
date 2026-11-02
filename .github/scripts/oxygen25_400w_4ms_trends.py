#!/usr/bin/env python3
"""Audit exact 400W 0–4ms native MOOSE plasma.csv. Diagnostic only."""
import argparse,csv,json,math,statistics
from pathlib import Path

FIELDS=("n_O2_X_avg","n_O2_a_avg","n_O_3P_avg","n_O_1D_avg")
RF="P_rf_raw_W_t6"

def analyze(path):
    with path.open(newline="") as f:
        reader=csv.DictReader(f)
        required=("time",RF,*FIELDS)
        if not set(required).issubset(reader.fieldnames or []):
            raise ValueError("missing time/RF/neutral columns")
        rows=[{k:float(r[k]) for k in required} for r in reader]
    if len(rows)<300:
        raise ValueError("too few native records")
    times=[r["time"] for r in rows]
    if (abs(times[0])>1e-15 or abs(times[-1]-.004)>1e-15
        or any(b<=a for a,b in zip(times,times[1:]))
        or not any(abs(t-.001)<1e-15 for t in times)):
        raise ValueError("bad time history or restart boundary")
    if any(not all(math.isfinite(v) for v in r.values()) or
           any(r[k]<0 for k in FIELDS) or
           (i and r[RF]<0) for i,r in enumerate(rows)):
        raise ValueError("nonfinite/negative monitor")
    diagnostics={}
    for name,lo in (("1to4ms",.001),("3to4ms",.003),("3p5to4ms",.0035)):
        chunk=[r for r in rows if r["time"]>=lo-1e-15]
        if len(chunk)<5:
            raise ValueError("insufficient late-time resolution")
        power=[r[RF] for r in chunk]
        data={}
        for k in FIELDS:
            values=[r[k] for r in chunk]
            tol=max(values)*1e-7
            diffs=[b-a for a,b in zip(values,values[1:])]
            signs=[1 if d>tol else -1 if d < -tol else 0 for d in diffs]
            nonzero=[s for s in signs if s]
            high=values[0]
            max_drop=0.
            for v in values[1:]:
                high=max(high,v)
                if high>0:max_drop=max(max_drop,(high-v)/high)
            data[k]={"final_cm3":values[-1]/1e6,
                     "relative_change_percent":100*(values[-1]/values[0]-1) if values[0]>0 else None,
                     "negative_steps":signs.count(-1),
                     "slope_sign_reversals":sum(a!=b for a,b in zip(nonzero,nonzero[1:])),
                     "max_drawdown_percent":100*max_drop}
        diagnostics[name]={"samples":len(chunk),
            "rf_min_W":min(power),"rf_max_W":max(power),
            "rf_peak_to_peak_W":max(power)-min(power),
            "rf_rms_error_W":math.sqrt(statistics.mean((p-400)**2 for p in power)),
            "neutral":data}
    late=diagnostics["3to4ms"]
    warnings=(late["rf_peak_to_peak_W"]>20 or late["rf_rms_error_W"]>20 or
              any(x["max_drawdown_percent"]>0.1 and x["slope_sign_reversals"]>=2
                  for x in late["neutral"].values()))
    return {"power_w":400,"final_time_s":.004,"rows":len(rows),
        "requested_dtmax_ns":10000,"timestep_convergence_established":False,
        "scientific_decision":"HOLD_REVIEW" if warnings else "NO_LARGE_OSCILLATION_STEADY_STATE_UNPROVEN",
        "diagnostics":diagnostics}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--csv",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    result=analyze(a.csv)
    a.output.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print("OXYGEN25_400W_4MS_RF_NEUTRAL_DIAGNOSTIC",result["scientific_decision"])

if __name__=="__main__":main()
