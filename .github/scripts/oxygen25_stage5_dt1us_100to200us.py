#!/usr/bin/env python3
"""Independent 400/1000W native Stage4-checkpoint continuation, 100–200us, dtmax=1us.

The source physics, 25-effective-O(ex)-EI936 chemistry, 100us Stage4 checkpoint,
and RF feedback are unchanged. Stage 5 here is a bounded experimental branch,
not an alteration to the canonical 100–500us Stage 5 plan. Requested intervals
do not imply fixed native adaptive timestep sizes or scientific acceptance.
"""
from __future__ import annotations

import argparse
from decimal import Decimal
import json
from pathlib import Path

import oxygen25_five_stage_plan as original

EXPERIMENT = original.Stage(5, 100000, 200000, 1000, 100)
STAGE4_RUN_ID = 41310708653
STAGE4_HEAD_SHA = "fdd13f48033b66d49ced6f191bc153090aae9d86"
POWERS = (400, 1000)
NS_S = Decimal("1e-9")


def stage(number: int) -> original.Stage:
    if type(number) is not int or number != 5:
        raise ValueError("Only experimental stage 5 is supported")
    return EXPERIMENT


def check_upstream(manifest: dict, number: int, power_w: int,
                   upstream_run_id: int) -> dict:
    stage(number)
    if type(power_w) is not int or power_w not in POWERS:
        raise ValueError("Invalid power")
    if type(upstream_run_id) is not int or upstream_run_id != STAGE4_RUN_ID:
        raise ValueError("Only the exact verified Stage4 100us checkpoint run is authorized")
    proof = original.verify_previous_manifest(manifest, 5, power_w, upstream_run_id)
    return {
        **proof,
        "experiment": "oxygen25_400_1000w_100to200us_dtmax1us",
        "direct_end_ns": EXPERIMENT.end_ns,
        "requested_interval_ns": EXPERIMENT.requested_spacing_ns,
        "requested_interval_count": EXPERIMENT.requested_steps,
        "stage4_head_sha": STAGE4_HEAD_SHA,
    }


def attest(manifest: dict, number: int, power_w: int,
           upstream_run_id: int) -> dict:
    stage(number)
    if (type(power_w) is not int or power_w not in POWERS
            or type(upstream_run_id) is not int
            or upstream_run_id != STAGE4_RUN_ID
            or manifest.get("schema") != 4
            or manifest.get("restart_mode") != "advanced_restart_not_recover"
            or manifest.get("source_sha") != original.SCIENCE_SOURCE_SHA
            or manifest.get("chemistry") != original.CHEMISTRY
            or manifest.get("scientific_acceptance") != "HOLD"
            or manifest.get("power_w") != power_w
            or manifest.get("upstream_time_ns") != EXPERIMENT.start_ns
            or manifest.get("recovered_time_ns") != EXPERIMENT.end_ns
            or type(manifest.get("actual_moose_step")) is not int
            or manifest["actual_moose_step"] < 1
            or (Decimal(str(manifest.get("final_time_s"))) -
                EXPERIMENT.end_ns * NS_S).copy_abs() >= Decimal("1e-15")):
        raise ValueError("Genuine dtmax1us 100-200us native continuation not established")
    expected = {"restart_run_200000ns.tar.gz", "restart_inputs_200000ns.tar.gz"}
    archives = manifest.get("archives", {})
    if (set(archives) != expected or
            not all(a.get("bytes", 0) > 0 and
                    len(str(a.get("sha256", ""))) == 64
                    for a in archives.values())):
        raise ValueError("200us native checkpoint archive SHA256 identity missing")
    result = dict(manifest)
    result["stage5_dt1us_100to200us_experiment"] = {
        "name": "oxygen25_400_1000w_100to200us_dtmax1us",
        "stage": 5,
        "start_ns": EXPERIMENT.start_ns,
        "end_ns": EXPERIMENT.end_ns,
        "interval_ns": EXPERIMENT.requested_spacing_ns,
        "requested_interval_count": EXPERIMENT.requested_steps,
        "upstream_run_id": upstream_run_id,
        "upstream_stage4_head_sha": STAGE4_HEAD_SHA,
        "baseline_five_stage_plan_sha256": original.plan_sha256(),
        "source_sha": original.SCIENCE_SOURCE_SHA,
        "scientific_acceptance": "HOLD",
        "timestep_convergence": "NOT_ESTABLISHED",
        "power_target_w": power_w,
        "unchanged_RF_PID_and_chemistry": True,
    }
    return result


def self_test() -> None:
    original.self_test()
    assert EXPERIMENT.start_ns == original.stage(4).end_ns
    assert EXPERIMENT.end_ns == 200000
    assert EXPERIMENT.requested_spacing_ns == 1000
    assert EXPERIMENT.requested_steps == 100
    assert len(EXPERIMENT.endpoints_ns) == 101
    for power in POWERS:
        sample = {
            "schema": 4,
            "restart_mode": "advanced_restart_not_recover",
            "source_sha": original.SCIENCE_SOURCE_SHA,
            "power_w": power, "chemistry": original.CHEMISTRY,
            "scientific_acceptance": "HOLD",
            "actual_moose_step": 123,
            "final_time_s": 0.0001,
            "recovery_requirements": {"native_recover_prefix": "run/0123"},
            "archives": {
                "restart_run_100000ns.tar.gz": {"sha256": "a" * 64, "bytes": 22},
                "restart_inputs_100000ns.tar.gz": {"sha256": "b" * 64, "bytes": 33},
            },
        }
        source = original.add_attestation(sample, 4, power, upstream_run_id=41294976910)
        proof = check_upstream(source, 5, power, STAGE4_RUN_ID)
        assert proof["direct_end_ns"] == 200000
        for corrupted in ({**source, "power_w": 999},
                          {**source, "final_time_s": 0.0002},
                          {**source, "five_stage_chain":
                           {**source["five_stage_chain"], "stage": 5}}):
            try:
                check_upstream(corrupted, 5, power, STAGE4_RUN_ID)
            except ValueError:
                pass
            else:
                raise AssertionError("Upstream corruption passed guard")
        outgoing = {
            **sample, "final_time_s": 0.0002, "upstream_time_ns": 100000,
            "recovered_time_ns": 200000,
            "archives": {
                "restart_run_200000ns.tar.gz": {"sha256": "c"*64, "bytes": 22},
                "restart_inputs_200000ns.tar.gz": {"sha256": "d"*64, "bytes": 33},
            },
        }
        assert attest(outgoing, 5, power, STAGE4_RUN_ID)["stage5_dt1us_100to200us_experiment"]["interval_ns"] == 1000
    print("OXYGEN25_400_1000W_100TO200US_DTMAX1US_SELFTEST_PASS")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-test", action="store_true")
    mode.add_argument("--stage", type=int)
    mode.add_argument("--check-upstream", type=Path)
    mode.add_argument("--attest", type=Path)
    parser.add_argument("--stage-number", type=int)
    parser.add_argument("--power-w", type=int)
    parser.add_argument("--upstream-run-id", type=int)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.stage is not None:
        print(json.dumps(stage(args.stage).to_record(), sort_keys=True))
        return
    if args.stage_number != 5 or args.power_w not in POWERS or args.upstream_run_id is None:
        parser.error("Expected --stage-number 5 --power-w 400|1000 --upstream-run-id")
    if args.check_upstream:
        check_upstream(json.loads(args.check_upstream.read_text()), 5,
                       args.power_w, args.upstream_run_id)
        print("OXYGEN25_DT1US_UPSTREAM_ACCEPTED", args.power_w)
    elif args.attest:
        m = json.loads(args.attest.read_text())
        args.attest.write_text(json.dumps(
            attest(m, 5, args.power_w, args.upstream_run_id),
            sort_keys=True, indent=2) + "\n")
        print("OXYGEN25_DT1US_NATIVE_ATTESTATION_PASS", args.power_w)


if __name__ == "__main__":
    main()
