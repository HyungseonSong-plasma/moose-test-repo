"""Observe exact historical consumer P2, never infer global deletion safety."""
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import traceback

root=Path(sys.argv[1]).resolve()
out=Path(sys.argv[2]).resolve()
out.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(root))
from physics_harness.execution.cases import stage_case
from physics_harness.adapters.moose import parameters as mp

exe=root/"physics_app/physics-opt"
work=root/".code4_historical_reachability"
work.mkdir()
target="PhysicsFVElectrostaticDrift"
types=re.compile(r"(?m)^\s*type\s*=\s*([A-Za-z_][A-Za-z_0-9]*)\s*(?:#.*)?$")
result={"schema":"code4.historical.reachability.v1","source_sha":subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip(),"source_tree":subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD^{tree}"],text=True).strip(),"binary_sha256":hashlib.sha256(exe.read_bytes()).hexdigest(),"additional_builds":0,"safe_delete":"HOLD","cases":{}}
def save():
    (out/"result.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
registered=set()
for p in (root/"physics_app/src").rglob("*.C"):
    registered.update(re.findall(r'registerMooseObject\s*\(\s*"PhysicsApp"\s*,\s*(\w+)\s*\)',p.read_text()))
result["target_registered_in_source"]=target in registered
def run(name,prepare):
    rec={"state":"STAGING"}
    result["cases"][name]=rec
    save()
    case=work/name
    folder=out/name
    folder.mkdir()
    try:
        deck=prepare(case)
        raw=deck.read_bytes()
        (folder/"input.i").write_bytes(raw)
        counts=Counter(types.findall(raw.decode()))
        rec.update({"state":"STAGED","input_sha256":hashlib.sha256(raw).hexdigest(),"type_counts":dict(counts),"target_instances":counts[target],"unregistered_physics_types_from_source":sorted(t for t in counts if t.startswith(("Physics","QPX")) and t not in registered)})
        save()
        p=subprocess.run([str(exe),"--check-input","-i",deck.name],cwd=case,text=True,capture_output=True,timeout=150)
        log=p.stdout+p.stderr
        (folder/"P2.log").write_text(log)
        rec.update({"state":"OBSERVED","P2_returncode":p.returncode,"P2":"PASS" if p.returncode==0 and "Syntax OK" in log else "FAIL","diagnostic_type_mentions":[t for t in sorted(counts) if t in log],"target_mentioned":target in log})
        print(name,"instances",counts[target],"P2",rec["P2"],flush=True)
    except Exception as err:
        rec.update({"state":"INCOMPLETE","error":repr(err)})
        (folder/"exception.log").write_text(traceback.format_exc())
        print(name,"INCOMPLETE",repr(err),flush=True)
    save()

def s5r(case):
    from physics_app.ci import check_stage5_s5r_assembly as s
    case.mkdir()
    deck,meta=s._stage(case)
    return deck

def e2a(case,d):
    from experiments.Issue26_electron_energy.E2a_controlled_diffusion.run import _stage_case
    from experiments.Issue282_e2a_rz_bridge.research_type_bridge import project_historical_registration_only
    _stage_case(case,diffusivity_m2_s=d)
    deck=case/"input.i"
    original=deck.read_bytes()
    (out/case.name/"input.historical.i").write_bytes(original)
    projected,receipt=project_historical_registration_only(original.decode())
    deck.write_text(projected)
    (out/case.name/"bridge.json").write_text(json.dumps(receipt,indent=2,sort_keys=True))
    return deck

def staged(case,source,text):
    stage_case(source,case,input_text=text,purge_directory_names=(".jitcache","checkpoint","checkpoints"),purge_patterns=("input_out*","*.log","*.e","*.exo"))
    return case/"input.i"

def h3(case,charge,field):
    path=root/".github/scripts/issue197_h3_migration_audit.py"
    names={"replace_scalar","current_runtime_input"}
    funcs=[n for n in ast.parse(path.read_text()).body if isinstance(n,ast.FunctionDef) and n.name in names]
    if {n.name for n in funcs}!=names:raise RuntimeError("H3 function identity")
    src=root/"experiments/Issue1_reactor_o2plus_integration/migration_only_exact_phi_ic"
    ns={"SOURCE":src,"re":re,"mp":mp}
    exec(compile(ast.Module(body=funcs,type_ignores=[]),str(path),"exec"),ns)
    text,_=ns["current_runtime_input"](charge_number=charge,field_sign=field)
    return staged(case,src,text)

def wall(case,enabled):
    path=root/".github/scripts/issue213_wall_drift.py"
    prefix=[]
    for node in ast.parse(path.read_text()).body:
        if not isinstance(node,(ast.Import,ast.ImportFrom,ast.Assign,ast.AnnAssign,ast.FunctionDef)):
            raise RuntimeError("unreviewed top-level wall declaration")
        prefix.append(node)
        if isinstance(node,ast.FunctionDef) and node.name=="build_case":break
    if not isinstance(prefix[-1],ast.FunctionDef) or prefix[-1].name!="build_case":raise RuntimeError("missing wall builder")
    ns={"__name__":"code4_historical_wall_stage","__file__":str(path)}
    exec(compile(ast.Module(body=prefix,type_ignores=[]),str(path),"exec"),ns)
    text,meta=ns["build_case"](wall_drift=enabled,dt=ns["BASELINE_DT"])
    return staged(case,ns["SOURCE"],text)

def sheath(case,enabled):
    from experiments.Issue27_surface_reactions.controlled_wall import issue215_sheath_particle_core as s
    text,meta=s.build_case(sheath=enabled,dt=s.BASELINE_DT)
    return staged(case,s.SOURCE,text)

run("S5R",s5r)
from experiments.Issue26_electron_energy.E2a_controlled_diffusion.run import CASE_DIFFUSIVITIES
for name,d in CASE_DIFFUSIVITIES.items():
    run("E2a_"+name,lambda case,d=d:e2a(case,d))
run("H3_positive",lambda case:h3(case,1,1))
run("H3_negative",lambda case:h3(case,-1,1))
run("wall_drift_off",lambda case:wall(case,False))
run("wall_drift_on",lambda case:wall(case,True))
run("sheath_control",lambda case:sheath(case,False))
run("sheath_primary",lambda case:sheath(case,True))
result["status"]="OBSERVED" if all(x["state"]=="OBSERVED" for x in result["cases"].values()) else "INCOMPLETE"
save()
print("CODE4_HISTORICAL_REACHABILITY="+result["status"])
sys.exit(0 if result["status"]=="OBSERVED" else 1)
