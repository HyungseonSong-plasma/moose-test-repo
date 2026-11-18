#!/usr/bin/env python3
"""Independent exact-source PR684 transport cutover verifier: 18 discrete cases.

2 positive fixture replays + 14 fail-closed mutations + 2 read-only
source/consumer assertions. No Native P2 or private EI data.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import traceback
import importlib.util

ROOT=Path(__file__).resolve().parents[2] if len(sys.argv)<2 else Path(sys.argv[1]).resolve()
OUT=Path(sys.argv[2]).resolve() if len(sys.argv)>2 else Path("issue672-pr684-18.json").resolve()
SRC=ROOT/"tests/test_issue672_p6_d1_transport_owner_cutover.py"
EXPECTED={
 "physics_app/src/physics/plasma/DDContinuityEq.C":"2d120416d1bfe7c5454d0a7e955dcd6d9a763abc",
 "experiments/Issue402_plasma_dsl_g1/public_option_s6_p2.py":"28e34e4352bec25006aca42e9abcac9acc584cc8",
 "experiments/Issue402_plasma_dsl_g1/run_chemistry_s6_p2_only.py":"6c6dcf6516d4169e4481f305dc882862253acbe9",
 "experiments/Issue402_plasma_dsl_g1/chemistry/prepare_hybrid_json_s6.py":"8a76517c7863be77d8390cd04b0b3be055f2c147",
 "tests/test_issue672_p6_d1_transport_owner_cutover.py":"041a37f4162192f9cf4ae7d59f59382f9c439c82"
}
def git_blob(path):
 import subprocess
 return subprocess.check_output(["git","hash-object",str(path)],text=True).strip()
def sha(blob):return hashlib.sha256(blob).hexdigest()
def stat_fixture(t):
 result={}
 for tag,path in [("C0",t.first),("OVERLAY",t.overlay),("JSON",t.js),("TABLE",t.table)]:
  result[tag]=sha(path.read_bytes()) if path.exists() else "ABSENT"
 return result
def replace_exact(path,before,after):
 s=path.read_text(encoding="utf-8")
 if s.count(before)!=1:raise AssertionError("MUTATOR_TARGET_NOT_UNIQUE:"+before)
 path.write_text(s.replace(before,after,1),encoding="utf-8")
def modify(t,name):
 if name=="missing_e": replace_exact(t.first,"[electron_transport]","[missing_e]")
 elif name=="duplicate_e":
  replace_exact(t.first,"  [electron_transport]\n",
   "  [electron_transport]\n    type = DDTransportMaterial\n  []\n  [electron_transport]\n")
 elif name=="wrong_fluid":replace_exact(t.first,"fluid_energy = true","fluid_energy = false")
 elif name=="wrong_table":replace_exact(t.first,"electron_moments.txt","other_table.txt")
 elif name=="wrong_gas":replace_exact(t.first,"T_g_fixed","T_g_wrong")
 elif name=="wrong_pressure":replace_exact(t.first,"pressure = p\n","pressure = wrong_p\n")
 elif name=="missing_Om":replace_exact(t.overlay,"[Om_species_transport_alias]","[missing_Om]")
 elif name=="missing_Op":replace_exact(t.overlay,"[Op_species_transport_alias]","[missing_Op]")
 elif name=="wrong_ion_coeff":replace_exact(t.overlay,"negative_ion_diffusion","unproven_diffusion")
 elif name=="charge_sign":t.change_json("Om","charge_number",1)
 elif name=="invalid_density":t.change_json("e","initial_number_density",-1)
 elif name=="existing_json_transport":t.change_json("e","transport_coef","lookup")
 elif name=="table_tamper":t.table.write_bytes(b"tampered-public-table")
 elif name=="table_missing":t.table.unlink()
 else:raise AssertionError("UNKNOWN_MUTATION:"+name)
COUNTERS=[
 ("N01_missing_e","missing_e",r"OWNER_COUNT"),
 ("N02_duplicate_e","duplicate_e",r"OWNER_COUNT|OWNER_IDENTITY"),
 ("N03_wrong_fluid","wrong_fluid",r"OWNER_IDENTITY"),
 ("N04_wrong_table","wrong_table",r"OWNER_IDENTITY"),
 ("N05_wrong_gas","wrong_gas",r"OWNER_IDENTITY"),
 ("N06_wrong_pressure","wrong_pressure",r"OWNER_IDENTITY"),
 ("N07_missing_Om","missing_Om",r"OWNER_COUNT"),
 ("N08_missing_Op","missing_Op",r"OWNER_COUNT"),
 ("N09_wrong_ion_coeff","wrong_ion_coeff",r"OWNER_IDENTITY"),
 ("N10_charge_sign","charge_sign",r"PRECUTOVER_INITIAL_IDENTITY"),
 ("N11_invalid_density","invalid_density",r"PRECUTOVER_INITIAL_IDENTITY"),
 ("N12_existing_json_transport","existing_json_transport",r"PRECUTOVER_INITIAL_IDENTITY"),
 ("N13_table_tamper","table_tamper",r"TABLE_SHA_MISMATCH"),
 ("N14_table_missing","table_missing",r"TABLE_SHA_MISMATCH")
]
data={"schema":"issue672.pr684.independent_18.exact_source.v1",
      "source_sha":os.environ.get("PR684_PIN",""),
      "source_git_blobs":{},"checks":[],"expected_count":18,"passed":0,
      "source_only":True,"Native_P2":"NOT_RUN","SCIENCE_HOLD":True}
try:
 for name,blob in EXPECTED.items():
  current=git_blob(ROOT/name)
  data["source_git_blobs"][name]={"expected":blob,"actual":current,"match":current==blob}
  if current!=blob:raise AssertionError("SOURCE_BLOB_SHA_MISMATCH:"+name)
 spec=importlib.util.spec_from_file_location("issue672_independent_testfixture",SRC)
 if spec is None or spec.loader is None:raise RuntimeError("TEST_SOURCE_UNAVAILABLE")
 mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
 def fixture():
  t=mod.TestExactCutover(methodName="test_cpp_historical_5_over_3_is_faithful")
  t.setUp()
  return t
 def record(key,func):
  entry={"id":key,"status":"FAIL"}
  try:
   details=func()
   entry["status"]="PASS"
   if isinstance(details,dict):entry.update(details)
  except Exception as exc:
   entry["error_type"]=type(exc).__name__
   entry["error"]=str(exc)[:260]
  data["checks"].append(entry)
 for case in ("417","941"):
  def positive(case=case):
   t=fixture()
   try:
    pre=stat_fixture(t)
    receipt=t.cutover(t.folder,t.ordered)
    post=stat_fixture(t)
    doc=json.loads(t.js.read_text())["species"]
    assert receipt["retired_material_count"]==4
    assert receipt["transport_json_species"]==["O2p","Om","Op","e"]
    assert receipt["native_P05"]=="NOT_RUN"
    assert pre["TABLE"]==post["TABLE"]==sha(mod.TABLE)
    assert all(pre[x]!=post[x] for x in ("C0","OVERLAY","JSON"))
    assert "[electron_transport]" not in t.first.read_text()
    assert all("["+x+"_species_transport_alias]" not in t.overlay.read_text() for x in ("O2p","Om","Op"))
    assert doc["e"]["energy_transport_coef"]=="fluid"
    assert doc["e"]["table_units"]=="reduced"
    assert doc["e"]["pressure"]=="p" and doc["e"]["gas_temperature"]=="T_g_fixed"
    assert doc["e"]["bounds_policy"]=="clamp"
    assert doc["O2p"]["mobility"]=="ion_mobility"
    assert doc["Om"]["diffusivity"]=="negative_ion_diffusion"
    assert doc["Op"]["diffusivity"]=="atomic_positive_ion_diffusion"
    return {"case":"S6-"+case+"_FIXTURE","retired_count":4,
      "before_sha256":pre,"after_sha256":post,"closure":"5/3_legacy_fluid_retained"}
   finally:t.doCleanups()
  record("P"+case+"_positive",positive)
 for id,mutation,pattern in COUNTERS:
  def negative(mutation=mutation,pattern=pattern):
   t=fixture()
   try:
    modify(t,mutation)
    pre=stat_fixture(t)
    err=""
    try:t.cutover(t.folder,t.ordered)
    except ValueError as e:err=str(e)
    if not err or not re.search(pattern,err):
     raise AssertionError("WRONG_FIRST_ERROR:"+err[:130])
    post=stat_fixture(t)
    if pre!=post:raise AssertionError("NON_ATOMIC_SCRATCH_WRITE")
    return {"expected_error_pattern":pattern,"observed_first_error":err[:180],
            "input_sha256_after_mutation":pre,"unmodified_after_rejection":True}
   finally:t.doCleanups()
  record(id,negative)
 def cpp():
  source=(ROOT/"physics_app/src/physics/plasma/DDContinuityEq.C").read_text()
  keys=['mechanism.fluidElectronEnergyTransport()',
        'params.set<bool>("fluid_energy") = fluid || legacy_fluid;',
        'if (legacy_fluid && !energy.empty() && !fluid)']
  assert all(source.count(k)>=1 for k in keys)
  return {"checks":len(keys),"status_class":"CXX_LEGACY_5_OVER_3_CLOSURE"}
 record("S17_cpp_energy_closure",cpp)
 def flow():
  source=(ROOT/"experiments/Issue402_plasma_dsl_g1/run_chemistry_s6_p2_only.py").read_text()
  keys=["prepare as prepare_hybrid_transport","hybrid_transport = prepare_hybrid_transport(",
        "chemistry, ordered, case, chemistry_cutover=cutover"]
  assert all(source.count(k)>=1 for k in keys)
  return {"checks":len(keys),"status_class":"FLOW_HYBRID_TRANSPORT_HANDOFF"}
 record("S18_flow_owner_handoff",flow)
 data["passed"]=sum(x["status"]=="PASS" for x in data["checks"])
 data["status"]="PASS_18_OF_18" if len(data["checks"])==18 and data["passed"]==18 else "FAIL"
except Exception as e:
 data["fatal"]=type(e).__name__+":"+str(e)[:240]
 data["status"]="HOLD_SOURCE_OR_HARNESS"
finally:
 OUT.parent.mkdir(parents=True,exist_ok=True)
 OUT.write_text(json.dumps(data,indent=2,sort_keys=True)+"\n")
 print("PR684_INDEPENDENT_EXACT_SOURCE_18",data["status"],data["passed"],"/",len(data["checks"]))
 print("RECEIPT",OUT)
sys.exit(0 if data["status"]=="PASS_18_OF_18" else 1)
