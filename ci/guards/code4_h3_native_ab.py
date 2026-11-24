"""H3 actual signed-wall control, bounded raw-FV substitution only."""
import ast
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import traceback

root=Path(sys.argv[1]).resolve()
out=Path(sys.argv[2]).resolve()
mode=sys.argv[3]
exe=root/"physics_app/physics-opt"
work=root/".code4_h3_ab"
def require(ok,msg):
    if not ok:raise RuntimeError(msg)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def git(*a):return subprocess.check_output(["git","-C",str(root),*a],text=True).strip()
identity={"source_sha":git("rev-parse","HEAD"),"source_tree":git("rev-parse","HEAD^{tree}"),"binary_sha256":sha(exe),"additional_builds":0}
def inventory(path):
    files={}
    for p in sorted(path.rglob("*")):
        require(not p.is_symlink(),"symlink")
        if p.is_file():files[p.relative_to(path).as_posix()]=sha(p)
    return files
oldblock="""    type = PhysicsFVElectrostaticDrift
    variable = w_O2_plus
    potential = phi
    mobility = ion_mobility
    carrier = rho
    charge_number = ${z_i}
    advected_interp_method = upwind
    boundaries_to_avoid = 'left right'""".replace("\\$","$")
def candidate(text,z,field):
    # Match actual H3 constants and solved, uncharged linear potential.
    for line in ("rho0 = 1","mu_i = 0.01","xmin = 0.0","xmax = 1.0","nx = 100","initial_condition = 1.0e-6","sticking = 0","type = FVDiffusion","coeff = relative_permittivity","prop_values = '${rho0} ${mu_i} ${T_g} 1.0'".replace("\\$","$")):
        require(line in text,"H3 precondition "+line)
    require(text.count("type = PhysicsFVElectrostaticDrift")==1 and text.count(oldblock)==1,"exact raw drift block")
    require("z_i = "+str(z)+"\n" in text,"charge")
    phi_left=20000 if field>0 else 0
    phi_right=0 if field>0 else 20000
    require("phi_left = "+str(phi_left)+"\n" in text and "phi_right = "+str(phi_right)+"\n" in text,"field")
    require(("expression = '20000*(1-x)'" if field>0 else "expression = '20000*x'") in text,"linear IC")
    velocity=z*0.01*(phi_left-phi_right)
    replacement=f"""    type = FVAdvection
    variable = w_O2_plus
    velocity = '{velocity:.17g} 0 0'
    advected_interp_method = upwind
    boundaries_to_avoid = 'left right'"""
    changed=text.replace(oldblock,replacement)
    require(changed.replace(replacement,oldblock)==text,"inverse mutation")
    return changed,velocity
pairs={}
if mode=="stage":
    sys.path.insert(0,str(root))
    from physics_harness.execution.cases import stage_case
    from physics_harness.adapters.moose import parameters as mp
    src=root/"experiments/Issue1_reactor_o2plus_integration/migration_only_exact_phi_ic"
    driver=root/".github/scripts/issue197_h3_migration_audit.py"
    require(git("hash-object",str(driver))=="36d34743ffa0806cee990b3c0801d751dd8d5536","driver identity")
    names={"replace_scalar","current_runtime_input"}
    funcs=[n for n in ast.parse(driver.read_text()).body if isinstance(n,ast.FunctionDef) and n.name in names]
    require({n.name for n in funcs}==names,"builder identity")
    ns={"SOURCE":src,"re":re,"mp":mp}
    exec(compile(ast.Module(body=funcs,type_ignores=[]),str(driver),"exec"),ns)
    work.mkdir()
    for z in (1,-1):
        for field in (1,-1):
            name=f"z{z:+d}_E{field:+d}"
            text,_=ns["current_runtime_input"](charge_number=z,field_sign=field)
            new,v=candidate(text,z,field)
            if field==1:
                expected="c33f58b521f9258f1967a5e60b821ca0505550ac8503fe057224484b4a9d5a9a" if z==1 else "9e942225dee3de31d587e477b9f59cb9d3063986c27655bff9e17313a6b9c0a5"
                require(hashlib.sha256(text.encode()).hexdigest()==expected,"previous H3 input drift")
            rec={"charge":z,"field_sign":field,"velocity":v,"cases":{}}
            for label,deck in (("old",text),("new",new)):
                path=work/name/label
                path.parent.mkdir(exist_ok=True)
                stage_case(src,path,input_text=deck,purge_directory_names=(".jitcache","checkpoint","checkpoints"),purge_patterns=("input_out*","*.log","*.e","*.exo"))
                folder=out/name/label
                folder.mkdir(parents=True)
                (folder/"input.i").write_text(deck)
                rec["cases"][label]={"files":inventory(path)}
            pairs[name]=rec
    (out/"stage_manifest.json").write_text(json.dumps({**identity,"pairs":pairs},indent=2,sort_keys=True)+"\n")
    print("H3_STAGE=8",flush=True)
    sys.exit(0)

require(mode=="native","mode")
manifest=out/"stage_manifest.json"
require(sha(manifest)==os.environ["STAGE_SHA256"],"manifest digest")
staged=json.loads(manifest.read_text())
require(all(staged[k]==v for k,v in identity.items()),"stage native identity")
pairs=staged["pairs"]
require(len(pairs)==4,"pair count")
result={**identity,"status":"HOLD","safe_delete":"HOLD","scope":"actual H3 four sign combinations only","pairs":pairs}
def save():
    (out/"result.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
def rel(a,b):
    return abs(a-b)/max(abs(a),abs(b),1e-300)
def solve(name,label,rec):
    path=work/name/label
    folder=out/name/label
    require(inventory(path)==rec["files"],"stage drift")
    for phase,flags in (("P2",["--check-input"]),("P3",[])):
        p=subprocess.run([str(exe),*flags,"-i","input.i"],cwd=path,text=True,capture_output=True,timeout=180)
        log=p.stdout+p.stderr
        (folder/(phase+".log")).write_text(log)
        ok=p.returncode==0 and (phase!="P2" or "Syntax OK" in log)
        rec[phase]="PASS" if ok else "FAIL"
        save()
        require(ok,name+" "+label+" "+phase)
    data=path/"input_out.csv"
    (folder/"input_out.csv").write_bytes(data.read_bytes())
    with data.open(newline="") as f:rows=[{k:float(v) for k,v in row.items()} for row in csv.DictReader(f)]
    require(len(rows)==2 and rows[0]["time"]==0 and math.isclose(rows[1]["time"],1e-5,rel_tol=1e-10),"time grid")
    require(all(math.isfinite(v) for row in rows for v in row.values()),"nonfinite")
    return rows
def oracle(rows,velocity):
    r0,r1=rows
    active="right" if velocity>0 else "left"
    inactive="left" if velocity>0 else "right"
    for row in rows:
        require(row[active+"_migration_mass_loss_rate"]>0 and abs(row[inactive+"_migration_mass_loss_rate"])<=1e-20,"wall direction/clamp")
        for side in ("left","right"):require(abs(row[side+"_surface_mass_loss_rate"])<=1e-20,"surface ownership")
    f0=r0[active+"_migration_mass_loss_rate"]
    f1=r1[active+"_migration_mass_loss_rate"]
    dm=r1["ion_mass_inventory"]-r0["ion_mass_inventory"]
    ledger=rel(dm,-f1*1e-5)
    require(rel(f0,1e-6*abs(velocity))<=1e-3 and ledger<=1e-8,"H3 independent wall ledger")
    # Independent raw 100-cell implicit upwind finite-volume recurrence, no
    # external inflow, outgoing wall mass owner once. Validate first moment.
    c=abs(velocity)*1e-5/0.01
    w=[]
    upstream=0.
    for i in range(100):
        value=(1e-6+c*upstream)/(1+c)
        w.append(value)
        upstream=value
    if velocity<0:w.reverse()
    moment=sum(x*(i+.5)*.01*.01 for i,x in enumerate(w))
    measured=r1["ion_mass_first_moment"]
    err=rel(measured,moment)
    require(err<=1e-5,"independent first moment")
    return {"active_wall":active,"initial_flux_error":rel(f0,1e-6*abs(velocity)),"mass_ledger_error":ledger,"moment_error":err,"moment_expected":moment}
try:
    for name,rec in pairs.items():
        z=rec["charge"];field=rec["field_sign"];v=rec["velocity"]
        require(v==z*field*200,"velocity identity")
        old=solve(name,"old",rec["cases"]["old"])
        new=solve(name,"new",rec["cases"]["new"])
        for label,rows in (("old",old),("new",new)):rec["cases"][label]["oracle"]=oracle(rows,v)
        errors={}
        require(len(old)==len(new),"row count")
        for a,b in zip(old,new):
            require(a.keys()==b.keys(),"CSV schema")
            for k in a:
                error=abs(a[k]-b[k])/max(abs(a[k]),abs(b[k]),1e-20)
                require(math.isclose(a[k],b[k],rel_tol=1e-8,abs_tol=1e-18),"A/B "+name+" "+k)
                errors[k]=max(errors.get(k,0.),error)
        rec["parity_errors"]=errors
        print(name,"P2/P3 A/B PASS",flush=True)
        save()
    result["status"]="PASS_BOUNDED"
except Exception as exc:
    result["error"]=repr(exc)
    (out/"exception.log").write_text(traceback.format_exc())
finally:save()
print("H3_AB="+result["status"],flush=True)
sys.exit(0 if result["status"]=="PASS_BOUNDED" else 1)
