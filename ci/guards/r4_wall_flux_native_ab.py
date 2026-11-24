"""Evidence-only R4 A/B, not a general FV replacement or retirement verdict."""
import csv
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import subprocess
import sys

root=Path(sys.argv[1]).resolve()
out=Path(sys.argv[2]).resolve()
out.mkdir(parents=True, exist_ok=True)
exe=root/"physics_app/physics-opt"
d4=root/"experiments/Issue3_dielectric_surface_charge"
NA=6.02214076e23
E=1.602176634e-19
ME=9.1093837139e-31
result={"schema":"r4.wall_flux_ab.v1","cases":{},"status":"HOLD","safe_delete":False,
        "source_sha":subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip(),
        "source_tree":subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD^{tree}"],text=True).strip(),
        "binary_sha256":hashlib.sha256(exe.read_bytes()).hexdigest(),"additional_builds":0}
def save():
    (out/"result.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
def module(name):
    spec=importlib.util.spec_from_file_location(name,d4/(name+".py"))
    obj=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj
gen=module("prepare_d4_see_energy")
oracle=module("analyze_d4_see_energy")
def replace_once(s,a,b):
    assert s.count(a)==1,a
    return s.replace(a,b,1)
def candidate(source,block=None,molar=False,sign="-1",see="4"):
    pattern=r"(?m)^  \[([^\]\n]+)\]\n    type = PhysicsFVElectronEnergyWallFluxBC\n    variable = (\w+)\n    boundary = (\w+)\n    electron_energy_density = (\w+)\n    mean_electron_energy = (\w+)\n    see_number_flux = (\w+)\n    state_form = physical_eV\n  \[\]"
    matches=list(re.finditer(pattern,source))
    assert matches
    materials=[]
    for match in matches:
        name,var,boundary,w,eps,gs=match.groups()
        assert var==w
        flux=name+"_outward_energy_flux"
        density="exp(w)" if molar else "w"
        injection=f"{see}*gs/{NA:.17g}" if molar else f"{see}*gs"
        expr=f"(5.0/6.0)*sqrt(16.0*{E:.17g}*eps/(3.0*3.141592653589793238462643383279502884*{ME:.17g}))*{density}-{injection}"
        lines=[f"  [{flux}]","    type = ADParsedFunctorMaterial",f"    property_name = {flux}",f"    functor_names = '{w} {eps} {gs}'","    functor_symbols = 'w eps gs'",f"    expression = '{expr}'"]
        if block is not None: lines.append(f"    block = {block}")
        lines.append("  []")
        materials.append("\n".join(lines))
        new=f"  [{name}]\n    type = FVFunctorNeumannBC\n    variable = {var}\n    boundary = {boundary}\n    functor = {flux}\n    factor = {sign}\n  []"
        source=replace_once(source,match.group(0),new)
    source=replace_once(source,"[FunctorMaterials]\n","[FunctorMaterials]\n"+"\n".join(materials)+"\n")
    assert "state_form = physical_eV" not in source
    return source
def molar_deck(source):
    s=candidate(source,block=1,molar=True)
    s=replace_once(s,f"initial_condition = {gen.W0:.17g}",f"initial_condition = {math.log(gen.W0/NA):.17g}")
    s=replace_once(s,"scaling = 1.0e-22",f"scaling = {NA*1e-22:.17g}")
    s=replace_once(s,"type = FVTimeKernel\n    variable = electron_energy","type = PhysicsFVLogMolarElectronTimeDerivative\n    variable = electron_energy")
    s=replace_once(s,"type = FVDiffusion\n    variable = electron_energy","type = PhysicsFVLogMolarElectronDiffusion\n    variable = electron_energy")
    s=replace_once(s,"[FunctorMaterials]\n",f"""[FunctorMaterials]
  [physical_energy_readback]
    type = ADParsedFunctorMaterial
    property_name = reconstructed_energy
    functor_names = 'electron_energy'
    functor_symbols = 'u'
    expression = '{NA:.17g}*exp(u)'
    block = 1
  []
""")
    s=replace_once(s,"functor = electron_energy\n    block = 1","functor = reconstructed_energy\n    block = 1")
    return s
def run(name,source,p2_only=False):
    work=out/name
    work.mkdir()
    deck=work/"input.i"
    deck.write_text(source)
    rec={"input_sha256":hashlib.sha256(deck.read_bytes()).hexdigest()}
    result["cases"][name]=rec
    save()
    for phase,flags in [("P2",["--check-input"]),("P3",[])]:
        if p2_only and phase=="P3": break
        proc=subprocess.run([str(exe),*flags,"-i",deck.name],cwd=work,text=True,capture_output=True,timeout=120)
        log=proc.stdout+proc.stderr
        (work/(phase+".log")).write_text(log)
        ok=proc.returncode==0 and (phase!="P2" or "Syntax OK" in log)
        rec[phase]="PASS" if ok else "FAIL"
        save()
        print(name,phase,rec[phase],flush=True)
        if not ok:return None
    if p2_only:return None
    path=work/"input_out.csv"
    assert path.is_file(),name
    return path
def rows(path):
    assert path is not None
    with path.open(newline="") as stream:return list(csv.DictReader(stream))
def compare(a,b,end,fields):
    aa,bb=rows(a),rows(b)
    assert len(aa)==len(bb)>=2
    assert math.isclose(float(aa[0]["time"]),0.,abs_tol=1e-14)
    assert math.isclose(float(aa[-1]["time"]),end,rel_tol=1e-10)
    for x,y in zip(aa,bb):
        assert math.isclose(float(x["time"]),float(y["time"]),rel_tol=1e-10,abs_tol=1e-14)
        for f in fields:
            assert math.isclose(float(x[f]),float(y[f]),rel_tol=5e-8,abs_tol=1e-12),(f,x[f],y[f])
def evaluate(path,gs):
    if path is None:return False
    x=oracle.evaluate(path,gs)
    return all(x["checks"].values())
def pair(name,original,modified,end,fields,gs=None):
    a=run(name+"_original",original)
    b=run(name+"_standard",modified)
    checks={}
    try:
        compare(a,b,end,fields)
        checks["parity"]=True
        if gs is not None:
            checks["original_oracle"]=evaluate(a,gs)
            checks["standard_oracle"]=evaluate(b,gs)
        else:
            checks["original_oracle"]=checks["standard_oracle"]=True
    except Exception as err:
        checks["error"]=repr(err)
    result[name]=checks
    save()
    return a,b
smoke=(root/"physics_app/ci/electron_energy_wall_smoke.i").read_text()
pair("external_wall",smoke,candidate(smoke),1e-8,["energy_thermal_avg","energy_see_avg"])
for mode,gs in gen.CASES.items():
    original=gen.build(gs)
    a,b=pair(mode,original,candidate(original,block=1),gen.DT,["energy_inventory"],gs)
    m=run(mode+"_log_molar",molar_deck(original))
    try:
        compare(a,m,gen.DT,["energy_inventory"])
        result[mode]["log_molar_oracle"]=evaluate(m,gs)
    except Exception as err:
        result[mode]["log_molar_error"]=repr(err)
    save()
for name,opts in [("wrong_sign",{"sign":"1"}),("wrong_see",{"see":"0"})]:
    gs=gen.CASES["see_on"]
    path=run(name,candidate(gen.build(gs),block=1,**opts))
    # A failing execution is not a successful oracle discrimination.
    result[name]={"oracle_rejects":path is not None and not evaluate(path,gs)}
    save()
for name in ("prepare_d4","prepare_d4_lowerd"):
    obj=module(name)
    for mode,gamma in obj.CASES.items():
        run(name+"_"+mode,obj.build(gamma),p2_only=True)
# Existing oracle evaluates each bounded inventory/ledger; cross SEE shift is
# explicitly checked between successful OFF and ON outputs as well.
for suffix in ("original","standard","log_molar"):
    a=out/("see_off_"+suffix)/"input_out.csv"
    b=out/("see_on_"+suffix)/"input_out.csv"
    try:
        measured=oracle.read(b)[1]-oracle.read(a)[1]
        expected=oracle.analytic(gen.CASES["see_on"])["final_energy_inventory_eV_m3"]-oracle.analytic(gen.CASES["see_off"])["final_energy_inventory_eV_m3"]
        result["cross_"+suffix]={"pass":measured>0 and math.isclose(measured,expected,rel_tol=oracle.REL_TOL),"measured":measured,"expected":expected}
    except Exception as err:
        result["cross_"+suffix]={"pass":False,"error":repr(err)}
ok=all(all(result[n].get(k) is True for k in ("parity","original_oracle","standard_oracle")) for n in ("external_wall","see_off","see_on"))
ok=ok and all(result[n].get("log_molar_oracle") is True for n in ("see_off","see_on"))
ok=ok and all(result[n]["oracle_rejects"] for n in ("wrong_sign","wrong_see"))
ok=ok and all(result["cross_"+n]["pass"] for n in ("original","standard","log_molar"))
result["status"]="PASS_BOUNDED" if ok else "HOLD"
save()
print("R4_NATIVE_AB="+result["status"])
sys.exit(0 if ok else 1)
