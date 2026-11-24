#!/usr/bin/env python3
"""G7 bounded actual S6 fixed-state Jv versus independent central residual FD.

Use exact G8 validated public staging and frozen PhysicsApp ELF. Probe only
the new Poisson arm, once per case, after a converged assembled Newton solve.
The full row vector is compared along three deterministic directions; this
is NOT exhaustive entrywise Jacobian certification or a science waiver.
"""
from __future__ import annotations
import argparse
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from issue652_g8_matched_native_pilot import (
    g6, SOURCE_SHA, CASES, CHEM_RELATIVE, C0, TABLE_RELATIVE, PUBLIC_D_100_SHA256,
    file_sha, verify_bundle, protected_files_for_case, repair_private_permissions,
    secure_tmpfs_cleanup,
)

LIMIT = 1e-8
STEPS = (1e-4, 5e-5, 2.5e-5)
MIN_S6_DOF = 5000
TIMEOUT = 900
FLOAT = r"[-+0-9.eE]+"
JVP = re.compile(rf"^G7_JVP (\d+) ([012]) ({FLOAT}) ({FLOAT}) ({FLOAT})$", re.M)
FIXED = re.compile(r"^G7_FIXED_STATE (\d+) (\d+)$", re.M)
RESTORE = re.compile(rf"^G7_RESTORE (\d+) ([01]) ({FLOAT})$", re.M)


def interpret(log, min_dof):
    fixed, directions, restore = FIXED.findall(log), JVP.findall(log), RESTORE.findall(log)
    result = {"status": "HOLD_PROBE_MISSING_OR_INVALID", "directions": [],
              "threshold": LIMIT, "central_steps": list(STEPS)}
    if len(fixed) != 1 or len(directions) != 3 or len(restore) != 1:
        return result
    n, its = map(int, fixed[0])
    if n < min_dof or its < 1 or {int(x[1]) for x in directions} != {0,1,2}:
        return result
    for count,k,*values in directions:
        values = list(map(float, values))
        if int(count)!=n or any(not math.isfinite(x) or x<0 for x in values):
            return result
        result["directions"].append(dict(zip(("relative_error_fine","relative_richardson_difference","relative_error_coarse"),values),direction=int(k)))
    count,same,err = restore[0]
    err=float(err)
    if int(count)!=n or same!="1" or not math.isfinite(err) or not 0<=err<=LIMIT:
        return result
    result.update(ndof=n,newton_iterations=its,restoration_relative_error=err)
    result["status"] = "PASS_FIXED_STATE_DIRECTIONAL" if all(
        max(d["relative_error_fine"],d["relative_error_coarse"],d["relative_richardson_difference"])<=LIMIT
        for d in result["directions"]) else "HOLD_DIRECTIONAL_TOLERANCE"
    return result


def run_native(command, folder, log, name, timeout):
    if command[:3] != ["docker","run","--rm"]:
        raise ValueError("G7_DOCKER_COMMAND")
    command=command[:3]+["--name",name]+command[3:]
    try:
        with log.open("xb") as sink:
            p=subprocess.run(command,cwd=folder,stdout=sink,stderr=subprocess.STDOUT,
                             timeout=timeout,check=False,env={k:v for k,v in os.environ.items()
                             if k not in ("PROTECTED_ARCHIVE_B64","OXYGEN24_RATES_TAR_XZ_B64")})
        return p.returncode
    except subprocess.TimeoutExpired:
        subprocess.run(["docker","rm","-f",name],stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL,timeout=60,check=False)
        return 124


def run(*, staged, stage_receipt, manifest, output, authorize):
    if not authorize or output.exists() or output.is_symlink():
        raise ValueError("G7_EXPLICIT_AUTHORIZATION_OR_OUTPUT")
    result={"schema":"issue652.g7.s6_fixed_state_directional.v1","source_sha":SOURCE_SHA,
            "scope":"ONE_CONVERGED_STATE_THREE_DIRECTIONS_PER_NEW_S6_CASE",
            "whole_matrix_entrywise":"UNVERIFIED","prior_strict_petsc_frobenius":"HOLD_UNCHANGED",
            "science":"SCIENCE_HOLD","P4":"NOT_RUN","P3_100us":"NOT_RUN","cases":{},
            "raw_private_inputs_logs_or_vectors_uploaded":False,"status":"HOLD"}
    private=None
    tables={}
    try:
        if g6.exact_source()!=SOURCE_SHA:
            raise ValueError("G7_SOURCE")
        stage=json.loads(stage_receipt.read_text())
        bundle=verify_bundle(manifest,SOURCE_SHA)
        if stage.get("same_input_stage")!="PASS" or stage.get("physics_app_source_sha")!=SOURCE_SHA or set(stage.get("cases",{}))!=set(CASES):
            raise ValueError("G7_STAGE")
        binary=g6.ROOT/"physics_app/physics-opt"
        observer=g6.ROOT/"physics_app/g7_jvp_probe.so"
        if file_sha(binary)!=bundle["files"]["physics_app/physics-opt"] or not observer.is_file():
            raise ValueError("G7_BINARY")
        result.update(binary_sha256=file_sha(binary),observer_sha256=file_sha(observer),manifest_sha256=file_sha(manifest))
        from issue671_secure_ei_rate_scratch import EXPECTED, read_hashed_rows
        try:
            _,tables=read_hashed_rows()
            if set(tables)!=set(EXPECTED):
                raise ValueError("G7_PROTECTED_SET")
        finally:
            os.environ.pop("PROTECTED_ARCHIVE_B64",None)
            os.environ.pop("OXYGEN24_RATES_TAR_XZ_B64",None)
        private=Path(tempfile.mkdtemp(prefix="issue652-g5-g8-g7-",dir="/dev/shm"))
        os.chmod(private,0o700)
        g5=json.loads((staged.parent/"g5-result/g5_stage_receipt.json").read_text())
        if g5.get("source_sha")!=SOURCE_SHA or set(g5.get("cases",{}))!=set(CASES):
            raise ValueError("G7_G5_STAGE")
        for case in CASES:
            record=result["cases"][case]={"status":"HOLD"}
            try:
                public=staged/"scratch"/case
                if any(p.is_symlink() for p in public.rglob("*")):
                    raise ValueError("G7_STAGE_SYMLINK")
                work=private/case
                shutil.copytree(public,work)
                chem=work/CHEM_RELATIVE
                if file_sha(work/TABLE_RELATIVE)!=PUBLIC_D_100_SHA256 or file_sha(chem/C0)!=stage["cases"][case]["new_g5_c0_sha256"]:
                    raise ValueError("G7_CASE_IDENTITY")
                ordered=g5["cases"][case]["ordered"]
                if len(ordered)!=11 or len(set(ordered))!=11 or Path(ordered[0]).name!=C0:
                    raise ValueError("G7_LAYER_ORDER")
                record["protected_tables"]=protected_files_for_case(work,case,tables)
                short,patch=g6.three_ns_input((chem/C0).read_bytes())
                (chem/C0).write_bytes(short)
                record["input_patch"]=patch
                command=g6.docker_cmd(work,ordered,observe=False)
                command[-1]+=" --check-input"
                p2=private/(case+"-p2.log")
                rc=run_native(command,work,p2,"g7-p2-"+case,360)
                repair_private_permissions(private)
                record["P2_rc"]=rc
                record["P2_syntax_ok"]=rc==0 and b"Syntax OK" in p2.read_bytes()
                if not record["P2_syntax_ok"]:
                    continue
                out=work/"g7_outputs"
                out.mkdir(mode=0o700)
                command=g6.docker_cmd(work,ordered+["Outputs/file_base=g7_outputs/plasma"],observe=False)
                token="/workspace/physics_app/physics-opt"
                if command[-1].count(token)!=1:
                    raise ValueError("G7_PRELOAD_ANCHOR")
                command[-1]=command[-1].replace(token,"G7_JVP_MIN_DOF=5000 LD_PRELOAD=/workspace/physics_app/g7_jvp_probe.so "+token)
                log=private/(case+"-p3.log")
                rc=run_native(command,work,log,"g7-p3-"+case,TIMEOUT)
                repair_private_permissions(private)
                record["P3_rc"]=rc
                record["probe"]=interpret(log.read_text(errors="replace"),MIN_S6_DOF)
                if rc==0:
                    metrics=g6.metrics_for_p3(work)
                    record["P3_time_rows"]=metrics["time_rows"]
                    record["P3_final_seconds"]=metrics["final_seconds"]
                    if record["probe"]["status"]=="PASS_FIXED_STATE_DIRECTIONAL":
                        record["status"]="PASS_BOUNDED_S6_DIRECTIONAL"
            except Exception as exc:
                record["blocker_class"]=type(exc).__name__
            print("G7_CASE",case,record["status"],flush=True)
        if set(result["cases"])==set(CASES) and all(c["status"]=="PASS_BOUNDED_S6_DIRECTIONAL" for c in result["cases"].values()):
            result["status"]="PASS_BOUNDED_S6_DIRECTIONAL_BOTH"
    except Exception as exc:
        result["blocker_class"]=type(exc).__name__
    finally:
        tables.clear()
        os.environ.pop("PROTECTED_ARCHIVE_B64",None)
        os.environ.pop("OXYGEN24_RATES_TAR_XZ_B64",None)
        if private is not None:
            secure_tmpfs_cleanup(private)
        output.write_text(json.dumps(result,sort_keys=True,indent=2,allow_nan=False)+"\n")
    print("G7_S6_DIRECTIONAL",result["status"],"SCIENCE_HOLD",flush=True)
    return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--staged",type=Path,required=True)
    p.add_argument("--stage-receipt",type=Path,required=True)
    p.add_argument("--manifest",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--authorize-protected-native",action="store_true")
    a=p.parse_args()
    result=run(staged=a.staged,stage_receipt=a.stage_receipt,manifest=a.manifest,output=a.output,authorize=a.authorize_protected_native)
    return 0 if result["status"]=="PASS_BOUNDED_S6_DIRECTIONAL_BOTH" else 3


if __name__=="__main__":
    raise SystemExit(main())
