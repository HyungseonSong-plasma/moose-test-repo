#!/usr/bin/env python3
"""Exact-source, fail-closed Native A/B for code4's TWO zero-field smoke inputs.

Stage the original legacy C++ kernel and the new zero-velocity FVAdvection
using identical inputs otherwise. Scientific scope is strictly phi=0,
raw mean_en, current two test-only inputs. No C++ retirement authorization.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
INPUT_ROOT = ROOT / "physics_app" / "ci"
PAIRS = {
    "electron_energy_transport_smoke.i": "b7b3850cb111cce0fed9414e75a7b2d3454d9b4e",
    "electron_energy_lookup_response_smoke.i": "12e775b24d2fb5bdfd46ba375a17d3cebca47991",
}
BEFORE = """  [energy_drift]
    type = PhysicsFVElectrostaticDrift
    variable = mean_en
    potential = phi_zero
    mobility = electron_energy_mobility
    carrier = carrier_one
    charge_number = -1
    advected_interp_method = upwind
  []"""
AFTER = """  [energy_drift]
    type = FVAdvection
    variable = mean_en
    velocity = '0 0 0'
    advected_interp_method = upwind
  []"""
TOL = {"rel": 1e-8, "abs": 1e-10}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def assert_exact_head(expected_head: str) -> None:
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if head != expected_head:
        raise ValueError(f"SOURCE_HEAD_MISMATCH:{head}!={expected_head}")


def prepare(folder: Path, expected_head: str) -> dict:
    assert_exact_head(expected_head)
    folder.mkdir(parents=True, exist_ok=True)
    entries = []
    tables = {}
    for filename, original_blob in PAIRS.items():
        raw = (INPUT_ROOT / filename).read_bytes()
        text = raw.decode("utf-8")
        if text.count(AFTER) != 1 or BEFORE in text:
            raise ValueError(f"NOT_AN_EXACT_CODE4_C1_REWIRE:{filename}")
        if text.count("[phi_zero]\n    type = ParsedFunction\n    expression = '0*x'") != 1:
            raise ValueError(f"ZERO_FIELD_UNPROVEN:{filename}")
        original = text.replace(AFTER, BEFORE)
        if git_blob(original.encode()) != original_blob:
            raise ValueError(f"UNEXPECTED_UNRELATED_CHANGE:{filename}")
        for version, body in (("before", original), ("after", text)):
            target = folder / f"{Path(filename).stem}_{version}.i"
            target.write_text(body, encoding="utf-8")
            entries.append({"input": target.name, "sha256": digest(target.read_bytes()),
                            "version": version, "source": filename})
        matches = re.findall(r"(?m)^\s*table_file\s*=\s*(\S+)\s*$", text)
        if len(matches) != 1:
            raise ValueError(f"TABLE_IDENTITY_UNRESOLVED:{filename}")
        table = matches[0]
        if "/" in table or ".." in table:
            raise ValueError(f"TABLE_PATH_UNEXPECTED:{table}")
        table_src = INPUT_ROOT / table
        shutil.copyfile(table_src, folder / table)
        tables[table] = digest(table_src.read_bytes())
    data = {
        "schema": "code4.zero_field_smoke_native_input.v0.1",
        "source_head": expected_head,
        "classification": "STAGED_NOT_EXECUTED",
        "scope": "TWO_TEST_ONLY_ZERO_FIELD_ENERGY_SMOKES",
        "inputs": entries,
        "tables_sha256": tables,
        "reference_original_blobs": PAIRS,
        "tolerance": TOL,
        "safe_delete": "HOLD"
    }
    (folder / "staging.json").write_text(json.dumps(data, indent=2, sort_keys=True)+"\n")
    print("CODE4_C1_STAGED_INPUTS=4")
    return data


def compare(folder: Path, expected_head: str, binary_hash: str) -> dict:
    assert_exact_head(expected_head)
    data = json.loads((folder / "staging.json").read_text())
    if (data["source_head"] != expected_head or
            data["schema"] != "code4.zero_field_smoke_native_input.v0.1" or
            data["reference_original_blobs"] != PAIRS or
            data["tolerance"] != TOL or
            not re.fullmatch(r"[0-9a-f]{64}", binary_hash or "")):
        raise ValueError("STAGE_OR_BINARY_IDENTITY_MISMATCH")
    for entry in data["inputs"]:
        path = folder / entry["input"]
        if not path.is_file() or digest(path.read_bytes()) != entry["sha256"]:
            raise ValueError(f"INPUT_HASH_MISMATCH:{entry['input']}")
    for table, sha in data["tables_sha256"].items():
        if digest((folder / table).read_bytes()) != sha:
            raise ValueError(f"TABLE_HASH_MISMATCH:{table}")
    comparisons, failures = [], []
    for filename in PAIRS:
        stem = Path(filename).stem
        rows = {}
        for version in ("before", "after"):
            path = folder / f"{stem}_{version}_out.csv"
            if not path.exists():
                raise FileNotFoundError(f"NO_NATIVE_CSV:{path}")
            with path.open(newline="") as f:
                rows[version] = list(csv.DictReader(f))
        first, second = rows["before"], rows["after"]
        if len(first) < 2 or len(first) != len(second):
            failures.append(f"{stem}:INCOMPLETE_TIME_GRID")
            continue
        if set(first[0]) != set(second[0]) or "time" not in first[0]:
            failures.append(f"{stem}:COLUMN_SET_CHANGED")
            continue
        if len(first[0]) < 2:
            failures.append(f"{stem}:NO_PHYSICAL_OBSERVABLE")
            continue
        max_relative = {}
        for index, (before, after) in enumerate(zip(first, second)):
            for key in before:
                try:
                    a,b = float(before[key]),float(after[key])
                except (TypeError,ValueError):
                    failures.append(f"{stem}:{key}:NON_NUMERIC")
                    continue
                if not (math.isfinite(a) and math.isfinite(b)):
                    failures.append(f"{stem}:{key}:NONFINITE")
                    continue
                if key == "time" and abs(a - b) > 1e-13:
                    failures.append(f"{stem}:TIME_MISMATCH:{index}")
                scale = max(abs(a), abs(b))
                ratio = abs(a-b)/max(scale,1e-100)
                max_relative[key] = max(max_relative.get(key,0.0),ratio)
                if abs(a-b) > TOL["abs"] + TOL["rel"]*scale:
                    failures.append(f"{stem}:{key}:AB_MISMATCH:{index}")
        comparisons.append({"input_source":filename, "rows":len(first),
                            "fields":sorted(first[0]), "max_relative_error":max_relative})
    report = {
        "schema": "code4.zero_field_smoke_native_ab.v0.1",
        "source_head": expected_head,
        "binary_sha256": binary_hash,
        "scope": data["scope"],
        "comparisons": comparisons,
        "failures":sorted(set(failures)),
        "native_parity":"PASS" if not failures else "FAIL",
        "general_replacement":"NOT_APPROVED",
        "heavy_mass_correction":"NOT_EVALUATED",
        "nonzero_field":"NOT_EVALUATED",
        "code4_safe_delete":"HOLD"
    }
    (folder / "result.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("CODE4_C1_NATIVE_AB=" + report["native_parity"])
    print("CODE4_C1_SAFE_DELETE=HOLD")
    for x in report["failures"]:
        print("CODE4_C1_AB_ERROR=" + x)
    return report


def main() -> int:
    p = argparse.ArgumentParser()
    x = p.add_mutually_exclusive_group(required=True)
    x.add_argument("--prepare",action="store_true")
    x.add_argument("--analyze",action="store_true")
    p.add_argument("--output",required=True,type=Path)
    p.add_argument("--expected-head",required=True)
    p.add_argument("--binary-sha256",default="")
    a = p.parse_args()
    if a.prepare:
        prepare(a.output,a.expected_head)
        return 0
    return 0 if compare(a.output,a.expected_head,a.binary_sha256)["native_parity"]=="PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
