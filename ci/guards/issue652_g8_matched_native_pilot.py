#!/usr/bin/env python3
"""G8 protected S6 417/941 original PublicD100: old-native vs new-generated Poisson.

Identical exact-head PhysicsApp ELF and all physical inputs except the 15
Poisson/charge owner handoff; preflight G8 source provenance must PASS.
Run P2 then bounded 3ns pilot in independent private /dev/shm scratch trees.
Compare nodal potential and independently reconstructed n_e/rho on identical
plasma meshes at common Exodus time frames. NO full100, P4 or science acceptance.
Protected rates, source decks, private logs and raw Exodus never uploaded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

# Execute the G8 analysis script from a separate checkout, but import all
# existing G5/G6 native modules from the SAME frozen Physics source as the
# reused ELF. Python normally prepends this script's directory otherwise.
_NativeSource = os.environ.get("G8_NATIVE_SOURCE_ROOT")
if _NativeSource:
    _NativeGuards = Path(_NativeSource).resolve() / "ci/guards"
    if not _NativeGuards.is_dir() or _NativeGuards.is_symlink():
        raise RuntimeError("EXACT_NATIVE_SOURCE_GUARDS_DIRECTORY_MISSING")
    sys.path.insert(0, str(_NativeGuards))

import issue652_g6_runtime_gate as g6
from issue652_g5_native_p2 import (
    OCI, file_sha, secure_tmpfs_cleanup,
)
from issue652_g8_matched_stage import (
    SOURCE_SHA, PUBLIC_D_100_SHA256, CASES, C0,
    CHEM_RELATIVE, TABLE_RELATIVE, MatchedHold,
)
from issue652_g6b_parallel_evidence import verify_bundle

MAX_SECONDS_PER_ARM = 900
NA = 6.02214076e23
ELEMENTARY_CHARGE = 1.602176634e-19
REQUIRED_LOGS = ("log_e", "log_O2p", "log_Op", "log_Om")
METRICS = ("potential", "electron_density", "charge_density")
# Diagnostic pilot thresholds fixed before comparison; not a P4 tolerance.
REL_RMS_LIMIT = {"potential": 1e-3, "electron_density": 1e-3,
                 "charge_density": 1e-2}


def bytes_sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b""):
            h.update(chunk)
    return h.hexdigest()


def execute_privately(command: list[str], cwd: Path, log: Path, seconds: int) -> tuple[int, str]:
    if log.exists() or log.is_symlink():
        raise MatchedHold("REFUSE_NATIVE_LOG_REUSE")
    if not 1 <= seconds <= MAX_SECONDS_PER_ARM:
        raise MatchedHold("NATIVE_TIMEOUT_OUT_OF_BOUNDS")
    with log.open("xb") as sink:
        try:
            p = subprocess.run(
                command, cwd=cwd, stdout=sink, stderr=subprocess.STDOUT,
                timeout=seconds, check=False,
                env={k: v for k, v in os.environ.items()
                     if k not in ("PROTECTED_ARCHIVE_B64",
                                  "OXYGEN24_RATES_TAR_XZ_B64")},
            )
            code = p.returncode
        except subprocess.TimeoutExpired:
            code = 124
    return code, bytes_sha(log)


def repair_private_permissions(private: Path) -> None:
    if (not private.is_relative_to(Path("/dev/shm"))
            or not private.name.startswith("issue652-g5-g8-")
            or private.is_symlink()):
        raise MatchedHold("PRIVATE_CHOWN_SCOPE_DENIED")
    subprocess.run(
        ["sudo", "chown", "-Rh", f"{os.getuid()}:{os.getgid()}", "--", str(private)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        check=True, timeout=90,
    )


def protected_files_for_case(root: Path, case: str, tables: dict) -> dict:
    from issue671_secure_ei_rate_scratch import EXPECTED, REQUIRED, validate_rows
    names = REQUIRED[case]
    target = root / CHEM_RELATIVE / "private_rates"
    if target.exists() or target.is_symlink():
        raise MatchedHold("PRIVATE_RATES_DEST_PRESENT")
    target.mkdir(mode=0o700)
    hashes = {}
    for name in sorted(names):
        blob = tables[name]
        if (hashlib.sha256(blob).hexdigest() != EXPECTED[name]
                or validate_rows(blob) != 100):
            raise MatchedHold("PROTECTED_EI_HASH_OR_SHAPE_DRIFT")
        file = target / name
        fd = os.open(file, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                     getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "wb") as sink:
            sink.write(blob)
        hashes[name] = file_sha(file)
        if hashes[name] != EXPECTED[name]:
            raise MatchedHold("PROTECTED_EI_STAGE_DIGEST_DRIFT")
    return {
        "required_table_count": len(names),
        "table_set_status": "EXACT_PROTECTED_DIGESTS_PASS",
        "protected_archive_upload": False,
    }


def exodus_read(path: Path) -> dict:
    import numpy as np
    from netCDF4 import Dataset

    if path.is_symlink() or not path.is_file() or path.stat().st_size < 4096:
        raise MatchedHold("P3_EXODUS_NOT_FOUND")
    def strs(matrix):
        a = np.asarray(matrix)
        return [row.astype("S1").tobytes().decode("ascii", "ignore").strip("\0 ")
                for row in a]
    with Dataset(path, "r") as ds:
        times = np.asarray(ds.variables["time_whole"][:], dtype=float)
        x = np.asarray(ds.variables["coordx"][:], dtype=float)
        y = np.asarray(ds.variables["coordy"][:], dtype=float)
        if (not np.all(np.isfinite(times)) or
                not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)) or
                len(times) < 3 or abs(float(times[-1])-3e-9) > 1e-12):
            raise MatchedHold("P3_EXODUS_TIME_OR_COORDS_INVALID")
        if not np.all(np.diff(times) > 0):
            raise MatchedHold("P3_EXODUS_NONMONOTONIC_TIME")
        names = strs(ds.variables["name_nod_var"][:])
        required = ("potential",) + REQUIRED_LOGS
        if any(names.count(key) != 1 for key in required):
            raise MatchedHold("P3_REQUIRED_NODAL_FIELD_MISSING")
        var = {}
        for key in required:
            data = np.asarray(ds.variables["vals_nod_var"+str(names.index(key)+1)][:],
                              dtype=float)
            if data.shape != (len(times), len(x)) or not np.all(np.isfinite(data)):
                raise MatchedHold("P3_NODAL_SHAPE_OR_NONFINITE")
            var[key] = data
        blocks = strs(ds.variables["eb_names"][:])
        if blocks.count("plasma") != 1:
            raise MatchedHold("P3_PLASMA_BLOCK_NOT_EXACTLY_ONCE")
        conn = np.asarray(ds.variables["connect"+str(blocks.index("plasma")+1)][:],
                          dtype=int)-1
        nodes = np.unique(conn)
        if not len(nodes) or nodes.min() < 0 or nodes.max() >= len(x):
            raise MatchedHold("P3_PLASMA_CONNECTIVITY_INVALID")
        other = {}
        for sigma in ("sigma_s", "sigma_wafer", "sigma_focus_ring"):
            if sigma in names:
                other[sigma] = np.asarray(
                    ds.variables["vals_nod_var"+str(names.index(sigma)+1)][:],
                    dtype=float)
    logs = {k: var[k][:, nodes] for k in REQUIRED_LOGS}
    with np.errstate(over="ignore", under="ignore", invalid="ignore"):
        species = {key: NA*np.exp(value) for key, value in logs.items()}
    if any(not np.isfinite(array).all() or (array < 0).any()
           for array in species.values()):
        raise MatchedHold("P3_RECONSTRUCTED_DENSITY_INVALID")
    charge = ELEMENTARY_CHARGE*(species["log_O2p"]+species["log_Op"]
                               -species["log_e"]-species["log_Om"])
    return {"time": times, "x": x, "y": y, "conn": conn, "nodes": nodes,
            "potential": var["potential"][:, nodes],
            "electron_density": species["log_e"],
            "charge_density": charge, "sigma": other,
            "filename_sha256": bytes_sha(path), "filename_size": path.stat().st_size}


def normalized_rms(old, new) -> dict:
    import numpy as np
    a, b = np.asarray(old, dtype=float), np.asarray(new, dtype=float)
    if a.shape != b.shape or not a.size or not np.isfinite(a).all() or not np.isfinite(b).all():
        raise MatchedHold("FIELD_ARRAY_MISMATCH_OR_NONFINITE")
    scale = max(float(np.max(np.abs(a))), float(np.max(np.abs(b))), 1e-30)
    diff = b-a
    return {
        "max_absolute": float(np.max(np.abs(diff))),
        "rms_absolute": float(np.sqrt(np.mean(diff*diff))),
        "normalization": scale,
        "relative_rms": float(np.sqrt(np.mean(diff*diff))/scale),
        "relative_max": float(np.max(np.abs(diff))/scale),
    }


def compare_exodus(old: Path, new: Path) -> dict:
    import numpy as np
    a, b = exodus_read(old), exodus_read(new)
    for key in ("time", "x", "y"):
        if a[key].shape != b[key].shape or not np.allclose(
                a[key], b[key], atol=1e-13 if key != "time" else 1e-15,
                rtol=0.0):
            raise MatchedHold("OLD_NEW_MESH_OR_TIME_NOT_IDENTICAL:" + key)
    if (not np.array_equal(a["conn"], b["conn"])
            or not np.array_equal(a["nodes"], b["nodes"])):
        raise MatchedHold("OLD_NEW_PLASMA_CONNECTIVITY_NOT_IDENTICAL")
    variables = {}
    for key in METRICS:
        values = normalized_rms(a[key], b[key])
        values["pilot_threshold"] = REL_RMS_LIMIT[key]
        values["pilot_comparison"] = (
            "WITHIN_PREDECLARED_PILOT_THRESHOLD" if
            values["relative_rms"] <= REL_RMS_LIMIT[key] else
            "ABOVE_PREDECLARED_PILOT_THRESHOLD")
        variables[key] = values
    sigma = {}
    for name in ("sigma_s", "sigma_wafer", "sigma_focus_ring"):
        if name in a["sigma"] and name in b["sigma"]:
            sigma[name] = normalized_rms(a["sigma"][name], b["sigma"][name])
        else:
            sigma[name] = {"status": "NOT_BOTH_RECORDED_AS_NODAL_EXODUS"}
    return {
        "time_points": len(a["time"]),
        "t_last_s": float(a["time"][-1]),
        "matched_nodes": len(a["nodes"]),
        "matched_exodus_coordinates_and_plasma_connectivity": True,
        "fields": variables, "surface_charges": sigma,
        "same_time_and_mesh": "PASS",
        "fieldwise_3ns_pilot": (
            "PASS_PROVISIONAL_3NS" if all(
                v["pilot_comparison"] == "WITHIN_PREDECLARED_PILOT_THRESHOLD"
                for v in variables.values()) else "HOLD_NUMERICAL_DIFFERENCE"
        ),
        "fieldwise_100us": "NOT_RUN", "science": "SCIENCE_HOLD",
    }


def run(*, before_g5: Path, after_g5: Path, stage_receipt: Path,
        build_manifest: Path, output: Path, cases: tuple[str, ...],
        authorize: bool) -> dict:
    if not authorize:
        raise MatchedHold("EXPLICIT_PROTECTED_NATIVE_AUTHORIZATION_REQUIRED")
    if output.exists() or output.is_symlink():
        raise MatchedHold("NATIVE_OUTPUT_OVERWRITE")
    if not cases or any(case not in CASES for case in cases):
        raise MatchedHold("CASE_SELECTION_INVALID")
    if g6.exact_source() != SOURCE_SHA:
        raise MatchedHold("SOURCE_OR_GITHUB_SHA_CHANGED")
    stage = json.loads(stage_receipt.read_text())
    bundle = verify_bundle(build_manifest, SOURCE_SHA)
    if (stage.get("schema") != "issue652.g8.old_new_same_input_stage.v1"
            or stage.get("same_input_stage") != "PASS"
            or stage.get("physics_app_source_sha") != SOURCE_SHA
            or set(stage.get("cases", {})) != set(CASES)):
        raise MatchedHold("G8_MATCHED_P0_STAGE_REQUIRED")
    binary = g6.ROOT/"physics_app/physics-opt"
    if file_sha(binary) != bundle["files"]["physics_app/physics-opt"]:
        raise MatchedHold("EXACT_P1_SHARED_BINARY_DIGEST_DRIFT")
    from issue671_secure_ei_rate_scratch import EXPECTED, read_hashed_rows
    _, tables = read_hashed_rows()
    os.environ.pop("OXYGEN24_RATES_TAR_XZ_B64", None)
    os.environ.pop("PROTECTED_ARCHIVE_B64", None)
    if set(tables) != set(EXPECTED):
        raise MatchedHold("PROTECTED_ARCHIVE_INCOMPLETE")
    result = {
        "schema": "issue652.g8.old_new_matched_native_3ns.v1",
        "source_sha": SOURCE_SHA,
        "binary_sha256": bundle["files"]["physics_app/physics-opt"],
        "manifest_sha256": file_sha(build_manifest),
        "same_single_P1_binary_old_and_new": True,
        "original_public_d100_sha256": PUBLIC_D_100_SHA256,
        "private_input_artifact": False,
        "private_log_artifact": False,
        "raw_exodus_artifact": False,
        "cases": {},
        "P3_3ns": "HOLD", "P3_100us": "NOT_RUN",
        "P4": "NOT_RUN", "science": "SCIENCE_HOLD",
    }
    private = Path(tempfile.mkdtemp(prefix="issue652-g5-g8-",dir="/dev/shm"))
    os.chmod(private,0o700)
    try:
        for case in cases:
            record = stage["cases"][case]
            oldbase = before_g5/"scratch"/case
            newbase = after_g5/"scratch"/case
            copies = {}
            checked_tables = {}
            for mode, src in (("old", oldbase), ("new", newbase)):
                dest = private/(case+"-"+mode)
                for file in src.rglob("*"):
                    if file.is_symlink():
                        raise MatchedHold("PUBLIC_SCRATCH_SYMLINK")
                shutil.copytree(src, dest)
                chem = dest/CHEM_RELATIVE
                if file_sha(dest/TABLE_RELATIVE) != PUBLIC_D_100_SHA256:
                    raise MatchedHold("PUBLIC_D100_DRIFT_BEFORE_NATIVE")
                old_c0 = (chem/C0).read_bytes()
                expected = (record["old_p4_c0_sha256"] if mode == "old"
                            else record["new_g5_c0_sha256"])
                if hashlib.sha256(old_c0).hexdigest() != expected:
                    raise MatchedHold("SOURCE_OWNER_C0_CHANGED")
                new_c0, _ = g6.three_ns_input(old_c0)
                (chem/C0).write_bytes(new_c0)
                checked_tables[mode] = protected_files_for_case(dest, case, tables)
                out = dest/"g8_outputs"
                out.mkdir(mode=0o700)
                copies[mode] = dest
            g5_record = json.loads(
                (after_g5.parent/"g5-result/g5_stage_receipt.json").read_text())
            if (g5_record.get("source_sha") != SOURCE_SHA
                    or set(g5_record.get("cases", {})) != set(CASES)):
                raise MatchedHold("G5_INPUT_ORDER_RECEIPT_IDENTITY_DRIFT")
            ordered = g5_record["cases"][case]["ordered"]
            if (len(ordered) != 11 or [Path(x).name for x in ordered][0] != C0
                    or len({Path(x).name for x in ordered}) != 11):
                raise MatchedHold("G5_ELEVEN_LAYER_RUNTIME_ORDER_INVALID")
            codes = {}
            for mode in ("old", "new"):
                command = g6.docker_cmd(copies[mode], ordered, observe=False)
                command[-1] += " --check-input"
                log = private/(case+"-"+mode+"-p2.log")
                code, digest = execute_privately(command, copies[mode], log, 360)
                repair_private_permissions(private)
                codes[mode] = code
                if code != 0 or b"Syntax OK" not in log.read_bytes():
                    raise MatchedHold("NATIVE_P2_FAIL_"+mode.upper()+":"+case)
            run_records = {}
            for mode in ("old", "new"):
                command = g6.docker_cmd(
                    copies[mode], ordered + ["Outputs/file_base=g8_outputs/plasma"],
                    observe=False)
                code,digest=execute_privately(
                    command, copies[mode], private/(case+"-"+mode+"-p3.log"),
                    MAX_SECONDS_PER_ARM)
                repair_private_permissions(private)
                if code:
                    raise MatchedHold("NATIVE_P3_FAIL_"+mode.upper()+":"+case)
                exodus = copies[mode]/"g8_outputs/plasma.e"
                if not exodus.is_file():
                    raise MatchedHold("G8_NO_NATIVE_P3_EXODUS_"+mode.upper())
                run_records[mode]={"P2_rc":codes[mode],"P3_rc":code,
                                   "exodus_sha256":file_sha(exodus),
                                   "exodus_bytes":exodus.stat().st_size}
            comparison=compare_exodus(
                copies["old"]/"g8_outputs/plasma.e",
                copies["new"]/"g8_outputs/plasma.e")
            result["cases"][case] = {
                "old":run_records["old"],"new":run_records["new"],
                "comparison":comparison,"protected_EI_inputs":
                    checked_tables["old"],
                "same_case_protected_table_set":checked_tables["old"]==checked_tables["new"],
                "science":"SCIENCE_HOLD",
            }
        result["P3_3ns"]=(
            "PASS_PROVISIONAL_3NS_BOTH" if set(result["cases"])==set(CASES)
            and all(v["comparison"]["fieldwise_3ns_pilot"]=="PASS_PROVISIONAL_3NS"
                    for v in result["cases"].values()) else
            "HOLD_PILOT_NOT_FULLY_PROVEN"
        )
    except Exception as exc:
        result["P3_3ns"]="HOLD"
        result["blocker_class"]=type(exc).__name__
        result["blocker_code"]=str(exc)[:100] if isinstance(exc, MatchedHold) else "NATIVE_RUNTIME_FAILURE"
    finally:
        tables.clear()
        os.environ.pop("PROTECTED_ARCHIVE_B64",None)
        os.environ.pop("OXYGEN24_RATES_TAR_XZ_B64",None)
        secure_tmpfs_cleanup(private)
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+"\n")
    print("G8_PAIRED_NATIVE_3NS",result["P3_3ns"],"SCIENCE_HOLD",flush=True)
    return result


def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument("--before-g5",type=Path,required=True)
    p.add_argument("--after-g5",type=Path,required=True)
    p.add_argument("--stage-receipt",type=Path,required=True)
    p.add_argument("--build-manifest",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--case",choices=CASES,action="append",required=True)
    p.add_argument("--authorize-protected-native",action="store_true")
    a=p.parse_args()
    try:
        result=run(before_g5=a.before_g5,after_g5=a.after_g5,
                   stage_receipt=a.stage_receipt,build_manifest=a.build_manifest,
                   output=a.output,cases=tuple(a.case),
                   authorize=a.authorize_protected_native)
    except (OSError,KeyError,TypeError,ValueError,subprocess.SubprocessError) as exc:
        # Explicit fail-closed source/contract codes only; never raw native
        # error strings (which could include protected input names/paths).
        sanitized = str(exc)
        code = sanitized if __import__("re").fullmatch(r"[A-Z0-9_]+",sanitized) else "REDACTED"
        print("G8_NATIVE_GATE_HOLD",type(exc).__name__,code,flush=True)
        return 2
    return 0 if result["P3_3ns"].startswith("PASS_PROVISIONAL") else 3


if __name__=="__main__":
    raise SystemExit(main())
