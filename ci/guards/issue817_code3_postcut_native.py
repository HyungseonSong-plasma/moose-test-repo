"""#817 pinned binary post-cut bounded Native P2/P3 source/charge and sign oracles."""
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
from ci.guards import issue817_code3_production_migration as gate
from physics_app.ci import check_stage5_h05_runtime as h05
from physics_app.ci import check_r2_o2_ionization_implementation as r2
ROOT = Path(__file__).resolve().parents[2]
HEAD = os.environ["SOURCE_HEAD"]
OCI = os.environ["OCI"]
NREF = 1.298e18
DT = 0.1

def digest(b):
    return hashlib.sha256(b).hexdigest()

def run_native(work, check):
    args = ["docker", "run", "--rm", "--platform", "linux/amd64",
            "--entrypoint", "/bin/bash", "--user",
            f"{os.getuid()}:{os.getgid()}", "--workdir", "/case",
            "-v", f"{ROOT}:/workspace", "-v", f"{work}:/case",
            OCI, "-lc", "set -euo pipefail; source /environment; export HOME=/case; "
            "/workspace/physics_app/physics-opt " +
            ("--check-input " if check else "") + "-i case.i"]
    p = subprocess.run(args, capture_output=True, text=True, timeout=360)
    log = p.stdout + p.stderr
    return {"rc": p.returncode, "syntax_ok": ("Syntax OK" in log) if check else None,
            "log_sha256": digest(log.encode()),
            "error_tail": log[-900:] if p.returncode else None}

def micro(sign, flipped=False):
    coef = (-1 if flipped else 1) / NREF
    mark = "-" if sign == -1 else ""
    return f"""[Mesh]
  [mesh]
    type = GeneratedMeshGenerator
    dim = 1
    nx = 1
  []
[]
[Variables]
  [n_e]
    type = MooseVariableFVReal
    initial_condition = 1
  []
[]
[FunctorMaterials]
  [source]
    type = ADParsedFunctorMaterial
    property_name = S_e_s5r
    functor_names = 'n_e'
    functor_symbols = 'q'
    expression = '{mark}{NREF:.17g}*(0.4+0.1*q)'
  []
[]
[FVKernels]
  [n_e_time]
    type = FVTimeKernel
    variable = n_e
  []
  [s5r_electron_source]
    type = FVCoupledForce
    variable = n_e
    v = S_e_s5r
    coef = {coef:.17g}
  []
[]
[Postprocessors]
  [n_e_avg]
    type = ElementAverageFunctorPostprocessor
    functor = n_e
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [S_e_avg]
    type = ElementAverageFunctorPostprocessor
    functor = S_e_s5r
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]
[Executioner]
  type = Transient
  dt = {DT:.17g}
  end_time = {DT:.17g}
  solve_type = NEWTON
[]
[Outputs]
  csv = true
  exodus = false
[]
"""

def run_case(name, source, r2_table=False):
    result={"source_sha256":digest(source.encode()),"P2":"NOT_RUN","P3":"NOT_RUN",
            "domain_closure":"NOT_RUN"}
    with tempfile.TemporaryDirectory(prefix="code3-postcut-"+name+"-") as td:
        work=Path(td)
        (work/"case.i").write_text(source)
        if r2_table:
            (work/"r2_o2_ionization_runtime_table.txt").write_text(
                "".join(f"{x:.8g} {y:.17g}\n" for x,y in r2.RATE_TABLE))
        result["P2"]=run_native(work,True)
        if result["P2"]["rc"] or not result["P2"]["syntax_ok"]:
            return result
        result["P3"]=run_native(work,False)
        if result["P3"]["rc"]:
            return result
        csvfile=work/"case_out.csv"
        with csvfile.open(newline="") as stream:
            rows=list(csv.DictReader(stream))
        if len(rows)<2 or "time" not in rows[-1]:
            raise ValueError("NO_VALID_CSV_TIMESTEP")
        result["csv_sha256"]=digest(csvfile.read_bytes())
        result["csv_rows"]=len(rows)
        if name=="H05":
            h05.validate(rows)
            result["domain_closure"]="PASS_H05"
        elif name=="R2":
            r2.validate_runtime_rows(rows)
            result["domain_closure"]="PASS_R2"
        elif name=="EI01":
            first,last=float(rows[0]["n_e_avg"]),float(rows[-1]["n_e_avg"])
            if not 0<last<first:
                raise ValueError("EI01_SIGNED_ATTACHMENT_FAIL")
            result["domain_closure"]="PASS_EI01"
        elif name.startswith("norm_"):
            sign=1 if "_positive" in name else -1
            q=float(rows[-1]["n_e_avg"])
            expected=(1+sign*DT*0.4)/(1-sign*DT*0.1)
            if "_flipped" in name:
                if abs(q-expected)<=0.04:
                    raise ValueError("WRONG_SIGN_CONTROL_NOT_DETECTED")
            elif not math.isclose(q,expected,rel_tol=1e-6,abs_tol=1e-8):
                raise ValueError("NORMALIZED_ANALYTIC_RESPONSE_MISMATCH")
            result["domain_closure"]="PASS_NORMALIZED_SIGN_ORACLE"
            result["final_n_e_hat"]=q
        else:
            raise ValueError("UNKNOWN_CASE")
    return result

def execute():
    receipt={"schema":"issue817.code3.postcut_native.v0.1","source_head":HEAD,
             "oci":OCI,"cases":{},"source_deleted":True,"main_merged":False,
             "full_s5r_runtime":"NOT_RUN_THERMAL_BLOCK",
             "coupled_ad_jacobian":"NOT_PROVEN","external_consumers":"UNRESOLVED"}
    out=ROOT/"evidence/code3_postcut_native_receipt.json"
    out.parent.mkdir(exist_ok=True)
    try:
        gate.audit(HEAD,"postcut")
        if not OCI.startswith("ghcr.io/hyungseonsong-plasma/physics-build-base@sha256:"):
            raise ValueError("OCI_NOT_PINNED")
        binary=ROOT/"physics_app/physics-opt"
        if binary.read_bytes()[:4]!=b"\x7fELF":
            raise ValueError("NO_COMPILED_POSTCUT_ELF")
        receipt["elf_sha256"]=digest(binary.read_bytes())
        h=h05.runtime_input()
        olddb=str(h05.DATABASE.resolve())
        if h.count(olddb)!=1:
            raise ValueError("H05_DB_DRIFT")
        h=h.replace(olddb,"/workspace/physics_app/data/heavy_reactions/stage5_s5e_h05_oxygen_heavy.json")
        cases=[("EI01",(ROOT/"physics_app/ci/ei01_attachment_runtime_smoke.i").read_text(),False),
               ("H05",h,False),("R2",r2.RUNTIME_INPUT,True)]
        for sign,label in ((1,"positive"),(-1,"negative")):
            cases.extend([("norm_"+label,micro(sign),False),
                          ("norm_"+label+"_flipped",micro(sign,True),False)])
        good=True
        for name,source,table in cases:
            r=run_case(name,source,r2_table=table)
            r["accepted"]=(isinstance(r["P2"],dict) and
                           r["P2"]["rc"]==0 and r["P2"]["syntax_ok"] and
                           isinstance(r["P3"],dict) and
                           r["P3"]["rc"]==0 and r["domain_closure"].startswith("PASS"))
            receipt["cases"][name]=r
            good &= bool(r["accepted"])
            out.write_text(json.dumps(receipt,sort_keys=True,indent=2)+"\n")
        receipt["status"]="PASS_BOUNDED_POSTCUT" if good else "HOLD_NATIVE_OR_CLOSURE"
    except Exception as exc:
        receipt["status"]="HOLD_EXCEPTION"
        receipt["exception"]=type(exc).__name__+":"+str(exc)[:450]
    out.write_text(json.dumps(receipt,sort_keys=True,indent=2)+"\n")
    print("ISSUE817_CODE3_POSTCUT_NATIVE="+receipt["status"])
    return 0 if receipt["status"]=="PASS_BOUNDED_POSTCUT" else 1

if __name__=="__main__":
    raise SystemExit(execute())
