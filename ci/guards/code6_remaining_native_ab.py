#!/usr/bin/env python3
"""Evidence-only remaining six generators exact W1 A/B, no production edits."""
import csv, hashlib, importlib.util, json, math, re, shutil, subprocess, sys
from pathlib import Path
ROOT=Path("/workspace")
OUT=Path("/evidence/remaining")
OUT.mkdir(parents=True,exist_ok=True)
EXE=ROOT/"physics_app/physics-opt"
OLD="PhysicsFVMassFractionTimeDerivative"
NEW="PhysicsFVConservativeMassFractionTimeDerivative"
HEAD="1cd5cbd79137791e1acdd13ac17c15c61e55f242"
def sha(data): return hashlib.sha256(data).hexdigest()
def blob(data): return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()
assert subprocess.check_output(["git","-C",str(ROOT),"rev-parse","HEAD"],text=True).strip()==HEAD
assert sha(EXE.read_bytes())=="57773f58e275f8c1c9d863a465044dab63f734bea04933b26a46459b5d743862"
for name,expected in [(OLD,"09b0f60eb6473ac295a690e463198c370fc2870b"),(NEW,"177a8d74bf9806cf9000f710b6583847ae6c0c58")]:
    assert blob((ROOT/"physics_app/src/fvkernels"/(name+".C")).read_bytes())==expected
def load(name,expected):
    p=ROOT/"physics_app/ci"/name
    assert blob(p.read_bytes())==expected
    spec=importlib.util.spec_from_file_location(name[:-3],p)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
def invoke(cmd,work,label):
    p=subprocess.run(cmd,cwd=work,text=True,capture_output=True,timeout=180)
    (work/(label+".stdout.log")).write_text(p.stdout)
    (work/(label+".stderr.log")).write_text(p.stderr)
    return p.returncode,p.stdout+p.stderr
def pair(name,text,variables,dt,oracle,files=None,negative=False):
    pattern=r"(?m)^([ \t]*type[ \t]*=[ \t]*)"+OLD+r"[ \t]*$"
    found=re.findall(r"type\s*=\s*"+OLD+r"\s*\n\s*variable\s*=\s*(\w+)\s*\n\s*rho\s*=\s*rho_const\s*\n",text)
    assert sorted(found)==sorted(variables), (name,found,variables)
    assert len(re.findall(pattern,text))==len(variables)==text.count(OLD)
    assert re.search(r"prop_names\s*=\s*['\"]rho_const(?: T_g)?['\"]",text)
    candidate=text.replace(OLD,NEW)
    assert candidate.replace(NEW,OLD)==text
    result={"source_head":HEAD,"variables":variables,"negative_temperature":negative,"cases":{}}
    data=[]
    for role,body in (("incumbent",text),("candidate",candidate)):
        work=OUT/name/role
        work.mkdir(parents=True)
        inp=work/"case.i"
        inp.write_text(body)
        for filename,value in (files or {}).items(): (work/filename).write_text(value)
        record={"input_sha256":sha(inp.read_bytes()),"p2":"NOT_RUN","p3":"NOT_RUN"}
        result["cases"][role]=record
        subprocess.run([sys.executable,str(ROOT/"bin/physics.py"),"preflight",str(inp)],cwd=ROOT,check=True)
        rc,msg=invoke([str(EXE),"--check-input","-i",inp.name],work,"p2")
        record["p2"]="PASS" if rc==0 else "FAIL"
        if rc==0:
            rc,msg=invoke([str(EXE),"-i",inp.name],work,"p3")
            record["p3"]="PASS" if rc==0 else "FAIL"
        if negative:
            assert rc!=0,(name,role,"nonpositive temperature unexpectedly accepted")
            record["negative_rejection_layer"]="P2" if record["p2"]=="FAIL" else "P3"
            # Preserve actual diagnostics; a nonzero exit alone is not scientific acceptance.
        else:
            assert record["p2"]==record["p3"]=="PASS",(name,role,msg)
            raw=(work/"case_out.csv").read_bytes()
            rows=list(csv.DictReader(raw.decode().splitlines()))
            assert [float(r["time"]) for r in rows]==[0.0,dt]
            assert all(math.isfinite(float(v)) for row in rows for v in row.values())
            record["model_oracle"]=oracle(rows)
            record["csv_sha256"]=sha(raw)
            data.append(raw)
    if negative:
        assert result["cases"]["incumbent"]["negative_rejection_layer"]==result["cases"]["candidate"]["negative_rejection_layer"]
        result["negative_signature_review"]="PENDING_LOG_REVIEW"
    else:
        result["csv_byte_identical"]=data[0]==data[1]
        assert result["csv_byte_identical"],name+" CSV difference; investigate"
    return result

def table(m):
    return "".join(f"{x:.8g} {y:.17g}\n" for x,y in m.RATE_TABLE)

report={"source_head":HEAD,"safe_delete":"HOLD","effective_integrator":"NOT_INDEPENDENTLY_PINNED","ad_parity":"NOT_RUN","variable_density":"NOT_RUN","cases":{}}
try:
    m=load("check_e8_ei10_energy_runtime.py","a6ce9a9b637232facceddcc8a038bb0f11803bf0")
    m.runtime_checker_self_test()
    report["cases"]["ei10"]=pair("ei10",m.RUNTIME_INPUT,["w_O2s"],m.DT,m.validate_runtime_rows)
    m=load("check_e8_ei16_energy_runtime.py","bb93bab83e571f7e2a2d27420b67f20783dc6d7c")
    m.runtime_checker_self_test()
    report["cases"]["ei16"]=pair("ei16",m.RUNTIME_INPUT,["w_O2p"],m.DT,m.validate_runtime_rows,{"e8_ei16_runtime_table.txt":table(m)})
    m=load("check_r2_o2_ionization_implementation.py","01d73b9c07d44935bb3136fdcb6c2f45fb1a4eaa")
    m.runtime_checker_self_test()
    report["cases"]["r2"]=pair("r2",m.RUNTIME_INPUT,["w_O2p"],m.DT,m.validate_runtime_rows,{"r2_o2_ionization_runtime_table.txt":table(m)})
    m=load("check_r3_o2s_excitation_implementation.py","87343d1f53638754a04ba5171e2b3a61d9f9231a")
    m.runtime_checker_self_test()
    report["cases"]["r3"]=pair("r3",m.RUNTIME_INPUT,["w_O2s"],m.DT,m.validate_runtime_rows)
    m=load("check_standard_moose_energy_projection.py","754007c0e1118faf97cc5d369c6d3ed87e41e4d2")
    m._validate_input_contract()
    report["cases"]["standard_ei10"]=pair("standard_ei10",m.EI10_INPUT,["w_O2s"],m.DT,lambda rows:m._compare("EI10",{k:float(v) for k,v in rows[-1].items()},m.EI10_ORACLE))
    report["cases"]["standard_ei16"]=pair("standard_ei16",m.EI16_INPUT,["w_O2p"],m.DT,lambda rows:m._compare("EI16",{k:float(v) for k,v in rows[-1].items()},m.EI16_ORACLE),{"standard_ei16_runtime_table.txt":table(m)})
    m=load("check_stage5_s5d_heavy_reactions.py","10aec84c5448c007f46ee9f27829c31cb6db8d53")
    m.static_check()
    m.self_test()
    variables=["w_O2p","w_O","w_Om","w_Op"]
    for t in (600.0,1200.0):
        name="s5d_"+str(int(t))+"K"
        report["cases"][name]=pair(name,m.input_text(t),variables,m.DT,lambda rows:m.validate_case(rows,t))
    for role in ("incumbent","candidate"):
        m.validate_scaling(report["cases"]["s5d_600K"]["cases"][role]["model_oracle"],report["cases"]["s5d_1200K"]["cases"][role]["model_oracle"])
    report["cases"]["s5d_negative_T"]=pair("s5d_negative_T",m.input_text(-600.0),variables,m.DT,None,negative=True)
    report["status"]="OBSERVED_NINE_PAIRS"
finally:
    (OUT/"receipt.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
print("CODE6_REMAINING_NATIVE_AB=OBSERVED_NINE_PAIRS")
