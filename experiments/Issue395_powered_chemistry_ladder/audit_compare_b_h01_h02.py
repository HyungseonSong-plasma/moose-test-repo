#!/usr/bin/env python3
"""1000W oxygen plasma B / B+H01 / B+H02 reproducible chemistry comparison.

Emit per-case time series from native CSV, do not invent missing data.
O neutral inventory is captured in kg using neutral_mass_O; multiply by
N_A/M_O to obtain the total number of O(3P) atoms.
Neutral mean number density requires actual plasma-domain volume and is
deliberately not inferred from a mass inventory alone.
"""
import argparse,csv,json,math
from pathlib import Path

def near(a,b,what,rtol=2e-5):
    if not math.isfinite(a) or not math.isfinite(b):
        raise AssertionError("nonfinite "+what)
    if abs(a-b)>rtol*max(abs(a),abs(b),1e-22):
        raise AssertionError(f"{what}: {a} not {b}")

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--result",required=True,type=Path)
    parser.add_argument("--case",required=True,choices=("B","B_H01","B_H02"))
    a=parser.parse_args()
    file=a.result/"run/plasma.csv"
    if not file.is_file():raise AssertionError("native plasma.csv missing; no comparison possible")
    with file.open(newline="") as stream:rows=list(csv.DictReader(stream))
    if len(rows)!=461 or not math.isclose(float(rows[-1]["time"]),1e-4,rel_tol=0,abs_tol=1e-12):
        raise AssertionError("461 points ending at 100us required")
    base_required=("time","neutral_mass_O","w_O_max","w_O_min","diss_R_integral","mixed_R_integral","edetach_R_integral")
    names=("R_integral","op_sink_integral","o2p_source_integral","o_mass_integral",
           "neutral_mass_integral","o2_mass_sink_integral","mass_closure_integral","charge_closure_integral")
    if a.case=="B_H01":
        required=base_required+tuple("h01_"+v for v in names)
    elif a.case=="B_H02":
        required=base_required+tuple("h02_"+v for v in ("R_integral","om_sink_integral","positive_sink_integral","o_mass_integral","neutral_mass_integral","mass_closure_integral","charge_closure_integral"))
    else:required=base_required
    for k in required:
        if k not in rows[0]:raise AssertionError("missing result column "+k)
    unexpected={"B":("h01_R_integral","h02_R_integral","h03_R_integral"),
      "B_H01":("h02_R_integral","h03_R_integral"),
      "B_H02":("h01_R_integral","h03_R_integral")}[a.case]
    for k in unexpected:
        if k in rows[0]:raise AssertionError("unexpected extra heavy channel "+k)
    series=[]
    for i,row in enumerate(rows):
        def v(k):
            n=float(row[k])
            if not math.isfinite(n):raise AssertionError("nonfinite "+k+" at "+str(i))
            return n
        t=v("time")
        mass=v("neutral_mass_O")
        if mass < 0:raise AssertionError("negative O inventory")
        if i and t<=series[-1]["time_s"]:raise AssertionError("nonincreasing times")
        d={"time_s":t,"time_us":t*1e6,"O_neutral_mass_kg":mass,
          "O_total_atoms":mass/0.016*6.02214076e23,
          "w_O_max":v("w_O_max"),"w_O_min":v("w_O_min"),
          "R_ground_mol_s":v("diss_R_integral"),
          "R_mixed_mol_s":v("mixed_R_integral"),
          "R_EDETACH_mol_s":v("edetach_R_integral")}
        if a.case=="B_H01":
            r=v("h01_R_integral")
            if r<-1e-22:raise AssertionError("negative H01 rate")
            near(v("h01_op_sink_integral"),-r,"H01 O+ sink")
            near(v("h01_o2p_source_integral"),r,"H01 O2+ source")
            near(v("h01_o_mass_integral"),0.016*r,"H01 O3P mass")
            near(v("h01_neutral_mass_integral"),-0.016*r,"H01 net neutral mass")
            near(v("h01_o2_mass_sink_integral"),-0.032*r,"H01 O2 sink")
            near(v("h01_mass_closure_integral"),0,"H01 mass closure")
            near(v("h01_charge_closure_integral"),0,"H01 charge closure")
            d["R_heavy_mol_s"]=r
        if a.case=="B_H02":
            r=v("h02_R_integral")
            if r<-1e-22:raise AssertionError("negative H02 rate")
            near(v("h02_om_sink_integral"),-r,"H02 O- sink")
            near(v("h02_positive_sink_integral"),-r,"H02 O+ sink")
            near(v("h02_o_mass_integral"),0.032*r,"H02 O3P mass")
            near(v("h02_neutral_mass_integral"),0.032*r,"H02 neutral mass")
            near(v("h02_mass_closure_integral"),0,"H02 mass closure")
            near(v("h02_charge_closure_integral"),0,"H02 charge closure")
            d["R_heavy_mol_s"]=r
        series.append(d)
    out=a.result/"diagnostics"
    out.mkdir(parents=True,exist_ok=True)
    with (out/(a.case+"_O3P_timeseries.csv")).open("w",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=list(series[0]))
        writer.writeheader()
        writer.writerows(series)
    m0=series[0]["O_neutral_mass_kg"];mf=series[-1]["O_neutral_mass_kg"]
    summary={"case":a.case,"status":"PASS","science_acceptance":"HOLD",
      "RF_target_W":1000,"initial_O3P_number_density_m3":5e18,
      "points":len(series),"last_time_us":series[-1]["time_us"],
      "first_O_mass_kg":m0,"last_O_mass_kg":mf,
      "O_mass_percent_change":100*(mf/m0-1) if m0>0 else None,
      "first_w_O_max":series[0]["w_O_max"],"last_w_O_max":series[-1]["w_O_max"],
      "quantity_note":"O total mass / inventory is not mean number density without domain volume"}
    (out/(a.case+"_O3P_summary.json")).write_text(json.dumps(summary,indent=2,allow_nan=False)+"\n")
    print(json.dumps(summary,indent=2,allow_nan=False))
    print("ISSUE395_"+a.case+"_O3P_TIMESERIES_P5_PASS")

if __name__=="__main__":main()
