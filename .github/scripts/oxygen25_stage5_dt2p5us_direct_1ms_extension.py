#!/usr/bin/env python3
"""Provenance-guarded independent 1000W Stage 5 100us-to-1ms dtmax=2.5us direct experiment.

The original 0–500us five-stage plan and accepted Stage4 checkpoint
are immutable. This independent branch tests whether continuing directly
100us→1000us with 360 requested 2.5us intervals differs from the 5us/10us controls.
A successful native runtime is not evidence of timestep convergence or scientific acceptance.
"""
from __future__ import annotations

import argparse
from decimal import Decimal
import json
from pathlib import Path

import oxygen25_five_stage_plan as original

EXPERIMENT = original.Stage(5, 100000, 1000000, 2500, 360)
STAGE4_RUN_ID = 41310708653
STAGE4_HEAD_SHA = "fdd13f48033b66d49ced6f191bc153090aae9d86"
REFERENCE_CHAIN_STAGE6_RUN_ID = 41347038089
NS_S = Decimal("1e-9")


def stage(number: int) -> original.Stage:
    if type(number) is not int or number != 5:
        raise ValueError("Stage5 direct 1ms experiment supports stage 5 only")
    return EXPERIMENT


def check_upstream(manifest: dict, number: int, power_w: int,
                   upstream_run_id: int) -> dict:
    stage(number)
    if type(upstream_run_id) is not int or upstream_run_id != STAGE4_RUN_ID:
        raise ValueError("Only the exact previously validated Stage4 run is accepted")
    proof = original.verify_previous_manifest(manifest, 5, power_w, upstream_run_id)
    return {**proof,
            "experiment": "stage5_1000w_100to1000us_dt2p5us",
            "direct_end_ns": EXPERIMENT.end_ns,
            "direct_requested_intervals": EXPERIMENT.requested_steps,
            "reference_stage6_run_id": REFERENCE_CHAIN_STAGE6_RUN_ID}


def attest(manifest: dict, number: int, power_w: int,
           upstream_run_id: int) -> dict:
    stage(number)
    if (power_w != 1000 or type(power_w) is not int
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
            or not isinstance(manifest.get("actual_moose_step"), int)
            or manifest["actual_moose_step"] < 1
            or (Decimal(str(manifest.get("final_time_s"))) -
                EXPERIMENT.end_ns * NS_S).copy_abs() >= Decimal("1e-15")):
        raise ValueError("Genuine 1ms native dt2p5us direct continuation not established")
    expected = {
        "restart_run_1000000ns.tar.gz",
        "restart_inputs_1000000ns.tar.gz",
    }
    archives = manifest.get("archives", {})
    if set(archives) != expected or not all(
            archives[key].get("bytes", 0) > 0 and
            len(str(archives[key].get("sha256", ""))) == 64
            for key in expected):
        raise ValueError("1ms dt2p5us archive SHA256 identity incomplete")
    result = dict(manifest)
    result["stage5_dt2p5us_direct_1ms_experiment"] = {
        "name": "stage5_1000w_100to1000us_dt2p5us",
        "stage": 5,
        "start_ns": EXPERIMENT.start_ns,
        "end_ns": EXPERIMENT.end_ns,
        "interval_ns": EXPERIMENT.requested_spacing_ns,
        "requested_interval_count": EXPERIMENT.requested_steps,
        "upstream_run_id": upstream_run_id,
        "upstream_stage4_head_sha": STAGE4_HEAD_SHA,
        "baseline_five_stage_plan_sha256": original.plan_sha256(),
        "source_sha": original.SCIENCE_SOURCE_SHA,
        "reference_stage6_run_id": REFERENCE_CHAIN_STAGE6_RUN_ID,
        "scientific_acceptance": "HOLD",
        "timestep_convergence": "NOT_ESTABLISHED",
        "comparison_to_two_restart_chain": "PENDING",
    }
    return result


def self_test() -> None:
    original.self_test()
    assert EXPERIMENT.start_ns == original.stage(4).end_ns
    assert EXPERIMENT.end_ns == 1000000
    assert len(EXPERIMENT.endpoints_ns) == 361
    assert EXPERIMENT.requested_steps == 360
    assert original.stage(5).end_ns == 500000
    sample = {
        "schema": 4,
        "restart_mode": "advanced_restart_not_recover",
        "source_sha": original.SCIENCE_SOURCE_SHA,
        "power_w": 1000, "chemistry": original.CHEMISTRY,
        "scientific_acceptance": "HOLD",
        "actual_moose_step": 123,
        "final_time_s": 0.0001,
        "recovery_requirements": {"native_recover_prefix": "run/0123"},
        "archives": {
            "restart_run_100000ns.tar.gz": {"sha256": "a" * 64, "bytes": 22},
            "restart_inputs_100000ns.tar.gz": {"sha256": "b" * 64, "bytes": 33},
        },
    }
    original.add_attestation(sample, 4, 1000, upstream_run_id=41294976910)
    sample = original.add_attestation(sample, 4, 1000, upstream_run_id=41294976910)
    assert check_upstream(sample, 5, 1000, STAGE4_RUN_ID)["direct_end_ns"] == 1000000
    for corrupted in (
        {**sample, "power_w": 400},
        {**sample, "final_time_s": 0.0005},
        {**sample, "five_stage_chain": {**sample["five_stage_chain"], "stage": 5}},
    ):
        try:
            check_upstream(corrupted, 5, 1000, STAGE4_RUN_ID)
        except ValueError:
            pass
        else:
            raise AssertionError("Stage4 corruption passed Stage5 direct gate")
    print("OXYGEN25_STAGE5_1000W_DT2P5US_DIRECT_1MS_EXTENSION_SELFTEST_PASS")


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
    if args.stage_number != 5 or args.power_w != 1000 or args.upstream_run_id is None:
        parser.error("Expected --stage-number 5 --power-w --upstream-run-id")
    if args.check_upstream:
        check_upstream(json.loads(args.check_upstream.read_text()), 5,
                       args.power_w, args.upstream_run_id)
        print("OXYGEN25_STAGE5_1000W_DT2P5US_DIRECT_1MS_UPSTREAM_ACCEPTED", args.power_w)
    elif args.attest:
        m = json.loads(args.attest.read_text())
        args.attest.write_text(json.dumps(
            attest(m, 5, args.power_w, args.upstream_run_id),
            sort_keys=True, indent=2) + "\n")
        print("OXYGEN25_STAGE5_1000W_DT2P5US_DIRECT_1MS_NATIVE_ATTESTATION_PASS", args.power_w)


if __name__ == "__main__":
    main()
