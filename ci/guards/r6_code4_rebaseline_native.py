"""R6: exact canonical input baseline, bounded zero-field-only Native A/B."""
import csv
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys

root=Path(sys.argv[1]).resolve()
out=Path(sys.argv[2]).resolve()
out.mkdir(parents=True,exist_ok=True)
exe=root/"physics_app/physics-opt"
ci=root/"physics_app/ci"
pairs={"electron_energy_transport_smoke.i":("b7b3850cb111cce0fed9414e75a7b2d3454d9b4e","69bcd9f05cdf3210de6d4eb8dead7892a9feb0ae"),"electron_energy_lookup_response_smoke.i":("12e775b24d2fb5bdfd46ba375a17d3cebca47991","c7fd527997bcdb11661e0b87224eafa3655bf98a")}
old="""  [energy_drift]
    type = PhysicsFVElectrostaticDrift
    variable = mean_en
    potential = phi_zero
    mobility = electron_energy_mobility
    carrier = carrier_one
    charge_number = -1
    advected_interp_method = upwind
  []"""
new="""  [energy_drift]
    type = FVAdvection
    variable = mean_en
    velocity = '0 0 0'
    advected_interp_method = upwind
  []"""
result={"schema":"r6.code4.canonical_ab.v1","status":"HOLD","safe_delete":False,"source_sha":subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip(),"source_tree":subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD^{tree}"],text=True).strip(),"binary_sha256":hashlib.sha256(exe.read_bytes()).hexdigest(),"additional_builds":0,"cases":{},"comparisons":{}}
def save():
    (out/"result.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
def require(ok,msg):
    if not ok:raise RuntimeError(msg)
def git_blob(raw):
    return hashlib.sha1(f"blob {len(raw)}".encode()+bytes(1)+raw).hexdigest()
def check_source(s):
    require(s.count(old)==1 and new not in s,"unexpected drift owner")
    require(s.count("expression = '0*x'")==1 and s.count("state_form = log_molar_eV")==1,"not exact canonical zero-field")
def run(name,s,table):
    work=out/name
    work.mkdir()
    deck=work/"input.i"
    deck.write_text(s)
    shutil.copyfile(table,work/table.name)
    rec={"input_sha256":hashlib.sha256(deck.read_bytes()).hexdigest(),"table_sha256":hashlib.sha256(table.read_bytes()).hexdigest()}
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
    with (work/"input_out.csv").open(newline="") as f:rows=[{k:float(v) for k,v in row.items()} for row in csv.DictReader(f)]
    require(len(rows)==2 and math.isclose(rows[0]["time"],0.,abs_tol=1e-15) and math.isclose(rows[-1]["time"],1e-8,rel_tol=1e-10),"time grid")
    return rows
def oracle(rows,table,energy,transport):
    values=[[float(x) for x in s.split()] for s in table.read_text().splitlines() if s.strip()]
    require(len(values)==2,"table bounds")
    a,b=values
    ratio=(energy-a[0])/(b[0]-a[0])
    scale=1.380649e-23*300./101325.
    mu=(a[1]+ratio*(b[1]-a[1]))*scale
    diff=(a[2]+ratio*(b[2]-a[2]))*scale
    expected={"time":None,"e_energy_eV_avg":energy,"electron_mobility_avg":mu,"electron_diffusion_avg":diff}
    if transport:expected.update({"electron_energy_mobility_avg":5./3.*mu,"electron_energy_diffusion_avg":5./3.*diff})
    errors={}
    for row in rows:
        require(set(row)==set(expected),"unexpected observable set: "+str(set(row)))
        for k,v in expected.items():
            require(math.isfinite(row[k]),"nonfinite "+k)
            if v is not None:
                error=abs(row[k]-v)/abs(v)
                errors[k]=max(errors.get(k,0.),error)
                require(error<=(1e-9 if k=="e_energy_eV_avg" else 1e-10),"oracle "+k)
    return errors
try:
    for filename,(sha,table_sha) in pairs.items():
        raw=(ci/filename).read_bytes()
        require(git_blob(raw)==sha,"baseline blob changed")
        table=ci/(Path(filename).stem+"_table.txt")
        require(git_blob(table.read_bytes())==table_sha,"table blob changed")
        s=raw.decode()
        check_source(s)
        transport="transport" in filename
        for label,energy in ([("base",5.73276)] if transport else [("low",2.86638),("base",5.73276),("high",8.59914)]):
            if label=="base":before=s
            else:
                require(s.count("initial_condition = 5.73276e16")==1,"unexpected initial")
                before=s.replace("initial_condition = 5.73276e16",f"initial_condition = {energy*1e16:.17g}")
            after=before.replace(old,new)
            require(after.replace(new,old)==before,"non-drift mutation")
            name=("transport" if transport else "lookup")+"_"+label
            a=run(name+"_before",before,table)
            b=run(name+"_after",after,table)
            x=oracle(a,table,energy,transport)
            y=oracle(b,table,energy,transport)
            err={}
            for ar,br in zip(a,b):
                require(set(ar)==set(br),"different fields")
                for k,v in ar.items():
                    w=br[k]
                    require(math.isclose(v,w,rel_tol=1e-10,abs_tol=1e-14),"parity "+k)
                    err[k]=max(err.get(k,0.),abs(v-w)/max(abs(v),abs(w),1e-100))
            result["comparisons"][name]={"before_oracle":x,"after_oracle":y,"max_relative_ab":err}
            save()
    result["status"]="PASS_BOUNDED"
except Exception as exc:
    result["error"]=repr(exc)
finally:
    save()
    print("R6_CODE4_NATIVE_AB="+result["status"])
sys.exit(0 if result["status"]=="PASS_BOUNDED" else 1)
