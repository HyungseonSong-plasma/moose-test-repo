"""Exact post-cut molar positive, normalized positive and retired parameter negatives."""
import csv
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

root=Path(sys.argv[1]).resolve()
out=Path(sys.argv[2]).resolve()
out.mkdir(parents=True,exist_ok=True)
exe=root/"physics_app/physics-opt"
result={"schema":"r5a.postcut.v1","status":"HOLD","safe_delete":False,"source_sha":subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip(),"source_tree":subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD^{tree}"],text=True).strip(),"binary_sha256":hashlib.sha256(exe.read_bytes()).hexdigest(),"additional_builds":0,"cases":{}}
def save():
    (out/"result.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
def require(ok,msg):
    if not ok:raise RuntimeError(msg)
def run(name,s,negative=False):
    work=out/name
    work.mkdir()
    deck=work/"input.i"
    deck.write_text(s)
    rec={"input_sha256":hashlib.sha256(deck.read_bytes()).hexdigest()}
    result["cases"][name]=rec
    save()
    for phase,flags in [("P2",["--check-input","--error-unused"]),("P3",[])]:
        proc=subprocess.run([str(exe),*flags,"-i",deck.name],cwd=work,text=True,capture_output=True,timeout=180)
        log=proc.stdout+proc.stderr
        (work/(phase+".log")).write_text(log)
        if negative:
            require(phase=="P2" and proc.returncode!=0 and "physical_eV_state" in log and any(t in log.lower() for t in ("unused","unknown","unrecognized","invalid parameter")),"retired parameter negative not attributable")
            rec["retired_parameter_rejected"]=True
            save()
            print(name,"P2 EXPECTED_REJECTION",flush=True)
            return
        ok=proc.returncode==0 and (phase!="P2" or "Syntax OK" in log)
        rec[phase]="PASS" if ok else "FAIL"
        save()
        print(name,phase,rec[phase],flush=True)
        require(ok,name+" "+phase)
    with (work/"input_out.csv").open(newline="") as f:rows=[{k:float(v) for k,v in row.items()} for row in csv.DictReader(f)]
    require(len(rows)==2 and rows[0]["time"]==0. and math.isclose(rows[-1]["time"],1e-8,rel_tol=1e-10),"time grid")
    return rows
def oracle(rows,density,w0,reference):
    t=2.*5.73276/3.
    speed=math.sqrt(8.*1.602176634e-19*t/(math.pi*9.1093837139e-31))
    errors={}
    for field,phi in [("energy_zero_avg",0.),("energy_cell_avg",10.)]:
        loss=1e-8*.25*density*speed*math.exp(-phi/t)*(2*t+phi)/reference
        expected=w0-loss
        require(math.isclose(rows[0][field],w0,rel_tol=5e-8),"initial "+field)
        rel=abs(rows[-1][field]-expected)/w0
        ledger=abs(rows[-1][field]-rows[0][field]+loss)/loss
        require(rel<=5e-8 and ledger<=5e-6,"oracle "+field)
        errors[field]={"final":rows[-1][field],"expected":expected,"relative_error":rel,"ledger_error":ledger}
    require(all(math.isclose(r["potential_cell_avg"],10.,rel_tol=1e-10) for r in rows),"cell potential changed")
    return errors
try:
    smoke=(root/"physics_app/ci/electron_grounded_sheath_energy_smoke.i").read_text()
    original=(root/"docs/provenance/issue713_r5a_sheath_energy/physics_app/ci/electron_grounded_sheath_energy_smoke.i.txt").read_text()
    require(hashlib.sha256(smoke.encode()).hexdigest()=="1e2d47dce00829d3233459b884d68d5f7198ed42eebea44471769450a061a99a","qualified smoke hash")
    require("physical_eV_state" not in (root/"physics_app/src/fvbcs/PhysicsFVElectronGroundedSheathEnergyBC.C").read_text(),"old parameter remains")
    result["molar_oracle"]=oracle(run("molar",smoke),1e16,5.73276e16,1.)
    # Normalized historical branch remains supported: use unit density and a
    # non-unit reference to distinguish its division from the molar branch.
    normalized=original.replace("initial_condition = 5.73276e16","initial_condition = 2.86638").replace("prop_values = '1.0e16 5.73276 0.0 0.0'","prop_values = '1.0 5.73276 0.0 0.0'").replace("physical_eV_state = true","energy_reference_eV = 2.0")
    require(normalized.count("energy_reference_eV = 2.0")==2,"normalized deck")
    result["normalized_oracle"]=oracle(run("normalized",normalized),1.,2.86638,2.)
    run("retired_true",original,True)
    run("retired_false",original.replace("physical_eV_state = true","physical_eV_state = false").replace("physical_eV_state = false","energy_reference_eV = 1.0\n    physical_eV_state = false"),True)
    result["status"]="PASS_BOUNDED"
except Exception as exc:
    result["error"]=repr(exc)
finally:
    save()
    print("R5A_POSTCUT="+result["status"])
sys.exit(0 if result["status"]=="PASS_BOUNDED" else 1)
