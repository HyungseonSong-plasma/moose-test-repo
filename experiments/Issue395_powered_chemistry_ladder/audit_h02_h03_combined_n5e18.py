#!/usr/bin/env python3
"""P5 physical history closure audit: B+H02+H03 simultaneously at 1000 W.

Both reaction rates have independent progress owners. The total negative ion sink
is -(R_H02+R_H03), the total O(3P) mass source is
(2*M_O*R_H02+3*M_O*R_H03), and the positive-ion sinks are independently
assigned to O+ (H02) and O2+ (H03). Electron source is zero for both.
"""
import argparse,csv,json,math
from pathlib import Path

M_O=0.016
ABS=1e-22
REL=2e-5

def close(actual, expected, label):
    if not math.isfinite(actual) or not math.isfinite(expected):
        raise AssertionError(f"{label}: nonfinite")
    if abs(actual-expected)>REL*max(abs(actual),abs(expected),ABS):
        raise AssertionError(f"{label}: {actual} != {expected}")

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--result",required=True,type=Path)
    args=parser.parse_args()
    with (args.result/"run/plasma.csv").open(newline="") as stream:
        rows=list(csv.DictReader(stream))
    if len(rows)!=461 or not math.isclose(float(rows[-1]["time"]),1e-4,abs_tol=1e-12,rel_tol=0):
        raise AssertionError("full 100us, 461-point trajectory required")
    suffixes=("R_integral","om_sink_integral","positive_sink_integral",
              "o_mass_integral","neutral_mass_integral","mass_closure_integral",
              "charge_closure_integral")
    required=["{}_{}".format(arm,k) for arm in ("h02","h03") for k in suffixes]
    required+=["edetach_R_integral","diss_R_integral","mixed_R_integral"]
    for k in required:
        if k not in rows[0]:raise AssertionError("missing required diagnostic: "+k)
    positive_rates={"H02":0,"H03":0}
    for i,row in enumerate(rows):
        def v(k):
            num=float(row[k])
            if not math.isfinite(num): raise AssertionError(f"nonfinite {k} at {i}")
            return num
        rates={}
        sinks=[]
        o_source=0.0
        for arm,count in (("h02",2),("h03",3)):
            p=arm+"_"
            r=v(p+"R_integral")
            if r < -ABS:raise AssertionError(f"negative {arm} progress at {i}")
            if r>ABS:positive_rates[arm.upper()]+=1
            close(v(p+"om_sink_integral"),-r,arm+" negative ion sink")
            close(v(p+"positive_sink_integral"),-r,arm+" positive ion sink")
            close(v(p+"o_mass_integral"),count*M_O*r,arm+" atomic O")
            close(v(p+"neutral_mass_integral"),count*M_O*r,arm+" neutral mass")
            close(v(p+"mass_closure_integral"),0,arm+" mass closure")
            close(v(p+"charge_closure_integral"),0,arm+" charge closure")
            rates[arm]=r
            sinks.append(v(p+"om_sink_integral"))
            o_source+=v(p+"o_mass_integral")
        close(sum(sinks),-(rates["h02"]+rates["h03"]),"total O- loss")
        close(o_source,M_O*(2*rates["h02"]+3*rates["h03"]),"total O3P production")
        # Confirm retained B-case and both dissociation reaction owners are finite.
        for k in ("edetach_R_integral","diss_R_integral","mixed_R_integral"):
            if v(k) < -ABS:raise AssertionError(f"negative {k} at {i}")
    result={
      "case":"B+H02+H03","status":"PASS","science_acceptance":"HOLD",
      "base_B_case":"Ground+Mixed+electron-impact O- detachment",
      "heavy_channels":["H02","H03"],
      "target_power_W":1000,"initial_O3P_number_density_m3":5e18,
      "detachment_loss_eV_event":1.4611,
      "source_base_sha":"aa81c1ca1d52e9431b56682b227fe96aa3a305cd",
      "time_points":len(rows),"last_time_us":float(rows[-1]["time"])*1e6,
      "last_rate_H02_mol_s":float(rows[-1]["h02_R_integral"]),
      "last_rate_H03_mol_s":float(rows[-1]["h03_R_integral"]),
      "last_total_Om_neutralization_mol_s":float(rows[-1]["h02_R_integral"])+float(rows[-1]["h03_R_integral"]),
      "positive_rate_samples":positive_rates,
      "mass_and_charge_closure":"PASS",
      "electron_energy_heavy_reactions":"zero direct electron impact; heavy energetics HOLD"
    }
    output=args.result/"diagnostics"/"B_plus_H02_H03_combined_audit.json"
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    print(json.dumps(result,indent=2,allow_nan=False))
    print("ISSUE395_B_PLUS_H02_H03_COMBINED_P5_PASS")

if __name__=="__main__":main()
