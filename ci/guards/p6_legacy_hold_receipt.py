#!/usr/bin/env python3
"""Evidence-only P6 legacy Public D and ARCH KEEP_HOLD verification; never Native P2 approval."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

P05 = "P05 FV Native/Physics duplicate or unexpected owner on 'log_O2p': ni_time"
D_ERRORS = ("transport_coef", "FV species kernels require [Physics]/[Plasmas]/[Transport]/[Chemistry]",
            "P05 FV Native/Physics duplicate or unexpected owner")

def need(condition: bool, key: str) -> None:
    if not condition:
        raise ValueError("P6_LEGACY_" + key)

def sha(path: Path) -> str:
    need(path.is_file() and not path.is_symlink(), "LOG_NOT_REGULAR")
    return hashlib.sha256(path.read_bytes()).hexdigest()

def verify_public(root: Path, head: str) -> dict:
    d=json.loads((root/"issue402_option_s6_p2_status.json").read_text())
    need(d.get("P0")=="PASS" and d.get("P1")=="PASS_SOURCE_BOUND_BINARY", "PUBLIC_P0_P1")
    need(d.get("P2")=="HOLD" and d.get("status")=="HOLD" and d.get("cleanup")=="PASS", "PUBLIC_HOLD")
    need(d.get("P3")==d.get("P4")=="NOT_RUN" and d.get("science")=="SCIENCE_HOLD","PUBLIC_SCIENCE")
    identity=d.get("identity",{})
    need(identity.get("source_sha")==head and identity.get("binary_sha256"),"PUBLIC_SOURCE")
    cases={}
    for case in ("417","941"):
        pair=d.get("checks",{}).get(case,{})
        b,dcase=pair.get("B",{}),pair.get("D",{})
        need(b.get("P2")=="PASS" and b.get("exit_code")==0 and
             b.get("classification")=="NATIVE_CHECK_INPUT_PASS" and b.get("layers")==10,
             "B_"+case)
        need(dcase.get("P2")=="HOLD" and dcase.get("exit_code") not in (None,0,124,127) and
             dcase.get("classification")=="NATIVE_CHECK_INPUT_REJECTED" and dcase.get("layers")==11,
             "D_"+case)
        for variant,check in (("B",b),("D",dcase)):
            p=root/("S6_"+case+"_"+variant+"_P2.log")
            need(sha(p)==check.get("log_sha256"),"LOG_SHA_"+case+variant)
            body=p.read_text(errors="replace")
            if variant=="B":
                need("Syntax OK" in body,"B_SYNTAX_"+case)
            else:
                need("*** ERROR ***" in body and any(e in body for e in D_ERRORS),
                     "D_UNEXPECTED_ERROR_"+case)
        cases[case]={"B":"PASS_HISTORICAL_CONTROL_ONLY","D":"KEEP_HOLD_NATIVE_REJECTION",
                     "B_log_sha256":b["log_sha256"],"D_log_sha256":dcase["log_sha256"]}
    return {"verdict":"PUBLIC_B_PASS_D_KEEP_HOLD","source_head":head,
            "binary_sha256":identity["binary_sha256"],"cases":cases,
            "D_positive_native":False,"P3":"NOT_RUN","P4":"NOT_RUN","science":"SCIENCE_HOLD"}

def verify_arch(root: Path, head: str) -> dict:
    cases={}
    for case in ("417","941"):
        p=root/("S6-"+case)
        d=json.loads((p/"status.json").read_text())
        need(d.get("source_sha")==head and d.get("case")==case,"ARCH_SOURCE_"+case)
        need(d.get("P0")=="PASS" and d.get("P1")=="PASS_SOURCE_BOUND_BINARY","ARCH_P0_P1_"+case)
        need(d.get("P2")=="HOLD" and d.get("status")=="HOLD","ARCH_HOLD_"+case)
        need(d.get("P3")==d.get("P4")=="NOT_RUN" and d.get("science")=="SCIENCE_HOLD",
             "ARCH_SCIENCE_"+case)
        native=d.get("native_check",{})
        need(native.get("P2")=="HOLD" and native.get("exit_code") not in (None,0,124,127)
             and native.get("classification")=="NATIVE_CHECK_INPUT_REJECTED",
             "ARCH_NOT_NATIVE_"+case)
        log=p/"native_P2.log"
        need(sha(log)==native.get("log_sha256"),"ARCH_LOG_SHA_"+case)
        need(P05 in log.read_text(errors="replace"),"ARCH_P05_CAUSE_"+case)
        need(bool(d.get("binary_sha256")),"ARCH_BINARY_"+case)
        cases[case]={"P05":"PASS_EXPECTED_REJECTION","native_positive":False,
                     "binary_sha256":d["binary_sha256"],"log_sha256":native["log_sha256"]}
    return {"verdict":"ARCH_HYBRID_EXPECTED_P05_BOTH_CASES_KEEP_HOLD",
            "source_head":head,"cases":cases,"historical_hybrid":"KEEP_HOLD",
            "native_positive":False,"P3":"NOT_RUN","P4":"NOT_RUN","science":"SCIENCE_HOLD"}

def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--mode",choices=("public","arch"),required=True)
    ap.add_argument("--root",type=Path,required=True)
    ap.add_argument("--expected-head",required=True)
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    try:
        result=(verify_public if args.mode=="public" else verify_arch)(
            args.root.resolve(),args.expected_head)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
        print("P6_LEGACY_HOLD_EVIDENCE_PASS",result["verdict"])
        return 0
    except (OSError,ValueError,TypeError,KeyError,json.JSONDecodeError) as exc:
        print("P6_LEGACY_FAIL_CLOSED",type(exc).__name__,str(exc)[:250])
        return 1

if __name__=="__main__":
    raise SystemExit(main())
