#!/usr/bin/env python3
"""Archive only proven public-rate P3 outputs; never copy raw logs or rate files."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
from run_issue493 import verify_native_csv

SOURCE = "29d1acc6ef7969908b86719e4b95c73a1565136d"
CANDIDATE = "bebaf47a33ff5ee1d6b933d9691bf48f5ec0f947"
OCI = "ghcr.io/hyungseonsong-plasma/physics-build-base@sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008"

def sha(path: Path) -> str:
    dig = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1 << 20), b""):
            dig.update(chunk)
    return dig.hexdigest()

def inspect(report: dict, root: Path, case: str, arm: str) -> tuple:
    if case not in ("417", "941") or arm not in ("B", "C"):
        raise ValueError("INVALID_CASE_ARM")
    if (report.get("schema") != "issue493_public_p3_native_v2"
        or report.get("case") != case
        or report.get("mode") != f"complete-{arm.lower()}"
        or report.get("source_sha") != SOURCE
        or report.get("candidate_sha") != CANDIDATE
        or report.get("oci_image") != OCI):
        raise ValueError("UNTRUSTED_SOURCE_OR_ARM")
    if (report.get("P0") != "PASS" or report.get("P1") != "PASS"
        or report.get("P3") != "HOLD" or report.get("P4") != "NOT_RUN"
        or report.get("science") != "SCIENCE_HOLD"):
        raise ValueError("AGGREGATE_GATE_MISMATCH")
    entry = report.get("variants", {}).get(arm, {})
    other = report.get("variants", {}).get("C" if arm == "B" else "B", {})
    if (entry.get("P2") != "PASS" or entry.get("P3") != "PASS"
        or other.get("P2") != "NOT_RUN" or other.get("P3") != "NOT_RUN"
        or report.get("p2_passed_arms") != [arm]
        or report.get("p3_passed_arms") != [arm]
        or entry.get("frames") != 461 or entry.get("t_end_seconds") != 0.0001
        or entry.get("exit_code") != 0 or entry.get("termination") != "EXIT"
        or entry.get("timed_out") is not False or entry.get("timeout_budget_seconds") != 20400):
        raise ValueError("FULL_NATIVE_COMPLETION_NOT_PROVEN")
    binary = entry.get("p1_binary_sha256")
    if not isinstance(binary, str) or not re.fullmatch("[a-f0-9]{64}", binary):
        raise ValueError("MISSING_SOURCE_BOUND_BINARY")
    folder = root / f"{case}_{arm}" / "issue493_outputs" / "run"
    outputs = {"plasma.e": folder / "plasma.e", "plasma.csv": folder / "plasma.csv"}
    manifest = {
        "schema": "issue493_public_p3_artifact_v1", "case": case, "arm": arm,
        "source_sha": SOURCE, "candidate_sha": CANDIDATE, "oci_image": OCI,
        "p1_binary_sha256": binary, "mesh_sha256": report.get("mesh_sha256"),
        "frames": 461, "t_end_seconds": 0.0001,
        "P0": "PASS", "P1": "PASS", "P2": "PASS", "P3": "PASS",
        "P4": "NOT_RUN", "science": "SCIENCE_HOLD", "files": {},
    }
    for name, file in outputs.items():
        if not file.is_file() or file.is_symlink() or file.stat().st_size <= 0:
            raise ValueError("OUTPUT_ABSENT_OR_UNSAFE")
        dig, size = sha(file), file.stat().st_size
        prefix = "native_exodus" if name == "plasma.e" else "native_csv"
        if entry.get(prefix + "_sha256") != dig or entry.get(prefix + "_bytes") != size:
            raise ValueError("OUTPUT_PROVENANCE_MISMATCH")
        manifest["files"][name] = {"sha256": dig, "bytes": size}
    with outputs["plasma.e"].open("rb") as source:
        magic = source.read(8)
    if not (magic.startswith(b"CDF") or magic.startswith(b"\x89HDF")):
        raise ValueError("EXODUS_FORMAT_NOT_NETCDF")
    verify_native_csv(outputs["plasma.csv"])
    return outputs, manifest

def publish(status: Path, run_root: Path, out: Path, case: str, arm: str) -> dict:
    inputs, manifest = inspect(json.loads(status.read_text()), run_root, case, arm)
    if out.exists():
        raise ValueError("ARCHIVE_ROOT_ALREADY_EXISTS")
    out.mkdir(mode=0o700, parents=True)
    for name, source in inputs.items():
        target = out / name
        shutil.copyfile(source, target)
        if sha(target) != manifest["files"][name]["sha256"]:
            raise ValueError("ARCHIVE_HASH_CHANGED")
    (out / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    return manifest

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--publish-root", type=Path, required=True)
    parser.add_argument("--case", choices=("417", "941"), required=True)
    parser.add_argument("--arm", choices=("B", "C"), required=True)
    a = parser.parse_args()
    try:
        m = publish(a.status, a.run_root, a.publish_root, a.case, a.arm)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print("ISSUE493_PUBLIC_OUTPUT_ARCHIVE_HOLD", type(exc).__name__, file=sys.stderr)
        return 2
    print(json.dumps({"event":"ISSUE493_PUBLIC_OUTPUT_ARCHIVE_PASS",
        "case":a.case, "arm":a.arm, "frames":461,
        "binary_sha256":m["p1_binary_sha256"], "files":m["files"],
        "science":"SCIENCE_HOLD"}, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
