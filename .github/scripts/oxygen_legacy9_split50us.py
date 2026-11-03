#!/usr/bin/env python3
"""Legacy9 50us native checkpoint -> separate-run 100us advanced restart.

The first segment keeps all 410 historical time steps to t=50us. The second
segment restores exact MOOSE/MultiApp state and caps adaptive dt at 1us.
No CSV/Exodus reinitialization, no private-rate archival, SCIENCE_HOLD.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import importlib.util
import json
import math
import re
import tarfile
from pathlib import Path

CHEM=Path("experiments/Issue395_powered_chemistry_ladder")
EXPECTED_SOURCE="8e2fe042dbc204b5fda22d346f1ad8d2e32db3ab"
EXPECTED_NETWORK=["EI-01","EI-02","DISS-G","EI-16","EI-17","EI-20","EI-2738","EI-407","EI-2067"]
STEP1_NS=50000
STEP2_NS=100000
OUTPUT_BASE="plasma_restart_50to100"
PARENT_MODEL="oxygen_legacy9_ei2067_100us.py"
SEQ=re.compile(r"(?m)^(\s*time_sequence\s*=\s*)'([^']+)'\s*$")
END=re.compile(r"(?m)^(\s*end_time\s*=\s*)[0-9eE.+-]+\s*$")
LOG_TIMESTEP=re.compile(r"(?m)^Time Step\s+(\d+),\s*time\s*=\s*([0-9.eE+-]+)")
DIGEST=re.compile(r"^[0-9a-f]{64}$")

def checksum(path):
    h=hashlib.sha256()
    with path.open("rb") as handle:
        for b in iter(lambda:handle.read(1048576),b""): h.update(b)
    return h.hexdigest()

def root_result(power):
    if power not in (400,1000): raise ValueError("RF power not allowed")
    return CHEM/f"results_rf_elastic_diss_ion_ei20_ei01_{power}w_adjacent_sheath_wall_closed_100us_dt1000ns"

def input_path(power):
    return CHEM/f"rf_elastic_diss_ion_ei20_ei01_{power}w_adjacent_sheath_wall_closed_100us_dt1000ns.i"

def parent_path(power):
    return CHEM/f"rf_elastic_multiapp_parent_{power}w_100us_dt1000ns_overlay.i"

def child_path(power):
    return CHEM/f"rf_elastic_multiapp_maxwell_{power}w_100us_dt1000ns_overlay.i"

def legacy_path(power,rid):
    return CHEM/f"{rid}_{power}w_100us_dt1000ns_overlay.i"

def native_grid_ns():
    return (list(range(101))+list(range(110,2001,10))
            +list(range(2100,10001,100))
            +list(range(11000,100001,1000)))

def grid(source):
    end=END.findall(source)
    seq=SEQ.findall(source)
    if len(end)!=1 or len(seq)!=1: raise ValueError("nonunique time stepper/grid")
    values=[float(v)*1e9 for v in seq[0][1].split()]
    return values

def assert_grid(source,stage):
    data=grid(source)
    expected=native_grid_ns()
    if stage==1: expected=[v for v in expected if v<=STEP1_NS]
    if len(data)!=len(expected) or any(abs(x-y)>1e-5 for x,y in zip(data,expected)):
        raise ValueError("stage grid altered or not monotonic")
    target=STEP1_NS if stage==1 else STEP2_NS
    match=END.search(source)
    if not match or not math.isclose(float(match.group().split("=")[1]),target*1e-9,abs_tol=1e-13,rel_tol=0):
        raise ValueError("wrong time endpoint")
    if len(re.findall(r"(?m)^\s*checkpoint\s*=\s*true\s*$",source))!=1:
        raise ValueError("checkpoint output not enabled")
    return len(expected)-1

def stage_first(power):
    path=input_path(power)
    txt=path.read_text()
    assert_grid(txt,2)
    old=SEQ.search(txt)
    if old is None: raise ValueError("time sequence absent")
    ns=native_grid_ns()
    first=[t for t in ns if t<=STEP1_NS]
    seconds=" ".join("0" if n==0 else format(n*1e-9,".17g") for n in first)
    out=txt[:old.start(2)]+seconds+txt[old.end(2):]
    replace=END.subn(lambda m:m.group(1)+"5.0000000000000002e-05",out,count=1)
    if replace[1]!=1: raise ValueError("missing end_time")
    out=replace[0]
    steps=assert_grid(out,1)
    if steps!=410: raise ValueError("stage first must have 410 time steps")
    path.write_text(out)
    print("LEGACY9_SPLIT_0_TO_50US_INPUT_PASS",power,steps,len(first))

def last_csv(path,target):
    with path.open(newline="") as handle:
        rows=list(csv.DictReader(handle))
    if len(rows)<2 or "time" not in rows[0]: raise ValueError("missing native csv history")
    times=[float(row["time"]) for row in rows]
    if any(not math.isfinite(t) for t in times) or any(b<=a for a,b in zip(times,times[1:])):
        raise ValueError("nonincreasing/native csv time")
    if not math.isclose(times[-1],target,rel_tol=0,abs_tol=1e-11):
        raise ValueError(f"native CSV endpoint {times[-1]} != {target}")
    return rows

def final_step(log,target):
    if not log.is_file(): raise ValueError("native solver log missing")
    data=LOG_TIMESTEP.findall(log.read_text(errors="replace"))
    if not data: raise ValueError("no native Time Step evidence")
    step,time=data[-1]
    if not math.isclose(float(time),target,rel_tol=0,abs_tol=1e-11):
        raise ValueError("native solver did not reach target")
    return int(step)

def checkpoint(prefix):
    for name in ("-restart-0.rd/data","-restart-0.rd/header","-mesh.cpa.gz/1/header.gz"):
        path=Path(str(prefix)+name)
        if not path.is_file() or path.stat().st_size==0:
            raise ValueError(f"native checkpoint item missing: {path}")

def required_inputs(power):
    from pathlib import Path
    main=input_path(power)
    baseline=(CHEM/"a0_full_icp.i",CHEM/"baseline_plasma_plus_unstructured_cover_plus_wafer.msh",
       CHEM/"issue397_maxwell_steady_abs1e11.i",CHEM/"o2_elastic.txt",
       CHEM/"o_elastic.txt",CHEM/"o2_ionization.txt",CHEM/"o_ionization.txt",
       CHEM/"o2_attachment.txt",CHEM/"electron_transport_initial_eedf.txt",
       Path("experiments/Issue91_real_qvt_r3/r3_e0/electron_moments.txt"))
    overlays=[
       parent_path(power),CHEM/f"rf_elastic_multiapp_maxwell_{power}w_100us_dt1000ns_overlay.i",
       CHEM/f"rf_elastic_multiapp_maxwell_{power}w_100us_dt1000ns_child.i",
       CHEM/f"o2_elastic_{power}w_100us_dt1000ns_overlay.i",
       CHEM/f"o2_attachment_ei01_{power}w_100us_dt1000ns_overlay.i",
       CHEM/f"o2_dissociation_{power}w_100us_dt1000ns_overlay.i",
       CHEM/f"o2_ionization_{power}w_100us_dt1000ns_overlay.i",
       CHEM/f"o_elastic_ei17_{power}w_100us_dt1000ns_overlay.i",
       CHEM/f"o_ionization_ei20_{power}w_100us_dt1000ns_overlay.i",
       CHEM/f"ei2738_detachment_formula_{power}w_100us_dt1000ns_overlay.i",
       CHEM/f"ei407_only_{power}w_100us_dt1000ns_overlay.i",
       CHEM/f"ei2067_only_{power}w_100us_dt1000ns_overlay.i"]
    return list(dict.fromkeys([main,*overlays,*baseline]))

def archive_kind(dest,files):
    items=[]
    with tarfile.open(dest,"w:gz") as out:
        for p in files:
            if not p.is_file() or p.is_symlink() or p.stat().st_size<=0:
                raise ValueError(f"native archive source unavailable: {p}")
            if "private_rates" in p.parts: raise ValueError("private rate leaked")
            out.add(p,arcname=p.as_posix(),recursive=False)
            items.append({"path":p.as_posix(),"bytes":p.stat().st_size,"sha256":checksum(p)})
    return {"name":dest.name,"sha256":checksum(dest),"bytes":dest.stat().st_size},items

def archive_first(power):
    result=root_result(power)
    inp=input_path(power)
    assert_grid(inp.read_text(),1)
    csv_path=result/"run/plasma.csv"
    rows=last_csv(csv_path,5e-5)
    step=final_step(result/"runtime.log",5e-5)
    prefix=result/"run/plasma_cp"/f"{step:04d}"
    checkpoint(prefix)
    variant=json.loads((result/"legacy6_latest_variant.json").read_text())
    if variant["chemistry_channels"]!=EXPECTED_NETWORK or variant["scientific_acceptance"]!="HOLD":
        raise ValueError("wrong stage1 chemistry/provenance")
    runfiles=sorted(p for p in (result/"run").rglob("*") if p.is_file())
    inputs=required_inputs(power)
    archives={}; inventory={}
    for kind,files in (("run",runfiles),("inputs",inputs)):
        dest=result/f"split_{kind}_{STEP1_NS}ns.tar.gz"
        archives[kind],inventory[kind]=archive_kind(dest,files)
    output={"schema":1,"variant":"LEGACY9_SPLIT_50US","power_W":power,
      "physics_source_sha":EXPECTED_SOURCE,
      "research_revision":"de1728327d1dc539422e421d5ad14ea764447f1a",
      "chemistry_channels":EXPECTED_NETWORK,
      "transport_table_sha256":variant["transport_table_sha256"],
      "ei407_lookup_sha256":variant["ei407_lookup_sha256"],
      "ei2067_lookup_sha256":variant["ei2067_lookup_sha256"],
      "stage_1_endpoint_s":5e-5,"native_last_step":step,
      "checkpoint_prefix":prefix.as_posix(),"archives":archives,"inventory":inventory,
      "stage1_rows":len(rows),"stage1_final":rows[-1],
      "scientific_acceptance":"HOLD","native_full_checkpoint":True}
    (result/f"split_{STEP1_NS}ns_manifest.json").write_text(json.dumps(output,indent=2,sort_keys=True)+"\n")
    print("LEGACY9_SPLIT_NATIVE_50US_CHECKPOINT_PASS",power,step,len(runfiles))

def safe_unpack(root,archive,meta,items):
    if checksum(archive)!=meta["sha256"]: raise ValueError("tampered native archive SHA")
    inventory={row["path"]:row for row in items}
    with tarfile.open(archive,"r:gz") as tar:
        members=tar.getmembers()
        if len(members)!=len(inventory) or set(m.name for m in members)!=set(inventory):
            raise ValueError("archive inventory mismatch")
        for member in members:
            if not member.isfile(): raise ValueError("nonfile tar member")
            rel=Path(member.name)
            if (rel.is_absolute() or ".." in rel.parts or
                not rel.parts or rel.parts[0]!="experiments"):
                raise ValueError("unsafe archive path")
            path=root/rel
            if not path.resolve().is_relative_to(root.resolve()):
                raise ValueError("unsafe archive destination")
            stream=tar.extractfile(member)
            if stream is None: raise ValueError("archive content missing")
            data=stream.read(); v=inventory[member.name]
            if len(data)!=v["bytes"] or hashlib.sha256(data).hexdigest()!=v["sha256"]:
                raise ValueError("invalid native member digest")
            path.parent.mkdir(exist_ok=True,parents=True)
            path.write_bytes(data)

def load_chain():
    path=Path(".github/scripts/oxygen25_restart_chain.py")
    spec=importlib.util.spec_from_file_location("native_recover",path)
    if spec is None or spec.loader is None: raise RuntimeError("reference native restart module missing")
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod

def restore(power,artifact):
    result=root_result(power)
    manifest=json.loads((artifact/f"split_{STEP1_NS}ns_manifest.json").read_text())
    if not (manifest["variant"]=="LEGACY9_SPLIT_50US" and
        manifest["power_W"]==power and manifest["physics_source_sha"]==EXPECTED_SOURCE
        and manifest["chemistry_channels"]==EXPECTED_NETWORK and
        manifest["native_full_checkpoint"] and manifest["scientific_acceptance"]=="HOLD"
        and manifest["stage_1_endpoint_s"]==5e-5):
        raise ValueError("untrusted upstream checkpoint identity")
    root=Path.cwd()
    for kind in ("run","inputs"):
        meta=manifest["archives"][kind]
        safe_unpack(root,artifact/meta["name"],meta,manifest["inventory"][kind])
    prefix=Path(manifest["checkpoint_prefix"])
    checkpoint(prefix)
    first=last_csv(result/"run/plasma.csv",5e-5)
    if first[-1]!=manifest["stage1_final"]:
        raise ValueError("upstream csv boundary not identical")
    main=input_path(power)
    assert_grid(main.read_text(),1)
    chain=load_chain()
    native=main.read_text()
    native=chain.suppress_parent_restart_ics(native)
    native=chain.stage_adaptive_stepper(native,"1000")
    native,count=END.subn(lambda m:m.group(1)+"0.0001",native,count=1)
    if count!=1 or "time_sequence =" in native: raise ValueError("failed safe restart stepper staging")
    native=chain.advanced_restart_input(native,prefix.as_posix())
    main.write_text(native)
    parent=parent_path(power)
    parent.write_text(chain.stage_parent_multiapp_restart_overlay(parent.read_text()))
    child=child_path(power)
    child.write_text(chain.stage_child_maxwell_restart_overlay(child.read_text()))
    if "no_restore = false" not in parent.read_text():
        raise ValueError("Maxwell MultiApp restoration disabled")
    if "initial_condition =" in main.read_text() or "initial_condition =" in child.read_text():
        raise ValueError("restart ICs could overwrite native checkpoint state")
    (result/"split_upstream_manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n")
    (result/"split_recovery_prefix.txt").write_text(prefix.as_posix()+"\n")
    print("LEGACY9_SPLIT_50US_NATIVE_PARENT_MAXWELL_RESTORE_STAGED_PASS",power)
    print("LEGACY9_SPLIT_RESTART_TIMESTEPPER_CAP_1US_PASS",power)

def validate_private(power):
    result=root_result(power)
    m=json.loads((result/"split_upstream_manifest.json").read_text())
    a=CHEM/"private_rates"/"EI-407_O2_X.txt"
    b=CHEM/"private_rates"/"EI-2067_O2_a1Delta.txt"
    if not(a.is_file() and b.is_file()): raise FileNotFoundError("private rate tables absent")
    if checksum(a)!=m["ei407_lookup_sha256"] or checksum(b)!=m["ei2067_lookup_sha256"]:
        raise ValueError("rate differs across 50us boundary")
    print("LEGACY9_SPLIT_PRIVATE_RATES_EXACT_REHYDRATION_PASS",power)

def verify_second(power):
    result=root_result(power)
    m=json.loads((result/"split_upstream_manifest.json").read_text())
    checkpoint(Path(m["checkpoint_prefix"]))
    validate_private(power)
    inp=input_path(power).read_text()
    if ("type = IterationAdaptiveDT" not in inp or
        "reset_dt = true" not in inp or "time_sequence =" in inp or
        "/workspace/"+m["checkpoint_prefix"] not in inp):
        raise ValueError("native advanced restart source not properly bound")
    final_csv=result/"run"/(OUTPUT_BASE+".csv")
    final=last_csv(final_csv,1e-4)
    if not any(float(r["time"])>5e-5+1e-11 for r in final):
        raise ValueError("no time integration after 50us checkpoint")
    step=final_step(result/"recovery_runtime.log",1e-4)
    rec_log=(result/"recovery_runtime.log").read_text(errors="replace")
    if not re.search(r"(?i)recover|restart",rec_log):
        raise ValueError("no native checkpoint recovery evidence")
    final_prefix=result/"run"/(OUTPUT_BASE+"_cp")/f"{step:04d}"
    checkpoint(final_prefix)
    original=last_csv(result/"run/plasma.csv",5e-5)
    if original[-1]!=m["stage1_final"]: raise ValueError("upstream state altered")
    if m["chemistry_channels"]!=EXPECTED_NETWORK: raise ValueError("chemistry changed")
    output={"schema":1,"variant":"LEGACY9_SPLIT_50_TO_100US",
      "power_W":power,"parent_50us_checkpoint":m["checkpoint_prefix"],
      "native_100us_checkpoint":final_prefix.as_posix(),"actual_moose_step":step,
      "native_endpoint_s":1e-4,"stage1_rows":len(original),"stage2_rows":len(final),
      "ei407_rate_sha256":m["ei407_lookup_sha256"],
      "ei2067_rate_sha256":m["ei2067_lookup_sha256"],
      "native_advanced_restart":True,"scientific_acceptance":"HOLD"}
    (result/"split_100000ns_result.json").write_text(json.dumps(output,indent=2,sort_keys=True)+"\n")
    print("LEGACY9_SPLIT_50US_TO_100US_NATIVE_RECOVERY_PASS",power,step,len(final))

def self_test():
    assert native_grid_ns()[0]==0 and native_grid_ns()[-1]==100000
    assert len(native_grid_ns())==461
    front=[t for t in native_grid_ns() if t<=STEP1_NS]
    assert len(front)==411 and front[-1]==50000 and front[-2]==49000
    tail=[t for t in native_grid_ns() if t>=STEP1_NS]
    assert len(tail)==51 and tail[0]==50000 and tail[-1]==100000
    assert all(b-a==1000 for a,b in zip(tail,tail[1:]))
    assert len(EXPECTED_NETWORK)==9
    print("LEGACY9_SPLIT_50US_TIMEGRID_410_PLUS_50_SELFTEST_PASS")

if __name__=="__main__":
    p=argparse.ArgumentParser()
    act=p.add_mutually_exclusive_group(required=True)
    for name in ("self-test","stage-first","archive-first","restore","verify-private","verify-second"):
        act.add_argument("--"+name,action="store_true")
    p.add_argument("--power-w",type=int,choices=(400,1000))
    p.add_argument("--artifact",type=Path)
    args=p.parse_args()
    if args.self_test:self_test()
    elif args.power_w is None:p.error("--power-w required")
    elif args.stage_first:stage_first(args.power_w)
    elif args.archive_first:archive_first(args.power_w)
    elif args.restore:
        if args.artifact is None:p.error("--artifact required")
        restore(args.power_w,args.artifact)
    elif args.verify_private:validate_private(args.power_w)
    else:verify_second(args.power_w)
