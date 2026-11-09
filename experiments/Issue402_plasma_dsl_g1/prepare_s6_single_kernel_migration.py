#!/usr/bin/env python3
"""Prepare an isolated one-kernel S6 migration from completed native archives.

The original archives and all original input files are immutable.
This prepares baseline/candidate inputs but does not claim a native solve.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path

PINNED_SOURCE = "29d1acc6ef7969908b86719e4b95c73a1565136d"
CASES = {"S6-417-407-2069-H25", "S6-941-407-2069-H25"}
KERNEL = "ne_transport"
ORIGINAL = {
    "type": "PhysicsFEMLogMolarDriftDiffusion",
    "variable": "log_ne",
    "potential": "potential",
    "mobility": "electron_mobility",
    "diffusion": "electron_diffusion",
    "charge_number": "-1",
    "block": "plasma",
}
BLOCK = re.compile(
    r"(?m)^  \[ne_transport\][ \t]*\r?\n"
    r"(?:^    [^\n]*\r?\n)+"
    r"^  \[\][ \t]*\r?\n"
)
ASSIGN = re.compile(r"(?m)^[ \t]*([a-z_]+)[ \t]*=[ \t]*([^\r\n]+)[ \t]*$")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def prepare(archive: Path, output_root: Path) -> dict:
    with zipfile.ZipFile(archive) as bundle:
        names = bundle.namelist()
        found = [n for n in names if n.endswith("/case_manifest.json")]
        if len(found) != 1:
            raise ValueError("Archive must contain exactly one case manifest")
        manifest = json.loads(bundle.read(found[0]))
        case = manifest.get("case")
        if case not in CASES:
            raise ValueError("Unexpected case: " + str(case))
        if (
            manifest.get("source_sha") != PINNED_SOURCE
            or manifest.get("science_acceptance") != "HOLD"
            or manifest.get("power_W") != 400
            or manifest.get("expected_native_steps") != 460
        ):
            raise ValueError("Archived science or provenance contract changed")
        layers = manifest.get("input_paths")
        if not isinstance(layers, list) or len(layers) != 10:
            raise ValueError("Expected exactly ten ordered original input layers")
        basenames = [Path(name).name for name in layers]
        if len(set(basenames)) != 10:
            raise ValueError("Original input names are not unique")
        zipped = [name for name in names if name.endswith(".i")]
        if len(zipped) != 10 or {Path(name).name for name in zipped} != set(basenames):
            raise ValueError("Archive inputs do not match the manifest")
        if any("/" in name or "\\" in name or name in {".", ".."} for name in basenames):
            raise ValueError("Unsafe input name")
        source_files = {
            name: bundle.read(next(x for x in zipped if Path(x).name == name))
            for name in basenames
        }
    base = basenames[0]
    source = source_files[base].decode("utf-8")
    matches = list(BLOCK.finditer(source))
    if len(matches) != 1:
        raise ValueError("Expected one original ne_transport Kernel")
    if any("ne_transport" in source_files[name].decode("utf-8")
           and re.search(r"(?m)^[ \t]*\[ne_transport\][ \t]*$", source_files[name].decode("utf-8"))
           for name in basenames[1:]):
        raise ValueError("Later overlay redefines ne_transport")
    previous = dict(ASSIGN.findall(matches[0].group()))
    if previous != ORIGINAL:
        raise ValueError("Original Kernel parameters changed: refusing migration")
    candidate_source = source[:matches[0].start()] + source[matches[0].end():]
    if BLOCK.search(candidate_source):
        raise ValueError("Original Kernel remains after migration")

    overlay = """[Physics]
  [Plasmas]
    [Transport]
      [DriftDiffusion]
        [Continuity]
          block = plasma
          fem_species = 'e'
          fvm_species = 'O2p Om Op'
          variables = 'log_ne log_ni log_nm log_nop'
          fem_potential = potential
          fem_mobility = 'electron_mobility'
          fem_diffusion = 'electron_diffusion'
          fem_charge_numbers = '-1'
          fem_kernel_names = 'ne_transport'
        []
      []
    []
  []
[]
"""
    result_dir = output_root / case
    if result_dir.exists():
        raise FileExistsError("Output exists: " + str(result_dir))
    baseline = result_dir / "baseline"
    candidate = result_dir / "candidate"
    baseline.mkdir(parents=True)
    candidate.mkdir(parents=True)
    original_digests = {}
    for name in basenames:
        data = source_files[name]
        (baseline / name).write_bytes(data)
        (candidate / name).write_bytes(
            candidate_source.encode("utf-8") if name == base else data
        )
        original_digests[name] = sha256(data)
    overlay_name = "migrated_continuity.i"
    (candidate / overlay_name).write_text(overlay, encoding="utf-8")
    report = {
        "case": case,
        "source_sha": PINNED_SOURCE,
        "science_acceptance": "HOLD",
        "original_layer_count": len(basenames),
        "migrated_kernel": KERNEL,
        "preserved_native_kernel_parameters": ORIGINAL,
        "preserved_original_kernel_name": True,
        "untouched_layers_sha256": {
            name: original_digests[name] for name in basenames[1:]
        },
        "baseline_input_order": basenames,
        "candidate_input_order": basenames + [overlay_name],
        "static_operator_mapping": "MATCH",
        "native_check_input": "NOT_EVALUATED",
        "native_400W_100us_parity": "NOT_EVALUATED",
        "notes": "Requires pinned PhysicsApp, the original runtime dependencies, and both new native solves.",
    }
    (result_dir / "migration_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", action="append", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if len(args.archive) != 2:
        parser.error("Supply one 417 archive and one 941 archive")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    reports = [prepare(path, args.output_dir) for path in args.archive]
    if {row["case"] for row in reports} != CASES:
        raise ValueError("Both S6 cases are required")
    print("TWO_S6_CASES_PREPARED_STATIC_ONLY")
    for row in reports:
        print(row["case"], row["static_operator_mapping"], "native parity pending")


if __name__ == "__main__":
    main()
