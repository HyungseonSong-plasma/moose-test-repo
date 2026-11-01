#!/usr/bin/env python3
"""Stage 6 (500 us to 1 ms) extension without rewriting the accepted five-stage plan.

The Stage 5 plan SHA and checkpoint remain immutable; Stage 6 receives a
separate extension attestation. Successful numerical continuation does not
claim physical steady state or timestep convergence.
"""
from __future__ import annotations

import argparse
from decimal import Decimal
import json
from pathlib import Path

import oxygen25_five_stage_plan as base

STAGE = base.Stage(6, 500000, 1000000, 10000, 50)
STAGE5_RUN_ID = 41324754911
STAGE5_SHA = "51380b301db44c204a998de87ec8f052ece0f3b0"
NS_S = Decimal("1e-9")


def stage(number: int) -> base.Stage:
    if type(number) is not int or number != 6:
        raise ValueError("Stage6 extension accepts stage 6 only")
    return STAGE


def check_upstream(manifest: dict, number: int, power: int, run_id: int) -> dict:
    s = stage(number)
    prev = base.stage(5)
    if type(power) is not int or power not in (400, 1000):
        raise ValueError("Stage6 power is restricted to 400 W or 1000 W")
    if type(run_id) is not int or run_id != STAGE5_RUN_ID:
        raise ValueError("Stage6 requires the exact accepted Stage5 run ID")
    chain = manifest.get("five_stage_chain")
    native_step = manifest.get("actual_moose_step")
    prefix = manifest.get("recovery_requirements", {}).get("native_recover_prefix")
    if (not isinstance(chain, dict)
            or manifest.get("schema") != 4
            or manifest.get("restart_mode") != "advanced_restart_not_recover"
            or chain.get("plan_sha256") != base.plan_sha256()
            or chain.get("stage") != 5
            or chain.get("start_ns") != prev.start_ns
            or chain.get("end_ns") != prev.end_ns
            or chain.get("interval_ns") != prev.requested_spacing_ns
            or chain.get("requested_step_count") != prev.requested_steps
            or chain.get("power_w") != power
            or manifest.get("power_w") != power
            or manifest.get("source_sha") != base.SCIENCE_SOURCE_SHA
            or manifest.get("chemistry") != base.CHEMISTRY
            or manifest.get("scientific_acceptance") != "HOLD"
            or not isinstance(native_step, int) or native_step < 1
            or not isinstance(prefix, str)
            or not prefix.endswith(f"/{native_step:04d}")
            or (Decimal(str(manifest.get("final_time_s"))) -
                prev.end_ns * NS_S).copy_abs() >= Decimal("1e-15")):
        raise ValueError("Stage5 native checkpoint/provenance does not match the accepted baseline")
    expected = {
        f"restart_run_{prev.end_ns}ns.tar.gz",
        f"restart_inputs_{prev.end_ns}ns.tar.gz",
    }
    archives = manifest.get("archives", {})
    if set(archives) != expected or not all(
        archives[n].get("bytes", 0) > 0 and
        len(str(archives[n].get("sha256", ""))) == 64 for n in expected
    ):
        raise ValueError("Stage5 archive identities missing")
    return {
        "from_stage": 5, "to_stage": s.number,
        "start_ns": s.start_ns, "end_ns": s.end_ns,
        "power_w": power, "upstream_run_id": run_id,
        "baseline_plan_sha256": base.plan_sha256(),
    }


def attest(manifest: dict, number: int, power: int, run_id: int) -> dict:
    stage(number)
    if (type(power) is not int or power not in (400, 1000)
            or type(run_id) is not int or run_id != STAGE5_RUN_ID
            or manifest.get("schema") != 4
            or manifest.get("power_w") != power
            or manifest.get("source_sha") != base.SCIENCE_SOURCE_SHA
            or manifest.get("chemistry") != base.CHEMISTRY
            or manifest.get("scientific_acceptance") != "HOLD"
            or manifest.get("restart_mode") != "advanced_restart_not_recover"
            or manifest.get("upstream_time_ns") != STAGE.start_ns
            or manifest.get("recovered_time_ns") != STAGE.end_ns
            or not isinstance(manifest.get("actual_moose_step"), int)
            or manifest["actual_moose_step"] < 1
            or (Decimal(str(manifest.get("final_time_s"))) -
                STAGE.end_ns * NS_S).copy_abs() >= Decimal("1e-15")):
        raise ValueError("Stage6 attestation requires genuine 1ms native completion")
    result = dict(manifest)
    result["stage6_extension"] = dict(
        stage=6,
        start_ns=STAGE.start_ns,
        end_ns=STAGE.end_ns,
        requested_interval_ns=STAGE.requested_spacing_ns,
        requested_intervals=STAGE.requested_steps,
        upstream_run_id=run_id,
        upstream_head_sha=STAGE5_SHA,
        original_five_stage_plan_sha256=base.plan_sha256(),
        physics_source_sha=base.SCIENCE_SOURCE_SHA,
        scientific_steady_state="NOT_ESTABLISHED",
        numerical_convergence="NOT_ESTABLISHED",
        checkpoint_ownership="independent-CI-native-advanced-restart",
    )
    return result


def self_test() -> None:
    base.self_test()
    assert STAGE.to_record() == {
        "stage": 6, "start_ns": 500000, "end_ns": 1000000,
        "interval_ns": 10000, "steps": 50, "requested_grid_points": 51,
    }
    assert STAGE.endpoints_ns[0] == base.stage(5).end_ns
    assert STAGE.endpoints_ns[-1] == 1000000
    assert len(STAGE.endpoints_ns) == 51
    native = dict(
        schema=4,
        restart_mode="advanced_restart_not_recover",
        source_sha=base.SCIENCE_SOURCE_SHA, power_w=400,
        chemistry=base.CHEMISTRY, final_time_s=0.0005,
        actual_moose_step=123, scientific_acceptance="HOLD",
        recovery_requirements={"native_recover_prefix": "x/0123"},
        archives={
            "restart_run_500000ns.tar.gz": {"sha256": "a" * 64, "bytes": 5},
            "restart_inputs_500000ns.tar.gz": {"sha256": "b" * 64, "bytes": 7},
        },
    )
    native = base.add_attestation(native, 5, 400, upstream_run_id=41310708653)
    assert check_upstream(native, 6, 400, STAGE5_RUN_ID)["to_stage"] == 6
    for corrupted in (
        dict(native, power_w=1000),
        dict(native, final_time_s=0.00051),
        dict(native, five_stage_chain={**native["five_stage_chain"], "plan_sha256": "0" * 64}),
    ):
        try:
            check_upstream(corrupted, 6, 400, STAGE5_RUN_ID)
        except ValueError:
            pass
        else:
            raise AssertionError("Stage6 upstream identity mutation unexpectedly passed")
    print("OXYGEN25_STAGE6_1MS_EXTENSION_SELFTEST_PASS")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-test", action="store_true")
    mode.add_argument("--stage", type=int)
    mode.add_argument("--check-upstream", type=Path)
    mode.add_argument("--attest", type=Path)
    p.add_argument("--stage-number", type=int)
    p.add_argument("--power-w", type=int)
    p.add_argument("--upstream-run-id", type=int)
    args = p.parse_args()
    if args.self_test:
        self_test()
        return
    if args.stage is not None:
        print(json.dumps(stage(args.stage).to_record(), sort_keys=True))
        return
    if args.stage_number != 6 or args.power_w not in (400, 1000) or args.upstream_run_id is None:
        p.error("Stage6 requires --stage-number 6, --power-w, --upstream-run-id")
    if args.check_upstream:
        check_upstream(json.loads(args.check_upstream.read_text()), 6,
                       args.power_w, args.upstream_run_id)
        print("OXYGEN25_STAGE6_UPSTREAM_MANIFEST_PASS", args.power_w)
    elif args.attest:
        record = json.loads(args.attest.read_text())
        args.attest.write_text(json.dumps(
            attest(record, 6, args.power_w, args.upstream_run_id),
            sort_keys=True, indent=2) + "\n")
        print("OXYGEN25_STAGE6_1MS_NATIVE_ATTESTATION_PASS", args.power_w)


if __name__ == "__main__":
    main()
