#!/usr/bin/env python3
"""G8 protected S6 417/941 original PublicD100: old-native vs new-generated Poisson.

Identical exact-head PhysicsApp ELF and all physical inputs except the 15
Poisson/charge owner handoff; preflight G8 source provenance must PASS.
Run P2 then bounded 3ns pilot in independent private /dev/shm scratch trees.
Compare nodal potential and independently reconstructed n_e/rho at matching
nodal or elemental support on identical plasma meshes and Exodus time frames. NO full100, P4 or science acceptance.
Protected rates, source decks, private logs and raw Exodus never uploaded.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
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

# Only fixed non-secret phase identifiers may be emitted on failures.
PREFLIGHT_PHASES = frozenset({
    "SOURCE_IDENTITY", "STAGE_RECEIPT", "BUILD_MANIFEST",
    "SHARED_ELF", "PROTECTED_ARCHIVE", "PRIVATE_TMPFS",
})


@contextmanager
def preflight_phase(phase):
    if phase not in PREFLIGHT_PHASES:
        raise MatchedHold("G8_UNKNOWN_PREFLIGHT_PHASE")
    try:
        yield
    except Exception:
        raise MatchedHold("G8_PREFLIGHT_" + phase + "_HOLD") from None
    print("G8_PREFLIGHT_" + phase + "_PASS", flush=True)


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


def exodus_read(path: Path, observation=None) -> dict:
    import numpy as np
    from netCDF4 import Dataset

    if observation is None:
        observation = {}
    if path.is_symlink() or not path.is_file() or path.stat().st_size < 4096:
        raise MatchedHold("P3_EXODUS_NOT_FOUND")

    def strs(matrix):
        a = np.ma.filled(matrix, b"\x00")
        return [row.astype("S1").tobytes().decode("ascii", "ignore").strip("\0 ")
                for row in a]

    def numeric(variable, dtype=float):
        data = np.ma.asarray(variable[:])
        if np.ma.getmaskarray(data).any():
            raise MatchedHold("P3_MASKED_FIELD_OR_MESH")
        result = np.asarray(data, dtype=dtype)
        if not np.isfinite(result).all():
            raise MatchedHold("P3_NODAL_SHAPE_OR_NONFINITE")
        return result

    with Dataset(path, "r") as ds:
        times = numeric(ds.variables["time_whole"])
        x = numeric(ds.variables["coordx"])
        y = numeric(ds.variables["coordy"])
        if (times.ndim != 1 or x.ndim != 1 or y.shape != x.shape
                or len(times) < 3 or abs(float(times[-1])-3e-9) > 1e-12):
            raise MatchedHold("P3_EXODUS_TIME_OR_COORDS_INVALID")
        if not np.all(np.diff(times) > 0):
            raise MatchedHold("P3_EXODUS_NONMONOTONIC_TIME")
        nodal = strs(ds.variables["name_nod_var"][:]) if "name_nod_var" in ds.variables else []
        elemental = strs(ds.variables["name_elem_var"][:]) if "name_elem_var" in ds.variables else []
        required = ("potential",) + REQUIRED_LOGS
        # Emit only fixed public field keys and counts, never the complete name list.
        observation["required_field_counts"] = {
            key: {"nodal": nodal.count(key), "elemental": elemental.count(key)}
            for key in required
        }
        blocks = strs(ds.variables["eb_names"][:])
        if blocks.count("plasma") != 1:
            raise MatchedHold("P3_PLASMA_BLOCK_NOT_EXACTLY_ONCE")
        block = blocks.index("plasma") + 1
        conn = numeric(ds.variables["connect"+str(block)], dtype=int)-1
        nodes = np.unique(conn)
        if conn.ndim != 2 or not len(nodes) or nodes.min() < 0 or nodes.max() >= len(x):
            raise MatchedHold("P3_PLASMA_CONNECTIVITY_INVALID")
        observation["plasma_nodes"] = int(len(nodes))
        observation["plasma_elements"] = int(len(conn))

        if any(nodal.count(key) > 1 or elemental.count(key) > 1 for key in required):
            raise MatchedHold("P3_DUPLICATE_REQUIRED_FIELD")
        if nodal.count("potential") != 1:
            raise MatchedHold("P3_REQUIRED_NODAL_POTENTIAL_MISSING")

        def read_nodal(key):
            data = numeric(ds.variables["vals_nod_var"+str(nodal.index(key)+1)])
            if data.shape != (len(times), len(x)):
                raise MatchedHold("P3_NODAL_SHAPE_OR_NONFINITE")
            return data

        def read_elemental(key):
            index = elemental.index(key)+1
            if "elem_var_tab" in ds.variables:
                truth = numeric(ds.variables["elem_var_tab"], dtype=int)
                if truth.shape != (len(blocks), len(elemental)) or truth[block-1, index-1] != 1:
                    raise MatchedHold("P3_PLASMA_ELEMENT_FIELD_INACTIVE")
            varname = "vals_elem_var"+str(index)+"eb"+str(block)
            if varname not in ds.variables:
                raise MatchedHold("P3_PLASMA_ELEMENT_FIELD_MISSING")
            data = numeric(ds.variables[varname])
            if data.shape != (len(times), len(conn)):
                raise MatchedHold("P3_ELEMENT_FIELD_SHAPE_INVALID")
            return data

        # Prefer actual cell data when all FV log states are available on plasma.
        # A nodal-only representation is retained as a distinct observation class.
        # Never interpolate or mix species centering to reconstruct charge.
        if all(elemental.count(key) == 1 for key in REQUIRED_LOGS):
            centering = "elemental"
            logs = {key: read_elemental(key) for key in REQUIRED_LOGS}
        elif (all(nodal.count(key) == 1 for key in REQUIRED_LOGS)
              and not any(elemental.count(key) for key in REQUIRED_LOGS)):
            centering = "nodal"
            logs = {key: read_nodal(key)[:, nodes] for key in REQUIRED_LOGS}
        else:
            raise MatchedHold("P3_REQUIRED_LOG_FIELDS_MISSING_OR_MIXED_CENTERING")
        observation["density_centering"] = centering
        potential = read_nodal("potential")[:, nodes]
        other = {}
        for sigma in ("sigma_s", "sigma_wafer", "sigma_focus_ring"):
            if nodal.count(sigma) == 1:
                other[sigma] = read_nodal(sigma)
    with np.errstate(over="ignore", under="ignore", invalid="ignore"):
        species = {key: NA*np.exp(value) for key, value in logs.items()}
    if any(not np.isfinite(array).all() or (array < 0).any()
           for array in species.values()):
        raise MatchedHold("P3_RECONSTRUCTED_DENSITY_INVALID")
    charge = ELEMENTARY_CHARGE*(species["log_O2p"]+species["log_Op"]
                               -species["log_e"]-species["log_Om"])
    if not np.isfinite(charge).all():
        raise MatchedHold("P3_RECONSTRUCTED_DENSITY_INVALID")
    return {"time": times, "x": x, "y": y, "conn": conn, "nodes": nodes,
            "density_centering": centering,
            "potential": potential,
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


def compare_exodus(old: Path, new: Path, observation=None) -> dict:
    import numpy as np
    if observation is None:
        observation = {}
    arrays = {}
    for mode, path in (("old", old), ("new", new)):
        observation[mode] = {}
        try:
            arrays[mode] = exodus_read(path, observation[mode])
        except Exception as exc:
            observation[mode]["blocker_code"] = observation_blocker(exc)
    if set(arrays) != {"old", "new"}:
        raise MatchedHold("P3_EXODUS_OBSERVATION_INCOMPLETE")
    a, b = arrays["old"], arrays["new"]
    if a["density_centering"] != b["density_centering"]:
        raise MatchedHold("OLD_NEW_DENSITY_CENTERING_MISMATCH")
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
        "matched_plasma_elements": len(a["conn"]),
        "field_centering": {"potential": "nodal",
                            "electron_density": a["density_centering"],
                            "charge_density": a["density_centering"]},
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


# The receipt is public: only fixed, allowlisted diagnostic codes can leave
# the private scratch. Raw field names, exceptions, logs and Exodus stay private.
OBSERVATION_BLOCKERS = frozenset({
    "P3_EXODUS_NOT_FOUND", "P3_MASKED_FIELD_OR_MESH",
    "P3_NODAL_SHAPE_OR_NONFINITE", "P3_EXODUS_TIME_OR_COORDS_INVALID",
    "P3_EXODUS_NONMONOTONIC_TIME", "P3_PLASMA_BLOCK_NOT_EXACTLY_ONCE",
    "P3_PLASMA_CONNECTIVITY_INVALID", "P3_DUPLICATE_REQUIRED_FIELD",
    "P3_REQUIRED_NODAL_POTENTIAL_MISSING", "P3_PLASMA_ELEMENT_FIELD_INACTIVE",
    "P3_PLASMA_ELEMENT_FIELD_MISSING", "P3_ELEMENT_FIELD_SHAPE_INVALID",
    "P3_REQUIRED_LOG_FIELDS_MISSING_OR_MIXED_CENTERING",
    "P3_RECONSTRUCTED_DENSITY_INVALID", "P3_EXODUS_OBSERVATION_INCOMPLETE",
    "OLD_NEW_DENSITY_CENTERING_MISMATCH",
    "OLD_NEW_PLASMA_CONNECTIVITY_NOT_IDENTICAL",
    "FIELD_ARRAY_MISMATCH_OR_NONFINITE",
    "OLD_NEW_MESH_OR_TIME_NOT_IDENTICAL:time",
    "OLD_NEW_MESH_OR_TIME_NOT_IDENTICAL:x",
    "OLD_NEW_MESH_OR_TIME_NOT_IDENTICAL:y",
})


def observation_blocker(exc):
    code = str(exc)
    return code if isinstance(exc, MatchedHold) and code in OBSERVATION_BLOCKERS else "P3_OBSERVATION_UNCLASSIFIED_HOLD"


def record_comparison(record, old, new):
    observation = record.setdefault("observation", {})
    try:
        record["comparison"] = compare_exodus(old, new, observation)
    except Exception as exc:
        record["comparison"] = {
            "fieldwise_3ns_pilot": "HOLD_OBSERVATION",
            "blocker_code": observation_blocker(exc),
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
    with preflight_phase("SOURCE_IDENTITY"):
        if g6.exact_source() != SOURCE_SHA:
            raise MatchedHold("SOURCE_OR_GITHUB_SHA_CHANGED")
    with preflight_phase("STAGE_RECEIPT"):
        stage = json.loads(stage_receipt.read_text())
        if (stage.get("schema") != "issue652.g8.old_new_same_input_stage.v1"
                or stage.get("same_input_stage") != "PASS"
                or stage.get("physics_app_source_sha") != SOURCE_SHA
                or set(stage.get("cases", {})) != set(CASES)):
            raise MatchedHold("G8_MATCHED_P0_STAGE_REQUIRED")
    with preflight_phase("BUILD_MANIFEST"):
        bundle = verify_bundle(build_manifest, SOURCE_SHA)
    with preflight_phase("SHARED_ELF"):
        binary = g6.ROOT/"physics_app/physics-opt"
        if file_sha(binary) != bundle["files"]["physics_app/physics-opt"]:
            raise MatchedHold("EXACT_P1_SHARED_BINARY_DIGEST_DRIFT")
    with preflight_phase("PROTECTED_ARCHIVE"):
        from issue671_secure_ei_rate_scratch import EXPECTED, read_hashed_rows
        try:
            _, tables = read_hashed_rows()
            if set(tables) != set(EXPECTED):
                raise MatchedHold("PROTECTED_ARCHIVE_INCOMPLETE")
        finally:
            os.environ.pop("OXYGEN24_RATES_TAR_XZ_B64", None)
            os.environ.pop("PROTECTED_ARCHIVE_B64", None)
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
    with preflight_phase("PRIVATE_TMPFS"):
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
            run_records = {"old": {}, "new": {}}
            case_receipt = {
                "old": run_records["old"], "new": run_records["new"],
                "protected_EI_inputs": checked_tables["old"],
                "same_case_protected_table_set": checked_tables["old"] == checked_tables["new"],
                "comparison": {"fieldwise_3ns_pilot": "NOT_RUN"},
                "science": "SCIENCE_HOLD",
            }
            result["cases"][case] = case_receipt
            for mode in ("old", "new"):
                command = g6.docker_cmd(copies[mode], ordered, observe=False)
                command[-1] += " --check-input"
                log = private/(case+"-"+mode+"-p2.log")
                code, digest = execute_privately(command, copies[mode], log, 360)
                repair_private_permissions(private)
                run_records[mode]["P2_rc"] = code
                run_records[mode]["P2_syntax_ok"] = code == 0 and b"Syntax OK" in log.read_bytes()
                if not run_records[mode]["P2_syntax_ok"]:
                    raise MatchedHold("NATIVE_P2_FAIL_"+mode.upper()+":"+case)
            for mode in ("old", "new"):
                command = g6.docker_cmd(
                    copies[mode], ordered + ["Outputs/file_base=g8_outputs/plasma"],
                    observe=False)
                code,digest=execute_privately(
                    command, copies[mode], private/(case+"-"+mode+"-p3.log"),
                    MAX_SECONDS_PER_ARM)
                repair_private_permissions(private)
                run_records[mode]["P3_rc"] = code
                if code:
                    raise MatchedHold("NATIVE_P3_FAIL_"+mode.upper()+":"+case)
                exodus = copies[mode]/"g8_outputs/plasma.e"
                if not exodus.is_file():
                    raise MatchedHold("G8_NO_NATIVE_P3_EXODUS_"+mode.upper())
                run_records[mode].update({
                    "exodus_sha256": file_sha(exodus),
                    "exodus_bytes": exodus.stat().st_size,
                })
            # A comparator failure cannot erase successful solver receipts or
            # prevent the next independent case from executing.
            record_comparison(case_receipt, copies["old"]/"g8_outputs/plasma.e",
                              copies["new"]/"g8_outputs/plasma.e")
            print("G8_CASE_COMPARISON", case,
                  case_receipt["comparison"]["fieldwise_3ns_pilot"], flush=True)
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
        # Only literal allowlisted phase labels, never arbitrary exception text.
        phase_codes = {"G8_PREFLIGHT_" + p + "_HOLD" for p in PREFLIGHT_PHASES}
        message = str(exc)
        code = message if isinstance(exc, MatchedHold) and message in phase_codes else "G8_UNCLASSIFIED_HOLD"
        print("G8_NATIVE_GATE_HOLD", code, flush=True)
        if not a.output.exists() and not a.output.is_symlink():
            receipt = {
                "schema": "issue652.g8.old_new_matched_native_3ns.v1",
                "source_sha": SOURCE_SHA,
                "P3_3ns": "HOLD", "P3_100us": "NOT_RUN",
                "P4": "NOT_RUN", "science": "SCIENCE_HOLD",
                "blocker_code": code, "cases": {},
                "private_input_artifact": False,
                "private_log_artifact": False,
                "raw_exodus_artifact": False,
            }
            a.output.parent.mkdir(parents=True, exist_ok=True)
            a.output.write_text(json.dumps(receipt, sort_keys=True, indent=2)+"\n")
        return 2
    return 0 if result["P3_3ns"].startswith("PASS_PROVISIONAL") else 3


if __name__=="__main__":
    raise SystemExit(main())
