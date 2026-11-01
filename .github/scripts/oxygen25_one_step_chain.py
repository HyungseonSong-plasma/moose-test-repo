#!/usr/bin/env python3
"""Five separate native execution jobs, one requested time event per level.

Smoke trajectory:
S1 0→1 ns (1 ns)
S2 1→11 ns (10 ns)
S3 11→111 ns (100 ns)
S4 111→1111 ns (1000 ns)
S5 1111→11111 ns (10000 ns)

These are *five requested intervals*, not necessarily five physical internal
solver steps. The native solver's actual step counts must be captured and
compared. Never fabricate fields/state from CSV.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
from pathlib import Path

SOURCE_SHA = "8e2fe042dbc204b5fda22d346f1ad8d2e32db3ab"
CHEM = "25-effective-O(ex)-EI936"
NS = Decimal("1e-9")

@dataclass(frozen=True)
class Level:
    n: int
    start_ns: int
    end_ns: int
    spacing_ns: int

    @property
    def requested_step_count(self) -> int:
        return (self.end_ns - self.start_ns) // self.spacing_ns

LEVELS = (
    Level(1, 0, 1, 1),
    Level(2, 1, 11, 10),
    Level(3, 11, 111, 100),
    Level(4, 111, 1111, 1000),
    Level(5, 1111, 11111, 10000),
)

def level(n: int) -> Level:
    if type(n) is not int or n not in range(1, 6):
        raise ValueError("invalid one-step level")
    return LEVELS[n-1]

def definition() -> dict:
    result = {
        "schema": 1, "source_sha": SOURCE_SHA, "chemistry": CHEM,
        "test_only": True, "independent_native_jobs": 5,
        "levels": [dict(n=x.n, start_ns=x.start_ns, end_ns=x.end_ns,
                        spacing_ns=x.spacing_ns, requested_steps=x.requested_step_count)
                   for x in LEVELS],
        "one_requested_interval_each": True, "native_solver_substeps_possible": True,
        "final_end_ns": LEVELS[-1].end_ns,
    }
    return result

def definition_sha() -> str:
    return hashlib.sha256(
        json.dumps(definition(),sort_keys=True,separators=(",",":")).encode()).hexdigest()

def assert_native_manifest(manifest: dict, n: int, power: int) -> None:
    s=level(n)
    if (manifest.get("source_sha") != SOURCE_SHA or
        manifest.get("power_w") != power or power not in (400,1000) or
        manifest.get("chemistry") != CHEM or
        manifest.get("scientific_acceptance") != "HOLD" or
        abs(Decimal(str(manifest.get("final_time_s"))) - Decimal(s.end_ns)*NS) > Decimal("1e-15") or
        type(manifest.get("actual_moose_step")) is not int or
        manifest["actual_moose_step"] <= 0):
        raise ValueError("native stage source/power/final-time/step identity mismatch")
    native=manifest.get("recovery_requirements",{}).get("native_recover_prefix")
    if not isinstance(native,str) or not native.endswith(f"/{manifest['actual_moose_step']:04d}"):
        raise ValueError("unverified native checkpoint path / actual step")
    archives=manifest.get("archives")
    if (not isinstance(archives,dict) or len(archives)!=2 or
        any(not isinstance(v,dict) or
            not isinstance(v.get("sha256"),str) or len(v["sha256"])!=64 or
            v.get("bytes",0)<=0 for v in archives.values())):
        raise ValueError("missing native checkpoint archive integrity")

def attest(manifest: dict, n: int, power: int, upstream: int|None) -> dict:
    assert_native_manifest(manifest,n,power)
    if (n==1 and upstream is not None) or (n>1 and (type(upstream) is not int or upstream<1)):
        raise ValueError("incorrect upstream run identity")
    result=dict(manifest)
    l=level(n)
    result["one_step_smoke"]={
        "definition_sha256":definition_sha(), "level":n,
        "power_w":power,"start_ns":l.start_ns,"end_ns":l.end_ns,
        "requested_interval_ns":l.spacing_ns,"requested_steps":1,
        "upstream_run_id":upstream,
        "one_step_means":"one requested target interval, native solver may substep",
        "native_end_step":manifest["actual_moose_step"],
        "physics_state":"genuine-native-serialized-parent-and-Maxwell",
        "scientific_acceptance":"HOLD",
    }
    return result

def verify_upstream(manifest: dict, n: int, power: int, upstream: int) -> None:
    if n<2 or type(upstream) is not int or upstream<=0:
        raise ValueError("missing exact accepted previous run")
    previous=level(n-1)
    assert_native_manifest(manifest,n-1,power)
    meta=manifest.get("one_step_smoke")
    if (not isinstance(meta,dict) or
        meta.get("definition_sha256")!=definition_sha() or
        meta.get("level")!=n-1 or
        meta.get("start_ns")!=previous.start_ns or
        meta.get("end_ns")!=previous.end_ns or
        meta.get("requested_interval_ns")!=previous.spacing_ns or
        meta.get("power_w")!=power or
        meta.get("requested_steps")!=1 or
        meta.get("native_end_step")!=manifest["actual_moose_step"]):
        raise ValueError("wrong preceding single-step level or continuation state")
    # Archived prior stage physical run, including all MOOSE/Maxwell fields,
    # is independently validated by restart_chain.extract_checked() SHA256.
    return

def self_test() -> None:
    assert len(LEVELS)==5 and sum(l.requested_step_count for l in LEVELS)==5
    assert [l.start_ns for l in LEVELS]==[0,1,11,111,1111]
    assert [l.end_ns for l in LEVELS]==[1,11,111,1111,11111]
    assert [l.spacing_ns for l in LEVELS]==[1,10,100,1000,10000]
    for n in range(2,6):
        prior=level(n-1)
        manifest={
            "source_sha":SOURCE_SHA,"power_w":400,"chemistry":CHEM,
            "scientific_acceptance":"HOLD",
            "final_time_s":str(Decimal(prior.end_ns)*NS),
            "actual_moose_step":n+10,
            "recovery_requirements":{"native_recover_prefix":f"x/{n+10:04d}"},
            "archives":{"run":{"sha256":"a"*64,"bytes":10},
                        "inputs":{"sha256":"b"*64,"bytes":20}},
        }
        x=attest(manifest,n-1,400,None if n==2 else 123)
        verify_upstream(x,n,400,123)
        for corrupt in (dict(x,power_w=1000),
                        dict(x,final_time_s=0),
                        dict(x,one_step_smoke=dict(x["one_step_smoke"],level=5)),
                        dict(x,actual_moose_step=1)):
            try:
                verify_upstream(corrupt,n,400,123)
            except ValueError:
                pass
            else:
                raise AssertionError("wrong native stage accepted")
    print("OXYGEN25_FIVE_SINGLE_EVENT_LEVELS_SELFTEST_PASS")

def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    g=p.add_mutually_exclusive_group(required=True)
    g.add_argument("--self-test",action="store_true")
    g.add_argument("--plan",action="store_true")
    g.add_argument("--level",type=int)
    g.add_argument("--attest",type=Path)
    g.add_argument("--verify-upstream",type=Path)
    p.add_argument("--level-number",type=int)
    p.add_argument("--power-w",type=int)
    p.add_argument("--upstream-run-id",type=int)
    args=p.parse_args()
    if args.self_test:
        self_test()
    elif args.plan:
        print(json.dumps(definition(),indent=2))
    elif args.level:
        print(json.dumps(vars(level(args.level)),sort_keys=True))
    elif args.attest:
        if args.level_number is None or args.power_w is None:
            p.error("attest requires level-number/power-w")
        orig=json.loads(args.attest.read_text())
        obj=attest(orig,args.level_number,args.power_w,args.upstream_run_id)
        args.attest.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")
        print("OXYGEN25_ONE_STEP_NATIVE_CHECKPOINT_ATTESTED",args.level_number,args.power_w)
    elif args.verify_upstream:
        if args.level_number is None or args.power_w is None or args.upstream_run_id is None:
            p.error("verification requires level-number/power-w/upstream-run-id")
        orig=json.loads(args.verify_upstream.read_text())
        verify_upstream(orig,args.level_number,args.power_w,args.upstream_run_id)
        print("OXYGEN25_ONE_STEP_UPSTREAM_NATIVE_STATE_VERIFIED",args.level_number,args.power_w)

if __name__=="__main__":
    main()
