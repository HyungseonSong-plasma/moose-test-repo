#!/usr/bin/env python3
"""Issue #224 depth-aware closure packets: dense zero-step RSS + R1 parity."""
from __future__ import annotations

import argparse, hashlib, json, math, os, re
from pathlib import Path
from typing import Any, Mapping

from experiments.Issue192_s5r_representative import run as s5r
from experiments.Issue216_w5_multistep_acceptance import run as w5
from experiments.Issue224_element_aggregate_memory import run_parallel as rp
from experiments.Issue224_observability_memory import run_c5 as c5
from experiments.Issue224_observability_memory import run_c5r as c5r
from physics_harness.adapters.moose import parameters as mp
from physics_harness.execution.cases import stage_case, validate_case_references

ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
REGIMES = {"zero_step", "physical_r1"}
SCHEDULES = {"production", "only", "without"}
PARAMS = {"type", "functor", "prefactor"}
AD = "ADElementIntegralFunctorPostprocessor"
NONAD = "ElementIntegralFunctorPostprocessor"
PARITY_TOL = 1.0e-4

class Issue224DepthError(RuntimeError): pass

def _write(out: Path, s: Mapping[str, Any]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(s, indent=2, sort_keys=True)+"\n")

def _zero_base(): return rp._production()
def _phys_base(): return w5._build_case(dt_s=w5.BASELINE_DT_S, uniform_refine=0)
def _paths(): return rp._element_paths(_zero_base()[0])

def _mutations(raw: Any, text: str, allowed: set[str]) -> list[dict[str, Any]]:
    if raw is None: return []
    if not isinstance(raw, list): raise Issue224DepthError("mutations must be a list")
    out, seen = [], set()
    keys = {"path","parameter","expected","value"}
    for i, m in enumerate(raw):
        if not isinstance(m, Mapping) or set(m) != keys: raise Issue224DepthError(f"mutation[{i}] bad keys")
        p, q, e, v = m["path"], m["parameter"], m["expected"], m["value"]
        if p not in allowed or q not in PARAMS: raise Issue224DepthError(f"mutation[{i}] bad target")
        if e is not None and not isinstance(e, str): raise Issue224DepthError(f"mutation[{i}] bad expected")
        if not isinstance(v, str) or not v or "\n" in v or "\r" in v: raise Issue224DepthError(f"mutation[{i}] bad value")
        if (p,q) in seen: raise Issue224DepthError(f"duplicate mutation {p}/{q}")
        seen.add((p,q))
        current = mp.get_parameter(text,p,q)
        if current != e: raise Issue224DepthError(f"expected mismatch {p}/{q}: {e!r} != {current!r}")
        if current == v: raise Issue224DepthError(f"no-op mutation {p}/{q}")
        if q == "type" and (e != AD or v != NONAD): raise Issue224DepthError("type mutation must be AD integral -> non-AD integral")
        out.append(dict(m))
    return out

def _validate_packet(raw: Mapping[str, Any]) -> dict[str, Any]:
    if set(raw) - {"id","depth","regime","question","cases"}: raise Issue224DepthError("unsupported packet keys")
    pid, depth, regime, question, cases = (raw.get(k) for k in ("id","depth","regime","question","cases"))
    if not isinstance(pid,str) or not ID_RE.fullmatch(pid): raise Issue224DepthError("bad packet id")
    if depth not in (1,2,3): raise Issue224DepthError("depth must be 1..3")
    if regime not in REGIMES: raise Issue224DepthError("bad regime")
    if not isinstance(question,str) or not question or len(question)>240: raise Issue224DepthError("bad question")
    if not isinstance(cases,list) or not 1 <= len(cases) <= 6: raise Issue224DepthError("cases must be 1..6")
    base = _zero_base()[0] if regime == "zero_step" else _phys_base()[0]
    allowed = set(_paths()); norm=[]; ids=set()
    for c in cases:
        if not isinstance(c,Mapping) or set(c)-{"id","schedule","paths","mutations","role"}: raise Issue224DepthError("bad case keys")
        cid, sch = c.get("id"), c.get("schedule")
        role = c.get("role","discriminator")
        if not isinstance(cid,str) or not ID_RE.fullmatch(cid) or cid in ids: raise Issue224DepthError("bad/duplicate case id")
        ids.add(cid)
        if sch not in SCHEDULES: raise Issue224DepthError(f"bad schedule {cid}")
        if not isinstance(role,str) or not role or len(role)>80: raise Issue224DepthError(f"bad role {cid}")
        if sch == "production":
            if c.get("paths") not in (None,[]): raise Issue224DepthError(f"production case carries paths: {cid}")
            paths=[]
        else:
            paths=c.get("paths")
            if not isinstance(paths,list) or not paths or not all(isinstance(x,str) for x in paths): raise Issue224DepthError(f"bad paths {cid}")
            if len(set(paths)) != len(paths) or set(paths)-allowed: raise Issue224DepthError(f"paths outside accepted 57: {cid}")
            paths=sorted(paths)
        if regime == "physical_r1" and sch != "production": raise Issue224DepthError("physical packet must preserve production schedule")
        norm.append({"id":cid,"schedule":sch,"paths":paths,"role":role,"mutations":_mutations(c.get("mutations"),base,allowed)})
    return {"id":pid,"depth":depth,"regime":regime,"question":question,"cases":norm}

def _apply(text: str, case: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    element=set(_paths()); before=c5._observer_snapshot(text); sch=case["schedule"]; selected=set(case["paths"])
    if sch == "production": deferred=[]
    else:
        keep = selected if sch == "only" else element-selected
        text,deferred = rp._defer_except(text,keep=keep,before=before,element_set=element)
    applied=[]
    for m in case["mutations"]:
        if mp.get_parameter(text,m["path"],m["parameter"]) != m["expected"]: raise Issue224DepthError("mutation drift")
        text=mp.upsert_parameter(text,m["path"],m["parameter"],m["value"]); applied.append(dict(m))
    after=c5._observer_snapshot(text)
    changed_out=[p for p in before if p not in element and after[p] != before[p]]
    if changed_out: raise Issue224DepthError(f"non-target observer change: {changed_out}")
    return text,{"case_id":case["id"],"role":case["role"],"schedule":sch,"schedule_paths":sorted(selected),"deferred_count":len(deferred),"deferred_paths":deferred,"mutations":applied,"changed_non_target_count":0}

def _zero_execute(exe: Path,out: Path,name: str,kind: str,packet: Mapping[str,Any],case=None,timeout=1800.0):
    spec={"id":packet["id"],"mode":"keep_initial","keep_paths":[_paths()[0]]}
    if kind != "candidate": return rp._execute(exe,out,name=name,kind=kind,spec=spec,timeout=timeout)
    original=rp._candidate
    try:
        rp._candidate=lambda text,_spec:_apply(text,case)
        return rp._execute(exe,out,name=name,kind="candidate",spec=spec,timeout=timeout)
    finally: rp._candidate=original

def _run_zero(exe: Path,out: Path,p: Mapping[str,Any],timeout: float):
    s={"schema_version":1,"issue":224,"packet":p,"base_sha":os.environ.get("EXPERIMENT_BASE_SHA"),"workflow_event_sha":os.environ.get("GITHUB_SHA"),"physics_opt_sha256":w5._sha256(exe),"regime":"zero_step","physical_timesteps_authorized":0,"promotion_authorized":False,"cases":{},"decision":{}}
    def run(name,kind,case=None):
        x=_zero_execute(exe,out,name,kind,p,case,timeout); s["cases"][name]=x; _write(out,s); return x
    before=run("production_before","production")
    for c in p["cases"]: run("candidate__"+c["id"],"candidate",c)
    low=run("all_57_deferred","all_57_deferred"); after=run("production_after","production")
    controls=all(x.get("hard_pass") is True for x in (before,low,after))
    if controls:
        drift=c5r._control_drift(before,after); lowcmp=c5r._comparison(before,after,low); lowclass=c5r._family_classification(lowcmp)
    else: drift={"stable":False,"reason":"CONTROL_EXECUTION_FAILURE"}; lowcmp={"status":"NOT_EVALUATED"}; lowclass="UNRESOLVED"
    decisions={}
    for c in p["cases"]:
        x=s["cases"]["candidate__"+c["id"]]
        if controls and x.get("hard_pass") is True:
            cmp=c5r._comparison(before,after,x); decisions[c["id"]]={"status":"MEASURED","comparison":cmp,"reduction_classification":c5r._family_classification(cmp)}
        else: decisions[c["id"]]={"status":"CASE_UNRESOLVED","reason":x.get("reason","UNKNOWN")}
    ready=controls and drift.get("stable") is True and lowclass=="MAJOR"
    s["decision"]={"production_control_drift":drift,"low_control_comparison":lowcmp,"low_control_reduction_classification":lowclass,"candidate_decisions":decisions,"interpretation_scope":"MEASUREMENT_ONLY_CROSS_CASE_ARBITRATION_REQUIRED","promotion_authorized":False}
    s["status"]="ISSUE224_DEPTH_EVIDENCE_READY" if ready else "ISSUE224_DEPTH_HOLD"; _write(out,s); return s

def _stage_phys(case_dir: Path,text: str,meta: Mapping[str,Any],mutation: Mapping[str,Any]):
    stage_case(w5.SOURCE,case_dir,input_text=text,purge_directory_names=(".jitcache","checkpoint","checkpoints"),purge_patterns=("input_out*","*.log","*.e","*.exo","prepare_evidence.json"))
    s5r._copy_runtime_assets(case_dir); refs=validate_case_references(case_dir)
    m={**dict(meta),"issue":224,"diagnostic":"DEPTH_AWARE_W5_R1_PHYSICAL_PARITY","input_sha256":hashlib.sha256(text.encode()).hexdigest(),"mutation":dict(mutation),"references":refs,"production_promotion_claim":False}
    (case_dir/"prepare_evidence.json").write_text(json.dumps(m,indent=2,sort_keys=True)+"\n"); return m

def _phys_execute(exe: Path,out: Path,name: str,text: str,meta: Mapping[str,Any],mutation: Mapping[str,Any],timeout: float):
    case_dir=out/"cases"/name; logs=out/"logs"; logs.mkdir(parents=True,exist_ok=True); staged=_stage_phys(case_dir,text,meta,mutation)
    p2=s5r._p2(exe,case_dir,logs/f"{name}_p2.log",timeout=timeout); item={"kind":"physical_r1","meta":staged,"p2":p2,"hard_pass":False}
    if p2.get("returncode") != 0: item["reason"]="P2_FAIL"; return item
    rlog=logs/f"{name}_runtime.log"; tlog=logs/f"{name}_time_v.log"; runtime=c5r._runtime_with_os_rss(exe,case_dir,rlog,tlog,timeout=timeout)
    try: evidence=w5._analyze_case(case_dir,input_text=text,meta=meta,runtime_log=rlog,runtime_returncode=int(runtime.get("returncode",1)))
    except (w5.Issue216Error,KeyError,ValueError,AssertionError) as exc: evidence={"hard_pass":False,"analysis_error":f"{type(exc).__name__}: {exc}"}
    peak=runtime.get("os_max_rss_mib"); item.update({"runtime":runtime,"memory":{"os_max_rss_mib":peak,"authoritative_peak_metric":"os_max_rss_mib"},"evidence":evidence})
    item["hard_pass"]=runtime.get("returncode")==0 and isinstance(peak,(int,float)) and math.isfinite(float(peak)) and float(peak)>0 and evidence.get("hard_pass") is True
    if not item["hard_pass"]: item["reason"]="W5_R1_RUNTIME_OR_INVARIANT_FAIL"
    return item

def _vdiff(a: Mapping[str,float],b: Mapping[str,float]):
    vals={k:{"a":float(a[k]),"b":float(b[k]),"symmetric_relative_difference":abs(float(a[k])-float(b[k]))/max(abs(float(a[k])),abs(float(b[k])),1e-300)} for k in sorted(set(a)&set(b))}
    mx=max((x["symmetric_relative_difference"] for x in vals.values()),default=math.inf)
    return {"values":vals,"max_symmetric_relative_difference":mx,"tolerance":PARITY_TOL,"pass":bool(vals) and mx<=PARITY_TOL}

def _run_phys(exe: Path,out: Path,p: Mapping[str,Any],timeout: float):
    base,meta=_phys_base(); s={"schema_version":1,"issue":224,"packet":p,"base_sha":os.environ.get("EXPERIMENT_BASE_SHA"),"workflow_event_sha":os.environ.get("GITHUB_SHA"),"physics_opt_sha256":w5._sha256(exe),"regime":"physical_r1","physical_timesteps_authorized":int(meta["expected_steps"]),"endpoint_parity_tolerance":PARITY_TOL,"promotion_authorized":False,"cases":{},"decision":{}}
    def run(name,text,mutation): x=_phys_execute(exe,out,name,text,meta,mutation,timeout); s["cases"][name]=x; _write(out,s); return x
    before=run("production_before",base,{"kind":"control"})
    for c in p["cases"]:
        text,mutation=_apply(base,c); run("candidate__"+c["id"],text,mutation)
    after=run("production_after",base,{"kind":"control"}); controls=before.get("hard_pass") is True and after.get("hard_pass") is True
    ctrl=_vdiff(before["evidence"]["endpoint"],after["evidence"]["endpoint"]) if controls else {"pass":False,"reason":"CONTROL_FAILURE"}; decisions={}
    for c in p["cases"]:
        x=s["cases"]["candidate__"+c["id"]]
        if controls and x.get("hard_pass") is True:
            a=_vdiff(before["evidence"]["endpoint"],x["evidence"]["endpoint"]); b=_vdiff(after["evidence"]["endpoint"],x["evidence"]["endpoint"])
            decisions[c["id"]]={"status":"MEASURED","w5_hard_gates_pass":True,"endpoint_vs_before":a,"endpoint_vs_after":b,"endpoint_parity_pass":a["pass"] and b["pass"]}
        else: decisions[c["id"]]={"status":"CASE_UNRESOLVED","w5_hard_gates_pass":x.get("hard_pass") is True,"reason":x.get("reason","UNKNOWN"),"endpoint_parity_pass":False}
    ready=controls and ctrl.get("pass") is True; s["decision"]={"production_control_endpoint_parity":ctrl,"candidate_decisions":decisions,"interpretation_scope":"R1_PHYSICAL_PARITY_ONLY_NO_PROMOTION_AUTHORIZATION","promotion_authorized":False}; s["status"]="ISSUE224_DEPTH_EVIDENCE_READY" if ready else "ISSUE224_DEPTH_HOLD"; _write(out,s); return s

def self_test():
    checks={"v3_runner_self_test":rp.self_test().get("status")=="PASS","element_count":len(_paths())==57}; ne="Postprocessors/n_e_inventory"
    p={"id":"SELF","depth":3,"regime":"zero_step","question":"exact rewrite","cases":[{"id":"exact","schedule":"only","paths":[ne],"mutations":[{"path":ne,"parameter":"type","expected":AD,"value":NONAD},{"path":ne,"parameter":"functor","expected":"n_e_physical","value":"n_e"},{"path":ne,"parameter":"prefactor","expected":None,"value":"${n_e_value}"}]}]}
    n=_validate_packet(p); text,e=_apply(_zero_base()[0],n["cases"][0]); checks.update({"type":mp.get_parameter(text,ne,"type")==NONAD,"functor":mp.get_parameter(text,ne,"functor")=="n_e","prefactor":mp.get_parameter(text,ne,"prefactor")=="${n_e_value}","defer56":e["deferred_count"]==56})
    try:
        bad=json.loads(json.dumps(p)); bad["cases"][0]["mutations"][1]["expected"]="wrong"; _validate_packet(bad); checks["mismatch_rejected"]=False
    except Issue224DepthError: checks["mismatch_rejected"]=True
    failed=sorted(k for k,v in checks.items() if not v); return {"status":"PASS" if not failed else "FAIL","checks":checks,"failed_checks":failed}

def main():
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument("--physics-opt",type=Path); ap.add_argument("--results-root",type=Path); ap.add_argument("--packet-json"); ap.add_argument("--timeout",type=float,default=1800); ap.add_argument("--self-test",action="store_true"); ap.add_argument("--validate-packet-json"); a=ap.parse_args()
    if a.self_test:
        r=self_test(); print(json.dumps(r,indent=2,sort_keys=True)); return 0 if r["status"]=="PASS" else 1
    if a.validate_packet_json is not None: print(json.dumps(_validate_packet(json.loads(a.validate_packet_json)),indent=2,sort_keys=True)); return 0
    if None in (a.physics_opt,a.results_root,a.packet_json): ap.error("runtime arguments required")
    p=_validate_packet(json.loads(a.packet_json)); exe=a.physics_opt.resolve()
    if not exe.is_file() or not os.access(exe,os.X_OK): raise Issue224DepthError(f"invalid physics-opt: {exe}")
    p0=self_test(); out=a.results_root.resolve(); out.mkdir(parents=True,exist_ok=True); (out/"requested_packet.json").write_text(json.dumps(p,indent=2,sort_keys=True)+"\n"); (out/"p0.json").write_text(json.dumps(p0,indent=2,sort_keys=True)+"\n")
    if p0["status"]!="PASS": raise Issue224DepthError(f"P0 failed: {p0}")
    s=_run_zero(exe,out,p,a.timeout) if p["regime"]=="zero_step" else _run_phys(exe,out,p,a.timeout); s["p0"]=p0; _write(out,s); print((out/"summary.json").read_text()); return 0 if s["status"]=="ISSUE224_DEPTH_EVIDENCE_READY" else 3

if __name__ == "__main__": raise SystemExit(main())
