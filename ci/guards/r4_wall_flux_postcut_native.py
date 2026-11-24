"""Exact post-cut W1 native checks, no general science or retirement acceptance."""
import csv
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys

root=Path(sys.argv[1]).resolve()
out=Path(sys.argv[2]).resolve()
out.mkdir(parents=True,exist_ok=True)
exe=root/"physics_app/physics-opt"
d4=root/"experiments/Issue3_dielectric_surface_charge"
result={"schema":"r4.postcut.v1","status":"HOLD","source_sha":subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip(),"source_tree":subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD^{tree}"],text=True).strip(),"binary_sha256":hashlib.sha256(exe.read_bytes()).hexdigest(),"additional_builds":0,"cases":{}}
def save():
    (out/"result.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
def require(ok,msg):
    if not ok: raise RuntimeError(msg)
def load(name):
    spec=importlib.util.spec_from_file_location(name,d4/(name+".py"))
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
def run(name,source,negative=False):
    case=out/name
    case.mkdir()
    deck=case/"input.i"
    deck.write_text(source)
    rec={"input_sha256":hashlib.sha256(deck.read_bytes()).hexdigest()}
    result["cases"][name]=rec
    save()
    for phase,args in [("P2",["--check-input"]),("P3",[])]:
        proc=subprocess.run([str(exe),*args,"-i",deck.name],cwd=case,text=True,capture_output=True,timeout=180)
        log=proc.stdout+proc.stderr
        (case/(phase+".log")).write_text(log)
        rec[phase]="PASS" if proc.returncode==0 and (phase!="P2" or "Syntax OK" in log) else "FAIL"
        save()
        print(name,phase,rec[phase],flush=True)
        if negative:
            require(phase=="P2" and proc.returncode!=0 and "PhysicsFVElectronEnergyWallFluxBC" in log and ("not a registered" in log or "not registered" in log or "not found" in log or "not a known" in log),"removed Factory negative not attributable")
            rec["retired_factory_rejected"]=True
            save()
            return None
        require(rec[phase]=="PASS",name+" "+phase)
    return case/"input_out.csv"
def rows(path,end):
    with path.open(newline="") as f:r=list(csv.DictReader(f))
    require(len(r)>=2,"missing INITIAL/final")
    require(math.isclose(float(r[0]["time"]),0.,abs_tol=1e-14),"initial time")
    require(math.isclose(float(r[-1]["time"]),end,rel_tol=1e-10),"final time")
    return r
try:
    require(not (root/"physics_app/src/fvbcs/PhysicsFVElectronEnergyWallFluxBC.C").exists(),"C source present")
    require(not (root/"physics_app/include/fvbcs/PhysicsFVElectronEnergyWallFluxBC.h").exists(),"header present")
    smoke=(root/"physics_app/ci/electron_energy_wall_smoke.i").read_text()
    require("PhysicsFVElectronEnergyWallFluxBC" not in smoke,"old BC remains")
    r=rows(run("external_wall",smoke),1e-8)
    beta=(5./6.)*math.sqrt(16.*1.602176634e-19*5./(3.*math.pi*9.1093837139e-31))
    for key,gs in [("energy_thermal_avg",0.),("energy_see_avg",100000.)]:
        w0=5e16
        wf=(w0+1e-8*4.*gs)/(1.+1e-8*beta)
        require(math.isclose(float(r[0][key]),w0,rel_tol=5e-8),"external initial")
        require(math.isclose(float(r[-1][key]),wf,rel_tol=5e-8),"external oracle")
    result["external_oracle"]="PASS"
    gen=load("prepare_d4_see_energy")
    oracle=load("analyze_d4_see_energy")
    measured={}
    for name,gs in gen.CASES.items():
        deck=gen.build(gs)
        require("PhysicsFVElectronEnergyWallFluxBC" not in deck and "PhysicsFVLogMolarElectronTimeDerivative" in deck,"wrong state")
        path=run(name,deck)
        rows(path,gen.DT)
        rec=oracle.evaluate(path,gs)
        result["cases"][name]["oracle"]=rec
        require(all(rec["checks"].values()),name+" inventory/ledger")
        measured[name]=oracle.read(path)[1]
    expected=oracle.analytic(gen.CASES["see_on"])["final_energy_inventory_eV_m3"]-oracle.analytic(gen.CASES["see_off"])["final_energy_inventory_eV_m3"]
    delta=measured["see_on"]-measured["see_off"]
    require(delta>0 and math.isclose(delta,expected,rel_tol=oracle.REL_TOL),"SEE delta")
    result["see_delta"]={"actual":delta,"expected":expected}
    original=(root/"docs/provenance/issue713_r4_wall_energy/physics_app/ci/electron_energy_wall_smoke.i.txt").read_text()
    run("retired_factory_negative",original,negative=True)
    result["status"]="PASS_BOUNDED"
except Exception as err:
    result["error"]=repr(err)
finally:
    save()
    print("R4_POSTCUT="+result["status"])
sys.exit(0 if result["status"]=="PASS_BOUNDED" else 1)
