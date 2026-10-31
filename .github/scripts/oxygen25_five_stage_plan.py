#!/usr/bin/env python3
"""Fail-closed Oxygen25 five-stage 0→500us *requested-target* schedule.

A stage is a separate native CI run and checkpoint. Only stage 1 is a fresh
initialization; stages 2–5 require the immediately previous stage's exact
native checkpoint artifact and independently verified SHA256 manifest.
Requested grid points do not guarantee that native adaptive solver steps
exactly coincide with them or that large dt is numerically stable.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
from pathlib import Path

SCIENCE_SOURCE_SHA = "8e2fe042dbc204b5fda22d346f1ad8d2e32db3ab"
CHEMISTRY = "25-effective-O(ex)-EI936"
PLANNER_SCHEMA = 1
NS_S = Decimal("1e-9")

@dataclass(frozen=True)
class Stage:
    number: int
    start_ns: int
    end_ns: int
    requested_spacing_ns: int
    requested_steps: int

    @property
    def name(self) -> str:
        return f"stage-{self.number}"

    @property
    def endpoints_ns(self) -> list[int]:
        return list(range(self.start_ns, self.end_ns + 1, self.requested_spacing_ns))

    @property
    def end_us(self) -> int | float:
        result = Decimal(self.end_ns) / Decimal(1000)
        return int(result) if result == int(result) else float(result)

    def to_record(self) -> dict:
        return dict(stage=self.number, start_ns=self.start_ns, end_ns=self.end_ns,
                    interval_ns=self.requested_spacing_ns, steps=self.requested_steps,
                    requested_grid_points=self.requested_steps + 1)

STAGES = (
    Stage(1, 0, 100, 1, 100),
    Stage(2, 100, 2000, 10, 190),
    Stage(3, 2000, 10000, 100, 80),
    Stage(4, 10000, 100000, 1000, 90),
    Stage(5, 100000, 500000, 10000, 40),
)

def grid_ns() -> list[int]:
    values = [0]
    for s in STAGES:
        if values[-1] != s.start_ns or (
            s.end_ns - s.start_ns != s.requested_steps * s.requested_spacing_ns
        ):
            raise ValueError("stage target boundary or step count inconsistent")
        values.extend(s.endpoints_ns[1:])
    if len(values) != 501 or values[-1] != 500000 or len(set(values)) != 501:
        raise ValueError("0–500us grid is not exactly 500 ordered intervals")
    return values

def stage(number: int) -> Stage:
    if type(number) is not int or number not in range(1, 6):
        raise ValueError("stage_number must be integer 1..5")
    return STAGES[number - 1]

def plan() -> dict:
    result = dict(schema=PLANNER_SCHEMA, science_source_sha=SCIENCE_SOURCE_SHA,
                  chemistry=CHEMISTRY, final_end_ns=500000,
                  total_requested_steps=500, total_requested_points=501,
                  stages=[s.to_record() for s in STAGES],
                  grid_ns_sha256=hashlib.sha256(
                      json.dumps(grid_ns(), separators=(",", ":")).encode()
                  ).hexdigest())
    return result

def plan_sha256() -> str:
    return hashlib.sha256(
        json.dumps(plan(), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

def upstream_artifact_name(number: int, power: int) -> str:
    s = stage(number)
    if power not in (400, 1000) or number == 1:
        raise ValueError("only a post-initial stage has an upstream artifact")
    previous = stage(number - 1)
    if number == 2:
        return f"oxygen25-ei936-{previous.end_ns}ns-initial-checkpoint-complete-{power}W"
    return f"oxygen25-ei936-{previous.end_ns}ns-restart-complete-{power}W"

def verify_previous_manifest(manifest: dict, number: int, power: int,
                             upstream_run_id: int) -> dict:
    s = stage(number)
    if number == 1:
        raise ValueError("stage1 has no previous checkpoint")
    if type(upstream_run_id) is not int or upstream_run_id <= 0:
        raise ValueError("upstream_run_id must be positive and exact")
    previous = stage(number - 1)
    expected_prefix = manifest.get("recovery_requirements", {}).get("native_recover_prefix")
    source = manifest.get("source_sha")
    meta = manifest.get("five_stage_chain")
    if (not isinstance(meta, dict) or meta.get("plan_sha256") != plan_sha256() or
            meta.get("stage") != previous.number or
            meta.get("start_ns") != previous.start_ns or
            meta.get("end_ns") != previous.end_ns or
            meta.get("interval_ns") != previous.requested_spacing_ns or
            meta.get("power_w") != power or
            manifest.get("power_w") != power or
            source != SCIENCE_SOURCE_SHA or manifest.get("chemistry") != CHEMISTRY or
            manifest.get("scientific_acceptance") != "HOLD" or
            not isinstance(expected_prefix, str) or
            not expected_prefix.endswith(f"/{manifest.get('actual_moose_step',-1):04d}") or
            not isinstance(manifest.get("actual_moose_step"), int) or
            not (Decimal(str(manifest.get("final_time_s"))) - previous.end_ns * NS_S).copy_abs() < Decimal("1e-15")):
        raise ValueError("upstream artifact source, stage, final time or checkpoint identity mismatch")
    if len(manifest.get("archives", {})) != 2 or not all(
        v.get("sha256") and v.get("bytes", 0) > 0
        for v in manifest["archives"].values()
    ):
        raise ValueError("upstream complete archive SHA256 identity missing")
    # Never accept provenance from a different study/power; the native
    # restart helper additionally verifies every archive member SHA256.
    return {"from_stage": previous.number, "to_stage": s.number,
            "from_ns": previous.end_ns, "to_ns": s.end_ns,
            "power_w": power, "upstream_run_id": upstream_run_id,
            "checkpoint_prefix": expected_prefix, "plan_sha256": plan_sha256()}

def add_attestation(manifest: dict, number: int, power: int,
                    upstream_run_id: int | None = None) -> dict:
    s = stage(number)
    if type(power) is not int or power not in (400, 1000):
        raise ValueError("unrecognized power")
    if number == 1 and upstream_run_id is not None:
        raise ValueError("first stage must not have an upstream run")
    if number > 1 and (type(upstream_run_id) is not int or upstream_run_id <= 0):
        raise ValueError("continued stage must have exact upstream run")
    if (manifest.get("source_sha") != SCIENCE_SOURCE_SHA or
            manifest.get("power_w") != power or manifest.get("chemistry") != CHEMISTRY or
            manifest.get("scientific_acceptance") != "HOLD" or
            (Decimal(str(manifest.get("final_time_s"))) - s.end_ns * NS_S).copy_abs() >= Decimal("1e-15") or
            not isinstance(manifest.get("actual_moose_step"), int) or
            manifest.get("actual_moose_step") < 1):
        raise ValueError("do not promote unfinished or incorrect native checkpoint")
    result = dict(manifest)
    result["five_stage_chain"] = {
        "plan_sha256": plan_sha256(), "stage": number, "power_w": power,
        "start_ns": s.start_ns, "end_ns": s.end_ns,
        "interval_ns": s.requested_spacing_ns,
        "requested_step_count": s.requested_steps,
        "upstream_run_id": upstream_run_id,
        "initialization": number == 1,
        "checkpoint_handoff": "independent-ci-native-state-only",
        "target_grid_vs_actual_native_steps": "distinct; native P3/P4 verification required",
    }
    return result

def self_test() -> None:
    assert len(grid_ns()) == 501 and all(
        a < b for a, b in zip(grid_ns(), grid_ns()[1:])
    )
    assert [s.requested_steps for s in STAGES] == [100,190,80,90,40]
    assert [s.end_ns for s in STAGES] == [100,2000,10000,100000,500000]
    assert sum(s.requested_steps for s in STAGES) == 500
    assert upstream_artifact_name(2,400) == \
        "oxygen25-ei936-100ns-initial-checkpoint-complete-400W"
    assert upstream_artifact_name(5,1000) == \
        "oxygen25-ei936-100000ns-restart-complete-1000W"
    for i in range(2,6):
        prev = stage(i-1)
        native = dict(source_sha=SCIENCE_SOURCE_SHA, power_w=400,
                      chemistry=CHEMISTRY, final_time_s=float(prev.end_ns*NS_S),
                      actual_moose_step=17, scientific_acceptance="HOLD",
                      recovery_requirements={"native_recover_prefix":"x/0017"},
                      archives={"run":{"sha256":"a"*64,"bytes":3},
                                "inputs":{"sha256":"b"*64,"bytes":4}})
        attested = add_attestation(native,i-1,400,upstream_run_id=None if i==2 else 123)
        assert verify_previous_manifest(attested,i,400,123)["to_stage"] == i
        for mutation in (dict(attested, power_w=1000),
                         dict(attested, five_stage_chain=dict(
                             attested["five_stage_chain"], stage=5)),
                         dict(attested, final_time_s=0)):
            try:
                verify_previous_manifest(mutation,i,400,123)
            except ValueError:
                pass
            else:
                raise AssertionError("cross-stage identity mutation accepted")
    print("OXYGEN25_FIVE_STAGE_500US_PLAN_SELFTEST_PASS")

def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-test", action="store_true")
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--stage", type=int)
    mode.add_argument("--check-upstream", type=Path)
    mode.add_argument("--attest", type=Path)
    p.add_argument("--stage-number", type=int)
    p.add_argument("--power-w", type=int)
    p.add_argument("--upstream-run-id", type=int)
    a=p.parse_args()
    if a.self_test:
        self_test()
    elif a.plan:
        print(json.dumps(plan(), indent=2, sort_keys=True))
    elif a.stage is not None:
        print(json.dumps(stage(a.stage).to_record(),sort_keys=True))
    elif a.check_upstream:
        if a.stage_number is None or a.power_w is None or a.upstream_run_id is None:
            p.error("--stage-number --power-w --upstream-run-id required")
        verify_previous_manifest(json.loads(a.check_upstream.read_text()),
                                 a.stage_number,a.power_w,a.upstream_run_id)
        print("OXYGEN25_UPSTREAM_FIVE_STAGE_PROVENANCE_PASS")
    elif a.attest:
        if a.stage_number is None or a.power_w is None:
            p.error("--stage-number and --power-w required")
        data = json.loads(a.attest.read_text())
        verified = add_attestation(data,a.stage_number,a.power_w,a.upstream_run_id)
        a.attest.write_text(json.dumps(verified,indent=2,sort_keys=True)+"\n")
        print("OXYGEN25_NATIVE_STAGE_ATTESTATION_PASS",a.stage_number,a.power_w)

if __name__ == "__main__":
    main()
