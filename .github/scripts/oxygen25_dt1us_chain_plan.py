#!/usr/bin/env python3
"""Fail-closed independent 1000 W Oxygen25 dtmax=1us native 100us→1ms study.

Five separate GitHub Actions jobs hand off *native MOOSE* checkpoints:
100→300→500→700→900→1000us. No CSV state synthesis and no changes to
original Stage4, accepted Stage5, 2.5us trial, RF feedback or chemistry.
The 1us cap is experimental; success is not numerical convergence or
permission for the independent 1ms→10ms dtmax=100us Stage6.
"""
from __future__ import annotations

import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path

import oxygen25_five_stage_plan as original

SEGMENTS = (
    (100000, 300000),
    (300000, 500000),
    (500000, 700000),
    (700000, 900000),
    (900000, 1000000),
)
SPACING_NS = 1000
POWER_W = 1000
STAGE4_RUN_ID = 41310708653
STAGE4_HEAD_SHA = "fdd13f48033b66d49ced6f191bc153090aae9d86"
SOURCE_SHA = original.SCIENCE_SOURCE_SHA
SCIENTIFIC_DECISION = "HOLD_STAGE6_10MS"
NS_S = Decimal("1e-9")


def chain_sha256() -> str:
    spec = {
        "plan": "oxygen25_1000W_100_to_1000us_dtmax_1us_native_segments",
        "segments": SEGMENTS,
        "spacing_ns": SPACING_NS,
        "power_w": POWER_W,
        "source_sha": SOURCE_SHA,
        "chemistry": original.CHEMISTRY,
        "stage4_run_id": STAGE4_RUN_ID,
        "stage4_head_sha": STAGE4_HEAD_SHA,
        "original_five_stage_plan_sha256": original.plan_sha256(),
    }
    return hashlib.sha256(json.dumps(
        spec, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def index_for(start: int, end: int) -> int:
    if type(start) is not int or type(end) is not int:
        raise ValueError("segment endpoints must be integers")
    if (start, end) not in SEGMENTS:
        raise ValueError("unapproved dt1us segment or boundary")
    return SEGMENTS.index((start,end))


def validate_manifest_identity(m: dict, *, time_ns: int, power_w: int) -> None:
    cp = m.get("recovery_requirements", {}).get("native_recover_prefix")
    native = m.get("actual_moose_step")
    expected_archives = {
        f"restart_run_{time_ns}ns.tar.gz",
        f"restart_inputs_{time_ns}ns.tar.gz",
    }
    archives = m.get("archives", {})
    if (type(power_w) is not int or power_w != POWER_W
        or m.get("schema") != 4
        or m.get("restart_mode") != "advanced_restart_not_recover"
        or m.get("power_w") != power_w
        or m.get("source_sha") != SOURCE_SHA
        or m.get("chemistry") != original.CHEMISTRY
        or m.get("scientific_acceptance") != "HOLD"
        or (Decimal(str(m.get("final_time_s", "NaN")))
            - Decimal(time_ns)*NS_S).copy_abs() >= Decimal("1e-15")
        or type(native) is not int or native < 1
        or not isinstance(cp,str) or not cp.endswith(f"/{native:04d}")
        or m.get("recovery_requirements", {}).get("native_recover_prefix") != m.get("checkpoint_prefix")
        or set(archives) != expected_archives
        or any(type(archives[key].get("bytes")) is not int
               or archives[key]["bytes"] <= 0
               or not isinstance(archives[key].get("sha256"),str)
               or len(archives[key]["sha256"]) != 64
               or any(char not in "0123456789abcdef" for char in archives[key]["sha256"])
               for key in expected_archives)):
        raise ValueError("invalid native checkpoint manifest identity or SHA256 inventory")


def check_upstream(m: dict, start: int, end: int,
                   power_w: int, upstream_run_id: int) -> dict:
    idx = index_for(start,end)
    if type(upstream_run_id) is not int or upstream_run_id <= 0:
        raise ValueError("must pin actual upstream GitHub run ID")
    if idx == 0:
        if upstream_run_id != STAGE4_RUN_ID:
            raise ValueError("first segment must use exact successful Stage4 run")
        # Staged Stage4 provenance is checked by the original immutable plan.
        original.verify_previous_manifest(
            m, number=5, power=power_w, upstream_run_id=upstream_run_id)
        validate_manifest_identity(m,time_ns=start,power_w=power_w)
    else:
        validate_manifest_identity(m,time_ns=start,power_w=power_w)
        prev = m.get("dt1us_chain")
        if (not isinstance(prev,dict)
            or prev.get("chain_sha256") != chain_sha256()
            or prev.get("segment_index") != idx-1
            or prev.get("start_ns") != SEGMENTS[idx-1][0]
            or prev.get("end_ns") != start
            or prev.get("interval_ns") != SPACING_NS
            or prev.get("power_w") != POWER_W
            or prev.get("workflow_run_id") != upstream_run_id
            or prev.get("source_sha") != SOURCE_SHA
            or prev.get("original_stage4_run_id") != STAGE4_RUN_ID):
            raise ValueError("previous dt1us native chain attestation invalid")
    return {
        "segment_index": idx,
        "start_ns": start, "end_ns": end,
        "power_w": power_w, "upstream_run_id": upstream_run_id,
        "chain_sha256": chain_sha256(),
        "requested_interval_ns": SPACING_NS,
        "requested_intervals": (end-start)//SPACING_NS,
    }


def attest(m: dict,start: int,end: int,power_w: int,
           upstream_run_id: int, workflow_run_id: int) -> dict:
    idx=index_for(start,end)
    if (type(workflow_run_id) is not int or workflow_run_id <= 0
        or (idx==0 and upstream_run_id != STAGE4_RUN_ID)
        or (idx>0 and upstream_run_id != workflow_run_id)
        or m.get("upstream_time_ns") != start
        or m.get("recovered_time_ns") != end):
        raise ValueError("unapproved new native stage provenance")
    validate_manifest_identity(m,time_ns=end,power_w=power_w)
    target_interval = m.get("time_sequence_s")
    if (not isinstance(target_interval,list)
        or len(target_interval) < (end-start)//SPACING_NS
        or not isinstance(m.get("stage_csv_file"),str)
        or not isinstance(m.get("latest_exodus_file"),str)
        or not isinstance(m.get("restart_source_prefix"),str)):
        raise ValueError("missing genuine native stage CSV, Exodus, or restart identity")
    expected_inputs = f"restart_inputs_{end}ns.tar.gz"
    if expected_inputs not in m["archives"]:
        raise ValueError("missing hashed restart inputs")
    result=dict(m)
    result["dt1us_chain"] = {
        "chain_sha256": chain_sha256(),
        "segment_index": idx,
        "start_ns": start, "end_ns": end,
        "interval_ns": SPACING_NS,
        "requested_intervals": (end-start)//SPACING_NS,
        "power_w": POWER_W,
        "source_sha": SOURCE_SHA,
        "original_stage4_run_id": STAGE4_RUN_ID,
        "original_stage4_head_sha": STAGE4_HEAD_SHA,
        "workflow_run_id": workflow_run_id,
        "upstream_run_id": upstream_run_id,
        "checkpoint_mode": "native_cross_job_advanced_restart_only",
        "scientific_decision": SCIENTIFIC_DECISION,
        "dtmax_100us_validated": False,
        "timestep_converged": False,
    }
    return result


def self_test() -> None:
    original.self_test()
    assert len(SEGMENTS)==5
    assert SEGMENTS[0][0] == original.stage(4).end_ns
    assert SEGMENTS[-1][1] == 1000000
    assert all(SEGMENTS[i][1]==SEGMENTS[i+1][0] for i in range(4))
    assert sum((e-s)//SPACING_NS for s,e in SEGMENTS)==900
    assert [(e-s)//SPACING_NS for s,e in SEGMENTS]==[200,200,200,200,100]
    assert len(chain_sha256())==64
    for k,(s,e) in enumerate(SEGMENTS):
        assert index_for(s,e)==k
    for bad in ((100000,1000000),(100000,500000),(500000,300000)):
        try: index_for(*bad)
        except ValueError: pass
        else: raise AssertionError("unreviewed chunk accepted")
    stage4 = {
        "schema": 4, "restart_mode": "advanced_restart_not_recover",
        "power_w": POWER_W, "source_sha": SOURCE_SHA,
        "chemistry": original.CHEMISTRY,
        "scientific_acceptance": "HOLD",
        "final_time_s": 0.0001,
        "actual_moose_step": 321,
        "recovery_requirements": {"native_recover_prefix": "run/0321"},
        "checkpoint_prefix": "run/0321",
        "archives": {
            "restart_run_100000ns.tar.gz":{"sha256":"a"*64,"bytes":200},
            "restart_inputs_100000ns.tar.gz":{"sha256":"b"*64,"bytes":100},
        },
    }
    stage4 = original.add_attestation(stage4,4,POWER_W,upstream_run_id=41294976910)
    assert check_upstream(stage4,100000,300000,POWER_W,STAGE4_RUN_ID)["segment_index"]==0
    for corrupt in (
        {**stage4, "power_w":400},
        {**stage4,"five_stage_chain":{**stage4["five_stage_chain"],"stage":5}},
        {**stage4,"archives":{}},
    ):
        try: check_upstream(corrupt,100000,300000,POWER_W,STAGE4_RUN_ID)
        except ValueError: pass
        else: raise AssertionError("corrupt Stage4 provenance accepted")
    test_id = 88888
    prior = dict(stage4)
    for i,(s,e) in enumerate(SEGMENTS):
        prior["final_time_s"] = e*1e-9
        prior["checkpoint_prefix"]=f"run/{321+i+1:04d}"
        prior["recovery_requirements"]={"native_recover_prefix": prior["checkpoint_prefix"]}
        prior["archives"] = {
            f"restart_run_{e}ns.tar.gz": {"sha256":"c"*64,"bytes":300},
            f"restart_inputs_{e}ns.tar.gz": {"sha256":"d"*64,"bytes":80},
        }
        prior["upstream_time_ns"]=s
        prior["recovered_time_ns"]=e
        prior["actual_moose_step"]=322+i
        prior["time_sequence_s"]=[0.0,1e-4,e*1e-9]+[e*1e-9]*((e-s)//SPACING_NS)
        prior["stage_csv_file"]="run/plasma_restart.csv"
        prior["latest_exodus_file"]="run/plasma_restart.e"
        prior["restart_source_prefix"]="run/prefix"
        prior=attest(prior,s,e,POWER_W,STAGE4_RUN_ID if i==0 else test_id,test_id)
        if i<4:
            assert check_upstream(prior,SEGMENTS[i+1][0],SEGMENTS[i+1][1],
                                  POWER_W,test_id)["segment_index"]==i+1
    print("OXYGEN25_DT1US_NATIVE_CHAIN_PLAN_SELFTEST_PASS")


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    modes=p.add_mutually_exclusive_group(required=True)
    modes.add_argument("--self-test",action="store_true")
    modes.add_argument("--check-upstream",type=Path)
    modes.add_argument("--attest",type=Path)
    p.add_argument("--start-ns",type=int)
    p.add_argument("--end-ns",type=int)
    p.add_argument("--power-w",type=int)
    p.add_argument("--upstream-run-id",type=int)
    p.add_argument("--workflow-run-id",type=int)
    a=p.parse_args()
    if a.self_test:
        self_test()
        return
    if None in (a.start_ns,a.end_ns,a.power_w,a.upstream_run_id):
        p.error("missing required exact native segment arguments")
    if a.check_upstream:
        result=check_upstream(json.loads(a.check_upstream.read_text()),
                              a.start_ns,a.end_ns,a.power_w,a.upstream_run_id)
        print("OXYGEN25_DT1US_UPSTREAM_NATIVE_ACCEPTED",
              json.dumps(result,sort_keys=True),flush=True)
    if a.attest:
        if a.workflow_run_id is None:
            p.error("--workflow-run-id is required for new checkpoint attestation")
        m=json.loads(a.attest.read_text())
        result=attest(m,a.start_ns,a.end_ns,a.power_w,
                      a.upstream_run_id,a.workflow_run_id)
        a.attest.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
        print("OXYGEN25_DT1US_NATIVE_SEGMENT_ATTESTED",
              a.start_ns,a.end_ns,a.workflow_run_id,flush=True)


if __name__=="__main__":
    main()
