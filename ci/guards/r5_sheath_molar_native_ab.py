"""Bounded physical-eV to molar GroundedSheath energy A/B. No deletion approval."""
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
NA=6.02214076e23
N=1e16
EPS=5.73276
W0=5.73276e16
DT=1e-8
result={"schema":"r5.sheath_molar_ab.v1","status":"HOLD","source_sha":subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip(),"source_tree":subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD^{tree}"],text=True).strip(),"binary_sha256":hashlib.sha256(exe.read_bytes()).hexdigest(),"additional_builds":0,"cases":{},"safe_delete":False}
def save():
    (out/"result.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
def require(ok,msg):
    if not ok:raise RuntimeError(msg)
def replace(s,a,b,count=1):
    require(s.count(a)==count,"unexpected source count: "+a)
    return s.replace(a,b)
def molar(source):
    s=replace(source,"initial_condition = 5.73276e16",f"initial_condition = {math.log(W0/NA):.17g}",2)
    s=replace(s,"prop_names = 'n_e mean_en zero_phi zero_flux'","prop_names = 'c_e mean_en zero_phi zero_flux'")
    s=replace(s,"prop_values = '1.0e16 5.73276 0.0 0.0'",f"prop_values = '{N/NA:.17g} 5.73276 0.0 0.0'")
    s=replace(s,"electron_density = n_e","electron_density = c_e",2)
    s=replace(s,"physical_eV_state = true","molar_energy_state = true",2)
    providers=[]
    for state,pp in [("energy_zero_drop","energy_zero_avg"),("energy_cell_drop","energy_cell_avg")]:
        s=replace(s,"type = FVTimeKernel\n    variable = "+state,"type = PhysicsFVLogMolarElectronTimeDerivative\n    variable = "+state)
        s=replace(s,"type = FVDiffusion\n    variable = "+state,"type = PhysicsFVLogMolarElectronDiffusion\n    variable = "+state)
        prop=state+"_physical"
        providers.append(f"""  [{prop}]
    type = ADParsedFunctorMaterial
    property_name = {prop}
    functor_names = '{state}'
    functor_symbols = 'u'
    expression = '{NA:.17g}*exp(u)'
  []""")
        s=replace(s,"functor = "+state+"\n","functor = "+prop+"\n")
    return replace(s,"[FunctorMaterials]\n","[FunctorMaterials]\n"+"\n".join(providers)+"\n")
def run(name,source):
    work=out/name
    work.mkdir()
    deck=work/"input.i"
    deck.write_text(source)
    rec={"input_sha256":hashlib.sha256(deck.read_bytes()).hexdigest()}
    result["cases"][name]=rec
    save()
    for phase,flags in [("P2",["--check-input"]),("P3",[])]:
        proc=subprocess.run([str(exe),*flags,"-i",deck.name],cwd=work,text=True,capture_output=True,timeout=180)
        log=proc.stdout+proc.stderr
        (work/(phase+".log")).write_text(log)
        ok=proc.returncode==0 and (phase!="P2" or "Syntax OK" in log)
        rec[phase]="PASS" if ok else "FAIL"
        save()
        print(name,phase,rec[phase],flush=True)
        require(ok,name+" "+phase)
    with (work/"input_out.csv").open(newline="") as f:r=list(csv.DictReader(f))
    require(len(r)>=2 and math.isclose(float(r[0]["time"]),0.,abs_tol=1e-14) and math.isclose(float(r[-1]["time"]),DT,rel_tol=1e-10),"time contract")
    return r
def flux(phi):
    t=2.*EPS/3.
    v=math.sqrt(8.*1.602176634e-19*t/(math.pi*9.1093837139e-31))
    return .25*N*v*math.exp(-phi/t)*(2*t+phi)
def oracle(rows):
    errors={}
    for key,phi in [("energy_zero_avg",0.),("energy_cell_avg",10.)]:
        initial=float(rows[0][key]);final=float(rows[-1][key])
        expected=W0-DT*flux(phi)
        err=abs(final-expected)/W0
        ledger=abs(final-initial+DT*flux(phi))/max(abs(DT*flux(phi)),1.)
        require(math.isclose(initial,W0,rel_tol=5e-8),key+" initial")
        require(err<=5e-8,key+" analytical final")
        require(ledger<=5e-6,key+" energy ledger")
        errors[key]={"expected":expected,"actual":final,"relative_error":err,"ledger_relative_error":ledger}
    require(all(math.isclose(float(r["potential_cell_avg"]),10.,rel_tol=1e-10) for r in rows),"cell potential changed")
    require(float(rows[-1]["energy_cell_avg"])>float(rows[-1]["energy_zero_avg"]),"suppression")
    return errors
try:
    source_text=(root/"physics_app/ci/electron_grounded_sheath_energy_smoke.i").read_text()
    a=run("physical",source_text)
    candidate=molar(source_text)
    b=run("molar",candidate)
    result["physical_oracle"]=oracle(a)
    result["molar_oracle"]=oracle(b)
    require(len(a)==len(b),"row count")
    for x,y in zip(a,b):
        for key in ("time","energy_zero_avg","energy_cell_avg","potential_cell_avg"):
            require(math.isclose(float(x[key]),float(y[key]),rel_tol=5e-8,abs_tol=1e-14),"parity "+key)
    result["status"]="PASS_BOUNDED"
except Exception as e:
    result["error"]=repr(e)
finally:
    save()
    print("R5_NATIVE_AB="+result["status"])
sys.exit(0 if result["status"]=="PASS_BOUNDED" else 1)
