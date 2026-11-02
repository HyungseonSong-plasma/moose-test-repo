#!/usr/bin/env python3
"""Provenance-guarded 400W native Oxygen25 1ms→4ms single-job experiment.

The Stage5 DIRECT 100us→1ms source checkpoint (Run 41358545575) is
immutable. Continue exact 400W physics/chemistry/RF PID and native state
with IterationAdaptiveDT dtmax=10us, reset_dt=true; 300 requested 10us
intervals do NOT assert 300 actual steps, convergence, or steady state.
This study is independent of the 1000W RF oscillation HOLD and Stage6 10ms.
"""
from __future__ import annotations

import argparse
from decimal import Decimal
import json
from pathlib import Path

import oxygen25_five_stage_plan as original

STUDY = original.Stage(6,1000000,4000000,10000,300)
UPSTREAM_RUN_ID = 41358545575
UPSTREAM_HEAD_SHA = "3d9fb0746f67422ed6d69ff9bd1676fd75f3e770"
UPSTREAM_BRANCH = "experiment/oxygen25-stage5-single-1ms-20261101"
UPSTREAM_ARTIFACT = "oxygen25-stage5-direct-ei936-1000000ns-restart-complete-400W"
UPSTREAM_ARTIFACT_ID = 13107661302
ORIGINAL_STAGE4_RUN_ID = 41310708653
ORIGINAL_STAGE4_SHA = "fdd13f48033b66d49ced6f191bc153090aae9d86"
POWER_W = 400
NS_S = Decimal("1e-9")


def stage(number: int) -> original.Stage:
    if type(number) is not int or number != 6:
        raise ValueError("Only isolated 400W 1ms→4ms experiment stage 6 is permitted")
    return STUDY


def valid_sha(s: object) -> bool:
    return isinstance(s,str) and len(s)==64 and all(c in "0123456789abcdef" for c in s)


def verify_archive_manifest(manifest: dict, endpoint_ns: int) -> None:
    expected = {f"restart_run_{endpoint_ns}ns.tar.gz",
                f"restart_inputs_{endpoint_ns}ns.tar.gz"}
    archives = manifest.get("archives")
    if (not isinstance(archives, dict) or set(archives) != expected or
            any(not isinstance(archives[name],dict)
                or type(archives[name].get("bytes")) is not int
                or archives[name]["bytes"] <= 0
                or not valid_sha(archives[name].get("sha256"))
                for name in expected)):
        raise ValueError("incomplete or invalid native archive SHA256 provenance")


def check_upstream(manifest: dict, number: int, power_w: int,
                   upstream_run_id: int) -> dict:
    stage(number)
    source_checkpoint = manifest.get("stage5_direct_1ms_experiment")
    step = manifest.get("actual_moose_step")
    cp = manifest.get("recovery_requirements",{}).get("native_recover_prefix")
    if (type(power_w) is not int or power_w != POWER_W
            or type(upstream_run_id) is not int or upstream_run_id != UPSTREAM_RUN_ID
            or manifest.get("schema") != 4
            or manifest.get("restart_mode") != "advanced_restart_not_recover"
            or manifest.get("source_sha") != original.SCIENCE_SOURCE_SHA
            or manifest.get("chemistry") != original.CHEMISTRY
            or manifest.get("power_w") != POWER_W
            or manifest.get("scientific_acceptance") != "HOLD"
            or manifest.get("upstream_time_ns") != 100000
            or manifest.get("recovered_time_ns") != STUDY.start_ns
            or (Decimal(str(manifest.get("final_time_s","NaN"))) -
                STUDY.start_ns*NS_S).copy_abs() >= Decimal("1e-15")
            or type(step) is not int or step < 1
            or not isinstance(cp,str) or not cp.endswith(f"/{step:04d}")
            or not isinstance(source_checkpoint,dict)
            or source_checkpoint.get("name") != "stage5_direct_100_to_1000us"
            or source_checkpoint.get("stage") != 5
            or source_checkpoint.get("start_ns") != 100000
            or source_checkpoint.get("end_ns") != 1000000
            or source_checkpoint.get("interval_ns") != 10000
            or source_checkpoint.get("requested_interval_count") != 90
            or source_checkpoint.get("upstream_run_id") != ORIGINAL_STAGE4_RUN_ID
            or source_checkpoint.get("upstream_stage4_head_sha") != ORIGINAL_STAGE4_SHA
            or source_checkpoint.get("baseline_five_stage_plan_sha256") != original.plan_sha256()
            or source_checkpoint.get("source_sha") != original.SCIENCE_SOURCE_SHA
            or source_checkpoint.get("scientific_acceptance") != "HOLD"
            or source_checkpoint.get("timestep_convergence") != "NOT_ESTABLISHED"):
        raise ValueError("upstream Stage5 DIRECT 400W native checkpoint provenance mismatch")
    verify_archive_manifest(manifest, STUDY.start_ns)
    return {
        "from_run": UPSTREAM_RUN_ID,
        "from_head_sha": UPSTREAM_HEAD_SHA,
        "from_branch": UPSTREAM_BRANCH,
        "artifact": UPSTREAM_ARTIFACT,
        "artifact_id": UPSTREAM_ARTIFACT_ID,
        "power_w": power_w,
        "from_ns": STUDY.start_ns,
        "to_ns": STUDY.end_ns,
        "requested_interval_ns": STUDY.requested_spacing_ns,
        "requested_intervals": STUDY.requested_steps,
        "source_sha": original.SCIENCE_SOURCE_SHA,
        "chemistry": original.CHEMISTRY,
        "timestep_convergence_established": False,
    }


def attest(manifest: dict, number: int, power_w: int,
           upstream_run_id: int) -> dict:
    stage(number)
    step=manifest.get("actual_moose_step")
    cp=manifest.get("recovery_requirements",{}).get("native_recover_prefix")
    if (type(power_w) is not int or power_w != POWER_W
            or type(upstream_run_id) is not int or upstream_run_id != UPSTREAM_RUN_ID
            or manifest.get("schema") != 4
            or manifest.get("restart_mode") != "advanced_restart_not_recover"
            or manifest.get("source_sha") != original.SCIENCE_SOURCE_SHA
            or manifest.get("chemistry") != original.CHEMISTRY
            or manifest.get("scientific_acceptance") != "HOLD"
            or manifest.get("power_w") != POWER_W
            or manifest.get("upstream_time_ns") != STUDY.start_ns
            or manifest.get("recovered_time_ns") != STUDY.end_ns
            or type(step) is not int or step < STUDY.requested_steps
            or not isinstance(cp,str) or not cp.endswith(f"/{step:04d}")
            or (Decimal(str(manifest.get("final_time_s","NaN"))) -
                STUDY.end_ns*NS_S).copy_abs() >= Decimal("1e-15")):
        raise ValueError("4ms native 400W P4 checkpoint identity unverified")
    verify_archive_manifest(manifest,STUDY.end_ns)
    result = dict(manifest)
    result["oxygen25_400w_1to4ms_single_6h"] = {
        "experiment": "400w_1ms_to_4ms_single_native_restart",
        "stage": 6,
        "start_ns": STUDY.start_ns,
        "end_ns": STUDY.end_ns,
        "interval_ns": STUDY.requested_spacing_ns,
        "requested_intervals": STUDY.requested_steps,
        "power_w": POWER_W,
        "upstream_run_id": UPSTREAM_RUN_ID,
        "upstream_head_sha": UPSTREAM_HEAD_SHA,
        "upstream_branch": UPSTREAM_BRANCH,
        "upstream_artifact_id": UPSTREAM_ARTIFACT_ID,
        "upstream_artifact_name": UPSTREAM_ARTIFACT,
        "physics_source_sha": original.SCIENCE_SOURCE_SHA,
        "chemistry": original.CHEMISTRY,
        "native_restart_not_csv_state": True,
        "job_timeout_minutes": 360,
        "timestep_convergence": "NOT_ESTABLISHED",
        "scientific_acceptance": "HOLD_BEFORE_STABILITY_ANALYSIS",
        "stage6_100us_10ms_gate": "HOLD",
    }
    return result


def self_test() -> None:
    original.self_test()
    assert STUDY.start_ns == 1000000 and STUDY.end_ns == 4000000
    assert STUDY.requested_spacing_ns == 10000 and STUDY.requested_steps == 300
    assert len(STUDY.endpoints_ns) == 301
    assert original.stage(5).end_ns == 500000
    source={
        "schema":4,"restart_mode":"advanced_restart_not_recover",
        "source_sha":original.SCIENCE_SOURCE_SHA,"power_w":POWER_W,
        "chemistry":original.CHEMISTRY,"scientific_acceptance":"HOLD",
        "upstream_time_ns":100000,"recovered_time_ns":1000000,
        "final_time_s":0.001,"actual_moose_step":121,
        "recovery_requirements":{"native_recover_prefix":"run/0121"},
        "archives":{
            "restart_run_1000000ns.tar.gz":{"sha256":"a"*64,"bytes":20},
            "restart_inputs_1000000ns.tar.gz":{"sha256":"b"*64,"bytes":30}},
        "stage5_direct_1ms_experiment":{
            "name":"stage5_direct_100_to_1000us",
            "stage":5,"start_ns":100000,"end_ns":1000000,
            "interval_ns":10000,"requested_interval_count":90,
            "upstream_run_id":ORIGINAL_STAGE4_RUN_ID,
            "upstream_stage4_head_sha":ORIGINAL_STAGE4_SHA,
            "baseline_five_stage_plan_sha256":original.plan_sha256(),
            "source_sha":original.SCIENCE_SOURCE_SHA,
            "scientific_acceptance":"HOLD",
            "timestep_convergence":"NOT_ESTABLISHED",
        },
    }
    assert check_upstream(source,6,400,UPSTREAM_RUN_ID)["to_ns"] == 4000000
    for bad in (
        {**source,"power_w":1000},
        {**source,"final_time_s":.0005},
        {**source,"archives":{}},
        {**source,"stage5_direct_1ms_experiment":{
            **source["stage5_direct_1ms_experiment"],"end_ns":500000}},
    ):
        try: check_upstream(bad,6,400,UPSTREAM_RUN_ID)
        except ValueError: pass
        else: raise AssertionError("invalid upstream native artifact passed")
    new=dict(source,upstream_time_ns=1000000,recovered_time_ns=4000000,
             actual_moose_step=329,final_time_s=.004,
             recovery_requirements={"native_recover_prefix":"run/0329"},
             archives={
                 "restart_run_4000000ns.tar.gz":{"sha256":"c"*64,"bytes":42},
                 "restart_inputs_4000000ns.tar.gz":{"sha256":"d"*64,"bytes":12},
             })
    assert attest(new,6,400,UPSTREAM_RUN_ID)["oxygen25_400w_1to4ms_single_6h"]["requested_intervals"]==300
    for bad in (
        {**new,"actual_moose_step":299},
        {**new,"final_time_s":.003},
    ):
        try: attest(bad,6,400,UPSTREAM_RUN_ID)
        except ValueError: pass
        else: raise AssertionError("invalid final native checkpoint passed")
    print("OXYGEN25_400W_1TO4MS_SINGLE_6H_EXTENSION_SELFTEST_PASS")


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-test",action="store_true")
    mode.add_argument("--check-upstream",type=Path)
    mode.add_argument("--attest",type=Path)
    p.add_argument("--stage",type=int)
    p.add_argument("--stage-number",type=int)
    p.add_argument("--power-w",type=int)
    p.add_argument("--upstream-run-id",type=int)
    a=p.parse_args()
    if a.self_test:
        self_test()
    elif a.stage is not None:
        print(json.dumps(stage(a.stage).to_record(),sort_keys=True))
    else:
        if (a.stage_number!=6 or a.power_w!=POWER_W
                or a.upstream_run_id!=UPSTREAM_RUN_ID):
            p.error("expected exact --stage-number 6 --power-w 400 --upstream-run-id 41358545575")
        manifest_path = a.check_upstream or a.attest
        assert manifest_path is not None
        manifest=json.loads(manifest_path.read_text())
        if a.check_upstream:
            evidence=check_upstream(manifest,6,400,a.upstream_run_id)
            print("OXYGEN25_400W_1MS_NATIVE_UPSTREAM_ACCEPTED",
                  json.dumps(evidence,sort_keys=True),flush=True)
        else:
            manifest_path.write_text(
                json.dumps(attest(manifest,6,400,a.upstream_run_id),
                           indent=2,sort_keys=True)+"\n")
            print("OXYGEN25_400W_4MS_NATIVE_ATTESTATION_PASS",flush=True)

if __name__ == "__main__":
    main()
