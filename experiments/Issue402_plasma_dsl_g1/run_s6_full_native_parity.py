#!/usr/bin/env python3
"""Run the full S6 baseline/candidate equivalence gate on a trusted local runner.

Never read private reaction tables from public artifacts. Never upload them.
Run only after the original pinned source workspace and private tables are
prepared independently by an authorized operator.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import numpy as np
from scipy.io import netcdf_file

from compare_full_s6 import compare
from prepare_s6_single_kernel_migration import (
    ASSIGN, BLOCK, CASES, ORIGINAL, PINNED_SOURCE, prepare
)

IMAGE = (
    "ghcr.io/hyungseonsong-plasma/physics-build-base@"
    "sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008"
)
ARCHIVE_DIGESTS = {
    "S6-417-407-2069-H25": "441eb637c0eefa947ecbc4e14853ab435e553616b8b6a1e1d11928309409bdcb",
    "S6-941-407-2069-H25": "d8643bf2d029a3236876b8912209be61fb85cecadc3125519897e441835d0177",
}
PRIVATE_TABLE = re.compile(r"private_rates/([A-Za-z0-9_.-]+\.txt)")
CHEM = Path("experiments/Issue395_powered_chemistry_ladder")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def inspect_archive(path: Path) -> dict:
    with zipfile.ZipFile(path) as bundle:
        names = bundle.namelist()
        manifests = [name for name in names if name.endswith("/case_manifest.json")]
        if len(manifests) != 1:
            raise ValueError("Expected exactly one archived S6 manifest")
        manifest = json.loads(bundle.read(manifests[0]))
        case = manifest.get("case")
        if case not in CASES or manifest.get("source_sha") != PINNED_SOURCE:
            raise ValueError("Unexpected S6 case or historical source")
        if file_digest(path) != ARCHIVE_DIGESTS[case]:
            raise ValueError("Archived evidence ZIP SHA256 differs from the pinned original")
        if (
            manifest.get("power_W") != 400
            or manifest.get("expected_native_steps") != 460
            or manifest.get("native_end_s") != 0.0001
            or manifest.get("science_acceptance") != "HOLD"
            or manifest.get("private_rate_bytes_published") is not False
        ):
            raise ValueError("Historical run or private-data contract changed")
        layers = manifest.get("input_paths", [])
        if len(layers) != 10 or len({Path(name).name for name in layers}) != 10:
            raise ValueError("Original S6 must contain ten distinct input layers")
        inputs = [name for name in names if name.endswith(".i")]
        if len(inputs) != 10:
            raise ValueError("Archived input count differs from the original run")
        by_name = {Path(name).name: name for name in inputs}
        if set(by_name) != {Path(layer).name for layer in layers}:
            raise ValueError("Archived input names do not match the manifest")
        source_layers = {}
        for layer in layers:
            source_layers[layer] = bundle.read(by_name[Path(layer).name])
            if digest(source_layers[layer]) != manifest["input_sha256"][layer]:
                raise ValueError("Original input SHA256 mismatch: " + Path(layer).name)
        if any("private_rates/" in name for name in names):
            raise ValueError("Public archive unexpectedly contains private tables")
        base = source_layers[layers[0]].decode("utf-8")
        matches = list(BLOCK.finditer(base))
        if len(matches) != 1 or dict(ASSIGN.findall(matches[0].group())) != ORIGINAL:
            raise ValueError("Original ne_transport Kernel differs from the approved mapping")
        reference_e = [name for name in names if name.endswith("/run/plasma.e")]
        reference_csv = [name for name in names if name.endswith("/run/plasma.csv")]
        if len(reference_e) != 1 or len(reference_csv) != 1:
            raise ValueError("Original native Exodus or diagnostics missing")
        tables = set()
        for source in source_layers.values():
            tables.update(PRIVATE_TABLE.findall(source.decode("utf-8")))
        return {
            "case": case,
            "layers": layers,
            "manifest": manifest,
            "table_files": sorted(tables),
            "exodus_member": reference_e[0],
            "csv_member": reference_csv[0],
            "archive_path": path,
            "kernel_sha256": digest(matches[0].group().encode()),
        }


def check_prepared_workspace(meta: dict, source_root: Path) -> None:
    checked = subprocess.check_output(
        ["git", "-C", str(source_root), "rev-parse", "HEAD"], text=True
    ).strip()
    if checked != PINNED_SOURCE:
        raise ValueError("Prepared source checkout is not the exact pinned historical commit")
    manifest = meta["manifest"]
    for source in meta["layers"]:
        expected = manifest["input_sha256"][source]
        actual = source_root / source
        if not actual.is_file() or file_digest(actual) != expected:
            raise ValueError("Original prepared input does not match the archive: " +
                             Path(source).name)
    allowed = set(manifest["private_rate_sha256_no_bytes"].values())
    if not meta["table_files"]:
        raise ValueError("Private rate-table references are missing from the original input")
    for name in meta["table_files"]:
        table = source_root / CHEM / "private_rates" / name
        if not table.is_file() or file_digest(table) not in allowed:
            raise ValueError("Missing or noncanonical private rate table for the S6 case")
    if not (source_root / CHEM / "baseline_plasma_plus_unstructured_cover_plus_wafer.msh").is_file():
        raise ValueError("Prepared S6 mesh is missing")
    for file in ("o2_elastic.txt", "o_elastic.txt"):
        if not (source_root / CHEM / file).is_file():
            raise ValueError("Prepared public chemistry rate table missing: " + file)


def check_native_timesteps(path: Path) -> dict:
    with netcdf_file(path, "r", mmap=False) as exodus:
        times = np.array(exodus.variables["time_whole"].data, copy=True)
    if (len(times) != 461 or not np.isfinite(times).all() or
        abs(float(times[0])) > 1e-15 or
        abs(float(times[-1]) - 0.0001) > 1e-13 or
        not np.all(np.diff(times) > 0)):
        raise ValueError("Native Exodus does not contain the original 460-step 0–100 us history")
    return {"timepoints": len(times), "end_time_s": float(times[-1])}


def compare_diagnostics(a: Path, b: Path, rtol: float, atol: float) -> dict:
    with a.open(newline="") as fa, b.open(newline="") as fb:
        aa, bb = list(csv.DictReader(fa)), list(csv.DictReader(fb))
    if len(aa) != 461 or len(bb) != 461:
        raise ValueError("CSV diagnostics must include the original 461 timepoints")
    if not aa or list(aa[0]) != list(bb[0]):
        raise ValueError("Original and new diagnostic columns differ")
    columns = list(aa[0])
    largest = 0.0
    for col in columns:
        old = np.asarray([float(row[col]) for row in aa])
        new = np.asarray([float(row[col]) for row in bb])
        if not np.isfinite(old).all() or not np.isfinite(new).all():
            raise ValueError("Nonfinite diagnostic: " + col)
        if not np.allclose(old, new, rtol=rtol, atol=atol):
            raise ValueError("S6 diagnostic differs: " + col)
        largest = max(largest, float(np.max(np.abs(old - new))))
    return {"diagnostic_columns": len(columns), "diagnostic_rows": len(aa),
            "maximum_absolute_difference": largest}


def execute(image: str, root: Path, binary: Path, output: Path, inputs: list[str],
            check_input: bool, timeout_seconds: int) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "docker", "run", "--rm", "--entrypoint", "/bin/bash", "--user", "0:0",
        "--workdir", "/workspace",
        "--volume", f"{root}:/workspace:ro",
        "--volume", f"{output.parents[2]}:/results",
        "--volume", f"{binary}:/plasma-opt:ro",
        "--env", "OXYGEN_RESEARCH_400=1",
        "--env", "OXYGEN_RESEARCH_FULL24=0",
        "--env", "OXYGEN_RESEARCH_EI2738_FORMULA=0",
        "--env", "OXYGEN_RESEARCH_QUICK_5MIN=0",
        image, "-lc", 'set -euo pipefail; source /environment; /plasma-opt "$@"', "--"
    ]
    if check_input:
        command.extend(["--check-input", "-i", *inputs])
    else:
        case = output.parents[1].name
        role = output.stem.removesuffix("_run")
        command.extend(["-i", *inputs, f"Outputs/file_base=/results/{case}/runs/{role}/plasma"])
    with output.open("wb") as log:
        completed = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                                   check=False, timeout=timeout_seconds)
    if completed.returncode != 0:
        raise RuntimeError("Native check or run failed; inspect private local log: " + output.name)


def run_case(meta: dict, source_root: Path, binary: Path, work: Path,
             timeout_seconds: int, rtol: float, atol: float) -> dict:
    case = meta["case"]
    case_dir = work / case
    prep_base = case_dir / "candidate" / Path(meta["layers"][0]).name
    prep_overlay = case_dir / "candidate" / "migrated_continuity.i"
    input_dir = source_root / CHEM
    suffix = case.replace("-", "_")
    new_base = input_dir / f".s6_{suffix}_migrated_base.i"
    new_overlay = input_dir / f".s6_{suffix}_migrated_physics.i"
    if new_base.exists() or new_overlay.exists():
        raise FileExistsError("Migration input filenames already exist; cannot overwrite")
    try:
        with new_base.open("x", encoding="utf-8") as file:
            file.write(prep_base.read_text(encoding="utf-8"))
        with new_overlay.open("x", encoding="utf-8") as file:
            file.write(prep_overlay.read_text(encoding="utf-8"))
        baseline_inputs = meta["layers"]
        candidate_inputs = [str(CHEM / new_base.name), *meta["layers"][1:],
                            str(CHEM / new_overlay.name)]
        logs = case_dir / "logs"
        logs.mkdir(exist_ok=True)
        for role, inputs in (("baseline", baseline_inputs),
                             ("candidate", candidate_inputs)):
            execute(IMAGE, source_root, binary, logs / f"{role}_check.log",
                    inputs, True, timeout_seconds)
        for role, inputs in (("baseline", baseline_inputs),
                             ("candidate", candidate_inputs)):
            run_dir = case_dir / "runs" / role
            run_dir.mkdir(parents=True, exist_ok=True)
            execute(IMAGE, source_root, binary, logs / f"{role}_run.log",
                    inputs, False, timeout_seconds)
            for ext in (".e", ".csv"):
                if not (run_dir / ("plasma" + ext)).is_file():
                    raise ValueError("Native output missing: " + role + ext)
        with zipfile.ZipFile(meta["archive_path"]) as z:
            reference_e = case_dir / "reference.e"
            reference_csv = case_dir / "reference.csv"
            reference_e.write_bytes(z.read(meta["exodus_member"]))
            reference_csv.write_bytes(z.read(meta["csv_member"]))
        before = case_dir / "runs" / "baseline" / "plasma.e"
        after = case_dir / "runs" / "candidate" / "plasma.e"
        for name in (reference_e, before, after):
            check_native_timesteps(name)
        exodus_archive_baseline = compare(reference_e, before, rtol=rtol, atol=atol)
        exodus_baseline_candidate = compare(before, after, rtol=rtol, atol=atol)
        csv_archive_baseline = compare_diagnostics(
            reference_csv, case_dir / "runs" / "baseline" / "plasma.csv", rtol, atol)
        csv_baseline_candidate = compare_diagnostics(
            case_dir / "runs" / "baseline" / "plasma.csv",
            case_dir / "runs" / "candidate" / "plasma.csv", rtol, atol)
        return {
            "case": case,
            "status": "S6_FULL_460_STEP_NATIVE_PARITY_PASS__SCIENCE_HOLD",
            "historical_vs_new_baseline": exodus_archive_baseline,
            "new_baseline_vs_migration": exodus_baseline_candidate,
            "historical_csv_vs_new_baseline": csv_archive_baseline,
            "new_baseline_csv_vs_migration": csv_baseline_candidate,
            "science_acceptance": "HOLD",
        }
    finally:
        for file in (new_base, new_overlay):
            if file.is_file():
                file.unlink()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", action="append", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--run", action="store_true",
                        help="Run all four new 460-step native solves on a trusted runner")
    parser.add_argument("--timeout-seconds", type=int, default=19800)
    parser.add_argument("--rtol", type=float, default=1e-11)
    parser.add_argument("--atol", type=float, default=1e-12)
    args = parser.parse_args()
    if len(args.archive) != 2 or args.rtol < 0 or args.atol < 0 or args.timeout_seconds <= 0:
        parser.error("Exactly two archives, nonnegative tolerances and positive timeout required")
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = {"status": "NOT_EVALUATED", "cases": [],
              "science_acceptance": "HOLD"}
    try:
        metas = [inspect_archive(path.resolve()) for path in args.archive]
        if {item["case"] for item in metas} != CASES:
            raise ValueError("Both historical 417/941 cases are required")
        for item in metas:
            prepare(item["archive_path"], output)
        report["status"] = "S6_ARCHIVED_INPUTS_VERIFIED__NATIVE_NOT_EVALUATED"
        report["cases"] = [
            {"case": item["case"], "kernel_sha256": item["kernel_sha256"],
             "input_layers_verified": 10, "private_rate_bytes_present": False,
             "full_native_replay": "NOT_EVALUATED"}
            for item in metas
        ]
        if args.run:
            if not args.source_root or not args.binary or not shutil.which("docker"):
                raise ValueError("Trusted prepared source checkout, PR binary and Docker are required")
            root = args.source_root.resolve()
            binary = args.binary.resolve()
            if output.is_relative_to(root) or root.is_relative_to(output):
                raise ValueError("Output directory must be separate from the original source")
            if not binary.is_file() or not os.access(binary, os.X_OK):
                raise ValueError("Native binary is missing or not executable")
            for item in metas:
                check_prepared_workspace(item, root)
            report["binary_sha256"] = file_digest(binary)
            report["build_image"] = IMAGE
            report["cases"] = []
            for item in metas:
                result = run_case(item, root, binary, output,
                                  args.timeout_seconds, args.rtol, args.atol)
                report["cases"].append(result)
                (output / item["case"] / "native_parity_report.json").write_text(
                    json.dumps(result, indent=2) + "\n", encoding="utf-8")
            report["status"] = "BOTH_S6_460_STEP_NATIVE_PARITY_PASS__SCIENCE_HOLD"
        print(report["status"])
    except Exception as exc:
        report["status"] = "S6_FULL_NATIVE_PARITY_NOT_PROVEN"
        report["failure"] = str(exc)
        raise
    finally:
        (output / "s6_native_parity_summary.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
