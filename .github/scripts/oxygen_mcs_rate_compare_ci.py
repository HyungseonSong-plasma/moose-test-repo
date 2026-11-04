#!/usr/bin/env python3
"""Compare MCS.OUT reference rates to in-run MOOSE oxygen chemistry rates.

Inputs: selected MCS rate constants (cm3/s assumed), and existing MOOSE
mean-energy lookup directory. Output: ONLY rate ratios and error statistics.
No private lookup rows or raw rate coefficients are written or printed.
Reaction identity differences are explicitly excluded from numerical scoring.
"""
import argparse
import csv
import importlib.util
import math
from pathlib import Path

NA = 6.02214076e23
BASE = Path("experiments/Issue395_powered_chemistry_ladder")
LOOKUP = (407, 413, 414, 415, 2058, 2067, 2068, 2069, 2072, 2074, 944)
FORMULAS = (2259, 936)
NOT_SAME_PROCESS = (2073,)
ALL = LOOKUP + FORMULAS + NOT_SAME_PROCESS

def interp(table, x):
    if x < table[0][0] or x > table[-1][0]:
        return None
    for i in range(1, len(table)):
        if x <= table[i][0]:
            x0, y0 = table[i-1]
            x1, y1 = table[i]
            return y0 + (y1-y0)*(x-x0)/(x1-x0)
    return table[-1][1]

def read_table(path):
    points=[]
    for row in path.read_text().splitlines():
        clean=row.split("#",1)[0].strip()
        if not clean:
            continue
        parts=clean.split()
        if len(parts)!=2:
            raise ValueError("Bad rate table format")
        e,k=map(float,parts)
        if not math.isfinite(e) or not math.isfinite(k) or k < 0:
            raise ValueError("Nonfinite or negative rate")
        if points and e <= points[-1][0]:
            raise ValueError("Non-increasing energy grid")
        points.append((e,k))
    if len(points)!=100:
        raise ValueError("Unexpected lookup row count")
    return points

def analytical(rid, mean_energy):
    te=(2.0/3.0)*mean_energy
    if te < 1.0 or te > 7.0:
        return None
    if rid==2259:
        return 2.4e-13*(300.0/(te*11604.51812155))**0.70*1e6
    if rid==936:
        return 4.54e-15*math.exp(-4.49/te)*1e6
    raise ValueError("Formula not implemented")

def write_csv(path, rows, fields):
    with path.open("w", newline="") as stream:
        writer=csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--rate-dir", required=True, type=Path)
    p.add_argument("--mcs-csv", required=True, type=Path)
    p.add_argument("--output-dir", required=True, type=Path)
    a=p.parse_args()
    modpath=BASE/"build_oxygen_24_source_overlay.py"
    spec=importlib.util.spec_from_file_location("oxygen_lookup_validator",modpath)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    paths=mod.validate_files(a.rate_dir)
    if not set(LOOKUP).issubset(paths):
        raise ValueError("Missing reaction lookup data")
    tables={rid:read_table(paths[rid]) for rid in LOOKUP}
    if 936 in paths:
        tables[936]=read_table(paths[936])
    with a.mcs_csv.open(newline="") as f:
        cases=list(csv.DictReader(f))
    if len(cases)!=24:
        raise ValueError("Expected exactly 24 MCS cases")
    want={"case","EoverN_Td","mean_energy_eV"}|{f"EI-{rid}" for rid in ALL}
    if not want.issubset(cases[0]):
        raise ValueError("MCS reference lacks required columns")
    a.output_dir.mkdir(parents=True,exist_ok=True)
    values=[]
    summaries=[]
    for rid in ALL:
        if rid in NOT_SAME_PROCESS:
            summaries.append({"reaction":f"EI-{rid}","mode":"PROCESS_IDENTITY_HOLD",
                              "matched_points":0,"mean_absolute_relative_error_pct":"",
                              "median_ratio":"","max_absolute_relative_error_pct":""})
            continue
        mode="LOOKUP" if rid in LOOKUP else "LOOKUP" if rid in tables else "FORMULA_FALLBACK" if rid==936 else "FORMULA"
        comparisons=[]
        for case in cases:
            en=float(case["mean_energy_eV"])
            mcs=float(case[f"EI-{rid}"])
            if mcs<=0:
                continue
            if mode=="LOOKUP":
                raw=interp(tables[rid], en)
                if raw is None:
                    continue
                model=raw/NA*1e6
            else:
                model=analytical(rid,en)
                if model is None:
                    continue
            if not math.isfinite(model) or model < 0:
                raise ValueError("Invalid model rate")
            ratio=model/mcs
            rec={"reaction":f"EI-{rid}","mode":mode,"case":case["case"],
                 "EoverN_Td":case["EoverN_Td"],"mean_energy_eV":case["mean_energy_eV"],
                 "moose_over_mcs":format(ratio, ".9g")}
            values.append(rec)
            comparisons.append(ratio)
        if not comparisons:
            raise ValueError(f"Missing matched rates for EI-{rid}")
        deviations=sorted(abs(100.0*(q-1)) for q in comparisons)
        sorted_ratios=sorted(comparisons)
        n=len(sorted_ratios)
        median=(sorted_ratios[(n-1)//2]+sorted_ratios[n//2])/2.0
        summaries.append({"reaction":f"EI-{rid}","mode":mode,
            "matched_points":n,
            "mean_absolute_relative_error_pct":format(sum(deviations)/n,".7g"),
            "median_ratio":format(median,".8g"),
            "max_absolute_relative_error_pct":format(deviations[-1],".7g")})
    write_csv(a.output_dir/"rate_ratios.csv",values,
              ["reaction","mode","case","EoverN_Td","mean_energy_eV","moose_over_mcs"])
    write_csv(a.output_dir/"summary.csv",summaries,
              ["reaction","mode","matched_points","mean_absolute_relative_error_pct",
               "median_ratio","max_absolute_relative_error_pct"])
    (a.output_dir/"DATA_POLICY.txt").write_text(
        "This artifact contains ratio/statistics ONLY; private rate tables not included.\n"
        "MCS.OUT RATE CONST interpreted as cm^3/s (source unit not confirmed).\n"
        "Mean electron energies from MCS; MOOSE lookup linearly interpolated.\n"
        "EI-2073 is not source-process-equivalent; numerical comparison deliberately excluded.\n"
        "EI-2068/2069 and EI-413/414 process mappings remain scientific HOLD.\n"
        "Formula comparisons use Te=(2/3)*mean energy, Te in [1,7] eV.\n"
        "No MOOSE simulation was run; this is a rate-coefficient table comparison only.\n")
    print("MCS_RATE_COMPARISON_RESULT_WRITTEN",
          "reactions",len(summaries),"ratios",len(values),
          "ei936_mode","LOOKUP" if 936 in paths else "FORMULA_FALLBACK")

if __name__=="__main__":
    main()
