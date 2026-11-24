#!/usr/bin/env python3
"""Evidence-only Stage5 EDetach/EI18/EI20 exact W1 A/B, no source edits."""
import csv, hashlib, importlib.util, json, math, re, shutil, subprocess, sys
from pathlib import Path
ROOT=Path("/workspace")
OUT=Path("/evidence/stage5")
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
def pair(name,text,variable,dt,oracle,table=None,negative=False):
    # Require exactly one explicit time kernel declaration and unchanged rho binding.
    pattern=r"(?m)^(\s*type\s*=\s*)"+OLD+r"[ \t]*$"
    assert len(re.findall(pattern,text))==1 and text.count(OLD)==1
    assert re.search(r"type\s*=\s*"+OLD+r"\s*\n\s*variable\s*=\s*"+variable+r"\s*\n\s*rho\s*=\s*rho_const\s*\n",text)
    assert re.search(r"prop_names\s*=\s*['\"]rho_const['\"]",text)
    candidate=text.replace(OLD,NEW)
    assert candidate.replace(NEW,OLD)==text
    result={"expected_strict_lookup_rejection":negative,"source_head":HEAD,"cases":{}}
    data=[]
    for role,body in (("incumbent",text),("candidate",candidate)):
        work=OUT/name/role
        work.mkdir(parents=True)
        inp=work/"case.i"
        inp.write_text(body)
        if table: shutil.copy2(table,work/table.name)
        record={"input_sha256":sha(inp.read_bytes()),"p2":"NOT_RUN","p3":"NOT_RUN"}
        result["cases"][role]=record
        subprocess.run([sys.executable,str(ROOT/"bin/physics.py"),"preflight",str(inp)],cwd=ROOT,check=True)
        rc,msg=invoke([str(EXE),"--check-input","-i",inp.name],work,"p2")
        record["p2"]="PASS" if rc==0 else "FAIL"
        if rc==0:
            rc,msg=invoke([str(EXE),"-i",inp.name],work,"p3")
            record["p3"]="PASS" if rc==0 else "FAIL"
        if negative:
            assert rc!=0 and "outside lookup range" in msg and "strict Stage-4 policy forbids clamp/floor" in msg,(name,role,msg)
            record["strict_lookup_negative"]="PASS"
        else:
            assert record["p2"]==record["p3"]=="PASS",(name,role,msg)
            csvpath=work/"case_out.csv"
            raw=csvpath.read_bytes()
            rows=list(csv.DictReader(raw.decode().splitlines()))
            assert [float(r["time"]) for r in rows]==[0.0,dt]
            assert all(math.isfinite(float(v)) for row in rows for v in row.values())
            record["model_oracle"]=oracle(rows)
            record["csv_sha256"]=sha(raw)
            data.append(raw)
    if not negative:
        result["csv_byte_identical"]=data[0]==data[1]
        assert result["csv_byte_identical"], name+" CSV difference; investigate without automatic acceptance"
    return result
report={"source_head":HEAD,"safe_delete":"HOLD","effective_integrator":"NOT_INDEPENDENTLY_PINNED","ad_parity":"NOT_RUN","variable_density":"NOT_RUN","cases":{}}
try:
    m=load("check_stage5_edetach_runtime.py","1743d85f1e3e88244452639bf1a2c3bec9263da4")
    m.static()
    report["cases"]["edetach"]=pair("edetach",m.text(),"w_Om",m.DT,m.val)
    m=load("check_stage5_ei18_runtime.py","08f1aad2ec500ab2e400e3e15b3e0a8f7882e9d0")
    m.static_gate()
    table=m._read_table_bytes(m.TABLE.read_bytes())
    for suffix,energy,negative in [("base",m.EPSILON_E0_EV,False),("below",m.LOOKUP_MIN_EV-.01,True),("above",m.LOOKUP_MAX_EV+.01,True)]:
        n="ei18_"+suffix
        report["cases"][n]=pair(n,m._runtime_input(energy),"w_Os",m.DT,lambda rows:m.validate_runtime_rows(rows,table),m.TABLE,negative)
    m=load("check_stage5_ei20_runtime.py","b71e0ec5b89536fedd8e0ca05f9fe4d405b595ed")
    m.static_gate()
    table=m.read_table(m.TABLE.read_bytes())
    for suffix,energy,negative in [("base",m.EREF,False),("below",m.XMIN-.01,True),("above",m.XMAX+.01,True)]:
        n="ei20_"+suffix
        report["cases"][n]=pair(n,m.runtime_input(energy),"w_Op",m.DT,lambda rows:m.validate(rows,table),m.TABLE,negative)
    report["status"]="OBSERVED_ALL_SEVEN_PAIRS"
finally:
    (OUT/"receipt.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
print("CODE6_STAGE5_NATIVE_AB=OBSERVED_ALL_SEVEN_PAIRS")
