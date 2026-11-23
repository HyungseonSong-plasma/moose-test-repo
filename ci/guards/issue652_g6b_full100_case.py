#!/usr/bin/env python3
"""#652 G6-B original Public D 100-row: one independent 460-step Native case.

An explicit --authorize-full-100us gate is mandatory. Run only in a protected
Actions runner. Full input C0 is left unchanged (100us, implicit Euler,
checkpoint true); one 417 or 941 case executes in private /dev/shm.

Outputs: bounded, non-sensitive status JSON and, ONLY if strict 461-point
postprocessing succeeds, explicit plasma.e/plasma.csv science output files.
No raw private rate tables, input decks, registration traces, solver logs or
checkpoint files are ever published. Finite full-time completion is NOT
scientific equivalence or charge-conservation acceptance.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time

import issue652_g6_runtime_gate as g6
import issue652_g6b_publicd100_stage as d100
from issue652_g5_native_p2 import C0, OCI, file_sha, secure_tmpfs_cleanup

CASES = ("417", "941")
MAX_SOLVER_SECONDS = 20400  # Existing full P3 single-arm 340-minute budget.
MAX_LOG_BYTES = 256 * 1024 * 1024
MIN_FREE_BYTES = 300 * 1024 * 1024
STEP_RE = re.compile(
    r"(?im)^\s*time\s*step\s*[:#]?\s*(\d{1,6})"
    r"(?:\s*[,;:]\s*time\s*=\s*([0-9.eE+-]+))?"
)


class Full100Hold(ValueError):
    pass


def load(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise Full100Hold("RECEIPT_MISSING_OR_SYMLINK")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise Full100Hold("RECEIPT_NOT_OBJECT")
    return data


def checked_preflight(*, case: str, staged: Path, p0_path: Path,
                      registration_path: Path, manifest_path: Path,
                      expected_source: str) -> tuple[dict, dict]:
    from issue652_g6b_parallel_evidence import verify_bundle, SOURCE_100_SHA

    if case not in CASES or not re.fullmatch(r"[0-9a-f]{40}", expected_source):
        raise Full100Hold("CASE_OR_SOURCE_INVALID")
    if g6.exact_source() != expected_source:
        raise Full100Hold("FULL100_EXACT_HEAD_MISMATCH")
    p0 = load(p0_path)
    g5 = load(staged.parent / "g5-result/g5_stage_receipt.json")
    registration = load(registration_path)
    bundle = verify_bundle(manifest_path, expected_source)
    if (p0.get("schema") != "issue652.g6b.publicd100.stage.v1"
            or p0.get("source_sha") != expected_source
            or p0.get("original_publicd_lookup_sha256") != SOURCE_100_SHA
            or p0.get("lookup_rows") != 100
            or set(p0.get("cases", {})) != set(CASES)
            or p0.get("protected_rate_data_in_receipt") is not False
            or g5.get("source_sha") != expected_source
            or set(g5.get("cases", {})) != set(CASES)):
        raise Full100Hold("PUBLIC_G5_G6B_IDENTITY_DRIFT")
    p0_case = p0["cases"][case]
    if (p0_case.get("P0") != "PASS_SCRATCH_ONLY_100ROW_PROVENANCE"
            or p0_case.get("new_lookup_sha256") != SOURCE_100_SHA
            or p0_case.get("P3_100us") != "NOT_RUN"
            or p0_case.get("science") != "SCIENCE_HOLD"):
        raise Full100Hold("P0_FULL100_PUBLIC_CASE_NOT_PROVEN")
    r = registration
    trace = r.get("cases", {}).get(case, {}).get("registration")
    if (r.get("source_sha") != expected_source or r.get("oci") != OCI
            or r.get("binary_sha256") != bundle["files"]["physics_app/physics-opt"]
            or r.get("observer_sha256") != bundle["files"]["physics_app/g6_owner_tracer.so"]
            or r.get("schema") != "issue652.g6.registration_p3.v1"
            or set(r.get("cases", {})) != {case}
            or r.get("registration") != "PASS_TYPED_15_OWNERS"
            or r.get("P3_3ns") != "NOT_RUN"
            or r.get("P4_100us") != "NOT_RUN"
            or r.get("raw_private_rates_in_artifact") is not False
            or r.get("science") != "SCIENCE_HOLD"
            or not isinstance(trace, dict)
            or trace.get("status") != "EXPECTED_15_GENERATED_OWNERS_TRACE_PASS"
            or len(trace.get("observed_expected_owners", {})) != 15
            or r["cases"][case].get("P2_syntax_ok") is not True):
        raise Full100Hold("PRECEDING_NATIVE_P2_REGISTRATION_NOT_PROVEN")
    ordered = g5["cases"][case]["ordered"]
    layers = g5["cases"][case]["layer_sha256"]
    if (len(ordered) != 11 or set(layers) != {Path(x).name for x in ordered}
            or Path(ordered[0]).name != C0):
        raise Full100Hold("G5_LAYER_ORDER_OR_DIGESTS_INVALID")
    public = staged / "scratch" / case
    root = public / d100.CHEM_RELATIVE
    for path in public.rglob("*"):
        if path.is_symlink():
            raise Full100Hold("PUBLIC_STAGE_SYMLINK_DENIED")
    if not root.is_dir() or root.is_symlink():
        raise Full100Hold("PUBLIC_STAGE_MISSING")
    if {Path(x).name: file_sha(root / Path(x).name) for x in ordered} != layers:
        raise Full100Hold("PUBLIC_ELEVEN_LAYER_DRIFT")
    grid = d100.time_contract((root / C0).read_bytes())
    if grid != p0_case.get("time") or grid["intervals"] != 460:
        raise Full100Hold("FULL100_GRID_PROVENANCE_DRIFT")
    lookup = public / d100.TABLE_RELATIVE
    if file_sha(lookup) != SOURCE_100_SHA:
        raise Full100Hold("PUBLIC_D_100_LOOKUP_DRIFT")
    if file_sha(g6.ROOT / "physics_app/physics-opt") != r["binary_sha256"]:
        raise Full100Hold("P1_BINARY_CHANGED_AFTER_REGISTRATION")
    return {"g5": g5, "p0": p0, "registration": r, "public": public,
            "ordered": ordered, "layers": layers}, grid


def _progress(log: Path) -> tuple[int | None, float | None]:
    with log.open("rb") as stream:
        stream.seek(0, os.SEEK_END)
        end = stream.tell()
        stream.seek(max(0, end - 1_000_000))
        raw = stream.read()
    if end > 1_000_000:
        raw = raw.partition(b"\n")[2]
    text = raw.decode("utf-8", errors="replace")
    found = STEP_RE.findall(text)
    steps = [(int(step), float(t) if t else None) for step, t in found
             if int(step) <= 460]
    return (
        max((s for s, _ in steps), default=None),
        max((t for _, t in steps if t is not None and
             math.isfinite(t) and 0 <= t <= 1e-4 + 1e-10), default=None),
    )


def monitor_native(command: list[str], *, case: str, private: Path,
                   log: Path, timeout_seconds: int,
                   heartbeat_seconds: int = 60) -> dict:
    if case not in CASES or not 1 <= timeout_seconds <= MAX_SOLVER_SECONDS:
        raise Full100Hold("INVALID_FULL100_SOLVER_BUDGET")
    if log.exists() or log.is_symlink():
        raise Full100Hold("PRIVATE_LOG_OVERWRITE")
    container = "issue652-g6b-full100-" + case
    if command[:3] != ["docker", "run", "--rm"]:
        raise Full100Hold("UNREVIEWED_DOCKER_COMMAND")
    command = command[:3] + ["--name", container] + command[3:]
    started = time.monotonic()
    rc = None
    reason = "UNKNOWN"
    samples = 0
    last_step = None
    last_t = None
    p = None
    # Never stream original solver output to Actions: private log only.
    with log.open("xb") as sink:
        try:
            p = subprocess.Popen(
                command, cwd=private, stdout=sink,
                stderr=subprocess.STDOUT, env={k: v for k, v in os.environ.items()
                                              if k != "PROTECTED_ARCHIVE_B64"},
            )
            while True:
                elapsed = time.monotonic() - started
                if elapsed >= timeout_seconds:
                    reason = "TIMEOUT"
                    break
                try:
                    rc = p.wait(timeout=min(heartbeat_seconds, timeout_seconds - elapsed))
                    reason = "EXIT_ZERO" if rc == 0 else "SOLVER_NONZERO"
                    break
                except subprocess.TimeoutExpired:
                    pass
                samples += 1
                latest, latest_t = _progress(log)
                if latest is not None:
                    last_step = max(last_step or 0, latest)
                if latest_t is not None:
                    last_t = max(last_t or 0, latest_t)
                if log.stat().st_size > MAX_LOG_BYTES:
                    reason = "LOG_BUDGET_EXCEEDED"
                    break
                if shutil.disk_usage(private).free < MIN_FREE_BYTES:
                    reason = "STORAGE_BUDGET_EXCEEDED"
                    break
                # Only sanitized timestep and monotonic elapsed time appear in CI logs.
                print(json.dumps({
                    "event": "G6B_NATIVE_100US_HEARTBEAT",
                    "case": case, "elapsed_s": round(elapsed),
                    "last_step": last_step, "last_time_s": last_t,
                    "checkpoint_contract": True,
                    "science": "HOLD",
                }, sort_keys=True), flush=True)
        finally:
            if p is not None and p.poll() is None:
                subprocess.run(
                    ["docker", "rm", "-f", container],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=40, check=False,
                )
                p.kill()
                p.wait(timeout=30)
    last, t = _progress(log)
    return {
        "status": reason, "exit_code": rc,
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "timeout_budget_seconds": timeout_seconds,
        "last_reported_step": max(
            (x for x in (last, last_step) if x is not None), default=None),
        "last_reported_time_seconds": max(
            (x for x in (t, last_t) if x is not None), default=None),
        "heartbeat_count": samples, "private_log_bytes": log.stat().st_size,
        "private_log_sha256": file_sha(log),
    }


def verify_full_csv(path: Path, original_c0: bytes) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size < 100:
        raise Full100Hold("FULL100_CSV_MISSING")
    source = original_c0.decode("utf-8")
    times_text = re.findall(r"(?m)^    time_sequence = '([^'\n]+)'$", source)
    if len(times_text) != 1:
        raise Full100Hold("FULL100_INPUT_SEQUENCE_UNREADABLE")
    expected = [float(v) for v in times_text[0].split()]
    if len(expected) != 461 or d100.time_contract(original_c0)["intervals"] != 460:
        raise Full100Hold("FULL100_INPUT_TIME_GRID_DRIFT")
    tracked = {key: {"first": None, "last": None, "min": None, "max": None}
               for key in g6.REQUIRED_CSV}
    count = 0
    with path.open(newline="") as source_file:
        reader = csv.DictReader(source_file)
        if (not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames))
                or not set(g6.REQUIRED_CSV).issubset(reader.fieldnames)
                or "time" not in reader.fieldnames):
            raise Full100Hold("FULL100_CSV_MISSING_REQUIRED_FIELDS")
        for row in reader:
            if count >= 461 or None in row or any(v is None or not v.strip() for v in row.values()):
                raise Full100Hold("FULL100_CSV_INVALID_ROW_OR_OVERRUN")
            try:
                numeric = {k: float(v) for k, v in row.items()}
            except ValueError as exc:
                raise Full100Hold("FULL100_CSV_NONNUMERIC") from exc
            if any(not math.isfinite(x) for x in numeric.values()):
                raise Full100Hold("FULL100_CSV_NONFINITE")
            time_observed = numeric["time"]
            if abs(time_observed - expected[count]) > max(1e-14, abs(expected[count]) * 1e-8):
                raise Full100Hold("FULL100_CSV_TIME_GRID_NOT_EXACT_460_INTERVALS")
            if numeric["ne_min"] <= 0 or numeric["ne_max"] <= 0:
                raise Full100Hold("FULL100_ELECTRON_DENSITY_NONPOSITIVE")
            if numeric["potential_min"] > numeric["potential_max"]:
                raise Full100Hold("FULL100_POTENTIAL_INVERTED")
            for key, evidence in tracked.items():
                value = numeric[key]
                if count == 0:
                    evidence["first"] = value
                    evidence["min"] = value
                    evidence["max"] = value
                evidence["last"] = value
                evidence["min"] = min(value, evidence["min"])
                evidence["max"] = max(value, evidence["max"])
            count += 1
    if count != 461:
        raise Full100Hold("FULL100_NOT_461_CSV_TIME_POINTS")
    return {
        "status": "PASS_NATIVE_FINITE_EXACT_461_TIME_POINTS",
        "time_points": count, "intervals": count - 1,
        "t0_seconds": expected[0], "t_end_seconds": expected[-1],
        "extrema": tracked,
        "charge_conservation_budget": "NOT_EVALUATED",
        "semantic_parity": "NOT_EVALUATED",
    }


def verify_exodus(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size < 4096:
        raise Full100Hold("FULL100_EXODUS_MISSING_OR_EMPTY")
    with path.open("rb") as f:
        magic = f.read(8)
    if not (magic.startswith(b"CDF\x01") or magic.startswith(b"CDF\x02")
            or magic.startswith(b"CDF\x05") or magic == b"\x89HDF\r\n\x1a\n"):
        raise Full100Hold("FULL100_EXODUS_NOT_NETCDF_OR_HDF5")
    return {"sha256": file_sha(path), "bytes": path.stat().st_size,
            "format_header_verified": True,
            "nodal_field_parity": "NOT_EVALUATED"}


def run(*, case: str, staged: Path, p0: Path, registration: Path,
        manifest: Path, source_sha: str, output: Path, export: Path,
        timeout_seconds: int, authorize: bool) -> dict:
    if not authorize:
        raise Full100Hold("FULL100_EXPLICIT_USER_AUTHORIZATION_REQUIRED")
    if case not in CASES or not 1 <= timeout_seconds <= MAX_SOLVER_SECONDS:
        raise Full100Hold("FULL100_CASE_OR_BUDGET_INVALID")
    if output.exists() or output.is_symlink() or export.exists() or export.is_symlink():
        raise Full100Hold("FULL100_OUTPUT_REUSE_DENIED")
    proof, grid = checked_preflight(
        case=case, staged=staged, p0_path=p0,
        registration_path=registration, manifest_path=manifest,
        expected_source=source_sha,
    )
    binary_hash = proof["registration"]["binary_sha256"]
    result = {
        "schema": "issue652.g6b.native_100us_case.v1",
        "source_sha": source_sha, "case_id": case,
        "oci_ref": OCI, "binary_sha256": binary_hash,
        "build_manifest_sha256": file_sha(manifest),
        "original_publicd_lookup_sha256": d100.PUBLIC_D_100_SHA256,
        "original_time_grid": grid, "P1": "PASS", "P2": "PASS_TYPED_15_OWNERS",
        "P3_100us": "HOLD", "P4": "NOT_RUN",
        "science": "SCIENCE_HOLD", "conservation": "UNVERIFIED",
        "raw_protected_rates_in_artifact": False,
        "native_solver_log_in_artifact": False,
        "native_input_deck_in_artifact": False,
        "original_s6_input_unchanged": True,
        "timeout_seconds": timeout_seconds,
    }
    private = None
    tables = {}
    try:
        from issue671_secure_ei_rate_scratch import (
            EXPECTED, REQUIRED, read_hashed_rows, validate_rows,
        )
        _, tables = read_hashed_rows()
        os.environ.pop("PROTECTED_ARCHIVE_B64", None)
        if set(tables) != set(EXPECTED):
            raise Full100Hold("PROTECTED_HASH_SET_INCOMPLETE")
        private = Path(tempfile.mkdtemp(prefix="issue652-g5-full100-", dir="/dev/shm"))
        os.chmod(private, 0o700)
        public = proof["public"]
        shutil.copytree(public, private / "case")
        work = private / "case"
        if any(p.is_symlink() for p in work.rglob("*")):
            raise Full100Hold("PRIVATE_STAGE_SYMLINK_DENIED")
        chem = work / d100.CHEM_RELATIVE
        rate_dir = chem / "private_rates"
        if rate_dir.exists() or rate_dir.is_symlink():
            raise Full100Hold("PRIVATE_RATES_EXIST_BEFORE_INJECTION")
        rate_dir.mkdir(mode=0o700)
        for name in sorted(REQUIRED[case]):
            blob = tables[name]
            if g6.sha(blob) != EXPECTED[name] or validate_rows(blob) != 100:
                raise Full100Hold("PROTECTED_RATE_HASH_OR_ROWS_INVALID")
            target = rate_dir / name
            fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                         getattr(os, "O_NOFOLLOW", 0), 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(blob)
            if file_sha(target) != EXPECTED[name]:
                raise Full100Hold("PROTECTED_RATE_STAGING_DRIFT")
        del blob
        tables.clear()
        if file_sha(g6.ROOT / "physics_app/physics-opt") != binary_hash:
            raise Full100Hold("BINARY_DRIFT_BEFORE_FULL100")
        expected_layers = proof["layers"]
        ordered = proof["ordered"]
        if {Path(x).name: file_sha(chem / Path(x).name) for x in ordered} != expected_layers:
            raise Full100Hold("PRIVATE_INPUT_LAYERS_CHANGED")
        c0 = (chem / C0).read_bytes()
        if file_sha(chem / C0) != expected_layers[C0]:
            raise Full100Hold("PRIVATE_C0_TIME_GRID_CHANGED")
        d100.time_contract(c0)
        out = work / "issue652_outputs"
        out.mkdir(mode=0o700)
        command = g6.docker_cmd(
            work, ordered + ["Outputs/file_base=issue652_outputs/plasma"],
            observe=False)
        evidence = monitor_native(
            command, case=case, private=work,
            log=private / "native_solver_private.log",
            timeout_seconds=timeout_seconds)
        result["solver"] = evidence
        if evidence["status"] != "EXIT_ZERO":
            result["P3_100us"] = "HOLD_" + evidence["status"]
        else:
            csv_path = out / "plasma.csv"
            exodus_path = out / "plasma.e"
            csv_evidence = verify_full_csv(csv_path, c0)
            exodus_evidence = verify_exodus(exodus_path)
            result["P3_100us"] = "PASS_NATIVE_FINITE_461_FRAMES"
            result["time_series"] = csv_evidence
            result["native_csv"] = {"sha256": file_sha(csv_path),
                                    "bytes": csv_path.stat().st_size}
            result["native_exodus"] = exodus_evidence
            if export.exists():
                raise Full100Hold("EXPORT_LOCATION_RACE")
            export.mkdir(parents=True, mode=0o700)
            for label, source_file in (("plasma.csv", csv_path), ("plasma.e", exodus_path)):
                target = export / label
                shutil.copyfile(source_file, target)
                if file_sha(target) != file_sha(source_file):
                    raise Full100Hold("PUBLIC_OUTPUT_COPY_SHA_MISMATCH")
            result["public_outputs_ready"] = True
    except Exception as exc:
        # Only narrow error type/class; never show rate names/contents or native logs.
        result["P3_100us"] = "HOLD"
        result["blocker_type"] = type(exc).__name__
        result["public_outputs_ready"] = False
    finally:
        tables.clear()
        os.environ.pop("PROTECTED_ARCHIVE_B64", None)
        if private is not None:
            secure_tmpfs_cleanup(private)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print("G6B_FULL100_SINGLE_CASE", case, result["P3_100us"],
          "P4_NOT_RUN SCIENCE_HOLD", flush=True)
    return result


def main() -> int:
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=CASES, required=True)
    parser.add_argument("--staged", type=Path, required=True)
    parser.add_argument("--public-p0", type=Path, required=True)
    parser.add_argument("--registration", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--export-outputs", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=MAX_SOLVER_SECONDS)
    parser.add_argument("--authorize-full-100us", action="store_true")
    args = parser.parse_args()
    if not args.authorize_full_100us:
        parser.error("full native 100us requires explicit --authorize-full-100us")
    if not 1 <= args.timeout_seconds <= MAX_SOLVER_SECONDS:
        parser.error("native solver timeout must be 1..20400 seconds")
    result = run(
        case=args.case, staged=args.staged, p0=args.public_p0,
        registration=args.registration, manifest=args.manifest,
        source_sha=args.source_sha, output=args.output,
        export=args.export_outputs, timeout_seconds=args.timeout_seconds,
        authorize=args.authorize_full_100us,
    )
    return 0 if result["P3_100us"] == "PASS_NATIVE_FINITE_461_FRAMES" else 3


if __name__ == "__main__":
    raise SystemExit(main())
