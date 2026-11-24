"""Observe exact historical consumer P2, never infer global deletion safety."""
import ast
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import traceback

root=Path(sys.argv[1]).resolve()
out=Path(sys.argv[2]).resolve()
out.mkdir(parents=True,exist_ok=True)
mode=sys.argv[3]
if mode not in ('stage','native'):raise ValueError('mode must be stage or native')
if mode=='stage':
    sys.path.insert(0,str(root))
    from physics_harness.execution.cases import stage_case, referenced_file_parameters
    from physics_harness.adapters.moose import parameters as mp

exe=root/"physics_app/physics-opt"
work=root/".code4_historical_reachability"
if mode=='stage':work.mkdir()
target="PhysicsFVElectrostaticDrift"
types=re.compile(r"(?m)^\s*type\s*=\s*([A-Za-z_][A-Za-z_0-9]*)\s*(?:#.*)?$")
result={"schema":"code4.historical.reachability.additional.v1","source_sha":subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip(),"source_tree":subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD^{tree}"],text=True).strip(),"binary_sha256":hashlib.sha256(exe.read_bytes()).hexdigest(),"additional_builds":0,"safe_delete":"HOLD","cases":{}}
def require(ok,msg):
    if not ok:raise RuntimeError(msg)
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def inventory(case):
    files={}
    for path in sorted(case.rglob("*")):
        require(not path.is_symlink(),"symlink in staged case: "+str(path))
        if path.is_file():
            files[path.relative_to(case).as_posix()]=sha(path)
    return files
def save():
    filename="stage_manifest.json" if mode=="stage" else "result.json"
    (out/filename).write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
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
        require(str(root) not in raw.decode(),"host absolute path embedded in input")
        rec["deck"]=deck.relative_to(case).as_posix()
        rec["files"]=inventory(case)
        refs=[]
        for ref in referenced_file_parameters(raw.decode(),case,skip_dynamic=True):
            path=Path(ref["resolved"])
            require(path.is_relative_to(root),"reference escapes checkout: "+str(path))
            require(not Path(ref["raw"]).is_absolute(),"nonportable absolute reference: "+ref["raw"])
            refs.append({"parameter":ref["parameter"],"raw":ref["raw"],"path":path.relative_to(root).as_posix(),"sha256":sha(path) if path.is_file() else None})
        rec["literal_file_references"]=refs
        print(name,"STAGED",counts[target],"instances",len(rec["files"]),"files",flush=True)
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

def e2a(case,mode):
    from experiments.Issue26_electron_energy.E2a_controlled_diffusion.run import _stage_case, CASE_DIFFUSIVITIES
    d=CASE_DIFFUSIVITIES[mode]
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

def load_builder(relative):
    path=root/relative
    prefix=[]
    relocated=0
    for node in ast.parse(path.read_text()).body:
        if not isinstance(node,(ast.Import,ast.ImportFrom,ast.Assign,ast.AnnAssign,ast.FunctionDef)):
            raise RuntimeError("unreviewed top-level builder declaration")
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="ROOT" for t in node.targets):
            require(isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Name) and node.value.func.id=="Path" and len(node.value.args)==1 and isinstance(node.value.args[0],ast.Constant) and node.value.args[0].value=="/workspace","unexpected root declaration")
            node.value.args[0]=ast.copy_location(ast.Constant(str(root)),node.value.args[0])
            relocated+=1
        prefix.append(node)
        if isinstance(node,ast.FunctionDef) and node.name=="build_case":break
    require(relocated==1 and isinstance(prefix[-1],ast.FunctionDef) and prefix[-1].name=="build_case","builder scope/ROOT identity")
    ns={"__name__":"code4_historical_stage","__file__":str(path)}
    exec(compile(ast.fix_missing_locations(ast.Module(body=prefix,type_ignores=[])),str(path),"exec"),ns)
    return ns

def wall(case,enabled):
    ns=load_builder(".github/scripts/issue213_wall_drift.py")
    text,meta=ns["build_case"](wall_drift=enabled,dt=ns["BASELINE_DT"])
    return staged(case,ns["SOURCE"],text)

def sheath(case,enabled):
    ns=load_builder("experiments/Issue27_surface_reactions/controlled_wall/issue215_sheath_particle_core.py")
    text,meta=ns["build_case"](sheath=enabled,dt=ns["BASELINE_DT"])
    return staged(case,ns["SOURCE"],text)

# Scope: the three previously unobserved direct/indirect Issue193 owners.
# Run original construction/staging only, never the historical runtime loop.
OWNER_BLOBS = {
    "experiments/Issue193_a8_see_acceptance/run.py": "08bb930fcbc3e2c7506e39dcba56c73347791d34",
    ".github/scripts/issue194_a7_multistep.py": "21f8fa3f1097636c53de21dde6b4e54c52f29d79",
    ".github/scripts/issue200_h6_nonlinear_control.py": "3ad59d903019ce00346be343f947dd9272d6dfa1",
}

def verify_owner(relative):
    path=root/relative
    data=path.read_bytes()
    digest=hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()
    require(digest==OWNER_BLOBS[relative],"historical owner blob mismatch: "+relative)
    return path

def stage_193(case,which):
    verify_owner("experiments/Issue193_a8_see_acceptance/run.py")
    from experiments.Issue193_a8_see_acceptance import run as a
    params=a.load_experiment_spec(a.A8_SPEC).parameters
    a.a8._stage_case(case,parameters=params,mode=which)
    deck=case/"input.i"
    promoted,_=a._promote_current_acceptance_types(deck.read_text(encoding="utf-8"))
    deck.write_text(promoted,encoding="utf-8")
    return deck

def load_multistep(relative):
    path=verify_owner(relative)
    prefix=[]
    relocated=0
    for node in ast.parse(path.read_text()).body:
        # Exact reviewed blob; only declaration prefix through original stage().
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="ROOT" for t in node.targets):
            require(isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Name) and node.value.func.id=="Path" and len(node.value.args)==1 and isinstance(node.value.args[0],ast.Constant) and node.value.args[0].value=="/workspace","unexpected ROOT")
            node.value.args[0]=ast.copy_location(ast.Constant(str(root)),node.value.args[0])
            relocated+=1
        if isinstance(node,ast.Expr):
            # Only the two original output-directory mkdir calls in Issue194.
            require(isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Attribute) and node.value.func.attr=="mkdir" and isinstance(node.value.func.value,ast.Name) and node.value.func.value.id in {"CASES","LOGS"},"unexpected expression")
            continue
        require(isinstance(node,(ast.Import,ast.ImportFrom,ast.Assign,ast.AnnAssign,ast.FunctionDef)),"unexpected declaration")
        prefix.append(node)
        if isinstance(node,ast.FunctionDef) and node.name=="stage":break
    require(relocated==1 and isinstance(prefix[-1],ast.FunctionDef) and prefix[-1].name=="stage","stage prefix identity")
    ns={"__name__":"code4_historical_stage","__file__":str(path)}
    exec(compile(ast.fix_missing_locations(ast.Module(body=prefix,type_ignores=[])),str(path),"exec"),ns)
    ns["CASES"]=work
    return ns

def stage_multistep(case,owner,family,index):
    relative=".github/scripts/issue194_a7_multistep.py" if owner==194 else ".github/scripts/issue200_h6_nonlinear_control.py"
    ns=load_multistep(relative)
    if family=="a6_matched_ledger":
        text,meta=ns["a6"]._build_a6_case_input(ns["base_text"],parameters=ns["a7"]._a6_parameters(ns["params"]),mode="comsol_wall")
    else:
        text,meta=ns["a7"]._build_a7_case_input(ns["base_text"],parameters=ns["params"],mode=family)
    if owner==194:
        require(len(ns["ALL_DTS"])==3,"unexpected Issue194 dt inventory")
        ns["stage"](case.name,text,meta,dt=ns["ALL_DTS"][index])
    else:
        require(len(ns["CONTROLS"])==4,"unexpected Issue200 control inventory")
        ns["stage"](case.name,text,meta,ns["CONTROLS"][index])
    return case/"input.i"

def observe():
    manifest=out/"stage_manifest.json"
    require(sha(manifest)==os.environ["STAGE_SHA256"],"stage manifest digest mismatch")
    staged_result=json.loads(manifest.read_text())
    for field in ("schema","source_sha","source_tree","binary_sha256","target_registered_in_source"):
        require(staged_result[field]==result[field],"stage/native mismatch: "+field)
    require(set(staged_result["cases"])==expected,"stage case inventory mismatch")
    result["stage_manifest_sha256"]=sha(manifest)
    result["cases"]=staged_result["cases"]
    save()
    for name,rec in result["cases"].items():
        if rec["state"]!="STAGED":continue
        folder=out/name
        case=work/name
        try:
            require(inventory(case)==rec["files"],"staged file inventory changed")
            deck=case/rec["deck"]
            require(sha(deck)==rec["input_sha256"],"input digest mismatch")
            for ref in rec["literal_file_references"]:
                path=root/ref["path"]
                require(path.resolve().is_relative_to(root),"reference escapes checkout")
                require((sha(path) if path.is_file() else None)==ref["sha256"],"referenced file changed: "+ref["path"])
            p=subprocess.run([str(exe),"--check-input","-i",deck.name],cwd=case,text=True,capture_output=True,timeout=150)
            log=p.stdout+p.stderr
            (folder/"P2.log").write_text(log)
            rec.update({"state":"OBSERVED","P2_returncode":p.returncode,"P2":"PASS" if p.returncode==0 and "Syntax OK" in log else "FAIL","diagnostic_type_mentions":[t for t in sorted(rec["type_counts"]) if t in log],"target_mentioned":target in log})
            print(name,"instances",rec["target_instances"],"P2",rec["P2"],flush=True)
        except Exception as err:
            rec.update({"state":"INCOMPLETE","error":repr(err)})
            (folder/"native_exception.log").write_text(traceback.format_exc())
            print(name,"INCOMPLETE",repr(err),flush=True)
        save()

specs=[("193_see_off",lambda case:stage_193(case,"see_off")),("193_see_on",lambda case:stage_193(case,"see_on"))]
for owner,count in ((194,3),(200,4)):
    for family in ("a6_matched_ledger","electron_thermal_only","combined_thermal"):
        for index in range(1 if family=="a6_matched_ledger" else count):
            specs.append((f"{owner}_{family}_{index}",lambda case,owner=owner,family=family,index=index:stage_multistep(case,owner,family,index)))
expected={name for name,_ in specs}
require(len(expected)==18,"additional case inventory")
if mode=="stage":
    for name,prepare in specs:
        run(name,prepare)
    require(set(result["cases"])==expected,"stage case inventory mismatch")
    result["status"]="STAGED" if all(x["state"]=="STAGED" for x in result["cases"].values()) else "STAGE_INCOMPLETE"
    save()
    print("CODE4_STAGE="+result["status"],flush=True)
    # Keep per-case staging failures; native still observes every staged case.
else:
    observe()
    result["status"]="OBSERVED" if set(result["cases"])==expected and all(x["state"]=="OBSERVED" for x in result["cases"].values()) else "INCOMPLETE"
    save()
    print("CODE4_HISTORICAL_REACHABILITY="+result["status"],flush=True)
    sys.exit(0 if result["status"]=="OBSERVED" else 1)
