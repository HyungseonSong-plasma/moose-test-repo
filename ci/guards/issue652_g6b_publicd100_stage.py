#!/usr/bin/env python3
"""#652 G6-B: strict Public D 100-row staging for G5 New-only Poisson.

Only replace the PUBLIC electron-transport lookup in marked disposable G5
Scratch. Preserve G5 Poisson/charge owners, JSON, C0, the 11 input layers,
time grid, archive and protected EI rates byte-for-byte. This preflight is NOT
a Native execution or a whole-time scientific-parity verdict.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
import sys
sys.path.insert(0, str(ROOT / "experiments/Issue402_plasma_dsl_g1/chemistry"))
from retire_s6_p4_duplicate_owners import C0  # canonical 11-layer Chemistry C0

CASES = ("417", "941")
OLD_42_SHA256 = "35534a522fa48ccb5222339c5040040630eef31e623e1c53f1e1c4540d2d653b"
PUBLIC_D_100_SHA256 = "994f6b1deece3c53be7fb3e7f9526555d0f9314fd58749bea6346639f08aa387"
SOURCE_100 = ROOT / "physics_app/database/electron_moments.txt"
TABLE_RELATIVE = Path("experiments/Issue91_real_qvt_r3/r3_e0/electron_moments.txt")
CHEM_RELATIVE = Path("experiments/Issue395_powered_chemistry_ladder")


class PublicD100Hold(ValueError):
    pass


def sha(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def checked_bytes(path: Path, expected: str, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise PublicD100Hold("G6B_MISSING_OR_SYMLINK_" + label)
    blob = path.read_bytes()
    if sha(blob) != expected:
        raise PublicD100Hold("G6B_SHA_MISMATCH_" + label)
    return blob


def lookup_contract(blob: bytes, expected_rows: int) -> dict:
    try:
        rows = blob.decode("utf-8").splitlines()
        triples = [[float(x) for x in row.split()] for row in rows]
    except (UnicodeError, ValueError) as exc:
        raise PublicD100Hold("G6B_LOOKUP_NOT_NUMERIC") from exc
    if len(triples) != expected_rows or any(len(x) != 3 for x in triples):
        raise PublicD100Hold("G6B_LOOKUP_CARDINALITY_OR_COLUMNS")
    if any(not all(math.isfinite(y) and y > 0 for y in x) for x in triples):
        raise PublicD100Hold("G6B_LOOKUP_NONPOSITIVE_OR_NONFINITE")
    if any(y[0] <= x[0] for x, y in zip(triples, triples[1:])):
        raise PublicD100Hold("G6B_LOOKUP_ENERGY_NOT_STRICTLY_INCREASING")
    if expected_rows == 100 and (triples[0][0] != 1.40991 or triples[-1][0] != 22.1378):
        raise PublicD100Hold("G6B_ORIGINAL100_ENDPOINT_DRIFT")
    return {"rows": expected_rows, "columns": 3, "sha256": sha(blob)}


def time_contract(c0: bytes) -> dict:
    try:
        source = c0.decode("utf-8")
        matches = re.findall(r"(?m)^    time_sequence = '([^'\n]+)'$", source)
        if len(matches) != 1:
            raise PublicD100Hold("G6B_EXACT_ONE_TIME_SEQUENCE_REQUIRED")
        times = [float(x) for x in matches[0].split()]
    except (UnicodeError, ValueError) as exc:
        raise PublicD100Hold("G6B_TIME_SEQUENCE_UNREADABLE") from exc
    if (len(times) != 461 or abs(times[0]) > 1e-18 or
            abs(times[-1] - 1e-4) > 1e-15 or
            not all(math.isfinite(t) for t in times)):
        raise PublicD100Hold("G6B_100US_TIME_ENDPOINT_OR_ROWS")
    dt = [b - a for a, b in zip(times, times[1:])]
    if len(dt) != 460 or not all(x > 0 for x in dt):
        raise PublicD100Hold("G6B_NONMONOTONIC_TIME_GRID")
    expected = ((1e-9, 100, 2e-16), (1e-8, 190, 2e-15),
                (1e-7, 80, 2e-14), (1e-6, 90, 2e-13))
    for step, count, tolerance in expected:
        if sum(abs(x - step) < tolerance for x in dt) != count:
            raise PublicD100Hold("G6B_TIME_CADENCE_DRIFT")
    required = ("  scheme = implicit-euler", "  end_time = 1e-4",
                "    type = TimeSequenceStepper", "  checkpoint = true")
    if any(source.count(token + "\n") != 1 for token in required):
        raise PublicD100Hold("G6B_EXECUTIONER_CONTRACT_DRIFT")
    return {"end_time_seconds": 1e-4, "time_points": 461,
            "intervals": 460, "dt_counts": {"1ns": 100, "10ns": 190,
                                           "100ns": 80, "1000ns": 90},
            "scheme": "implicit-euler", "checkpoint": True}


def preflight_case(stage: Path, receipt: dict, case: str, public_blob: bytes) -> dict:
    root = stage / "scratch" / case
    chem = root / CHEM_RELATIVE
    marker = chem / ".issue633_disposable_scratch"
    if (not chem.is_dir() or chem.is_symlink() or marker.is_symlink() or
            not marker.is_file() or marker.read_text().strip() != "issue633-scratch-only"):
        raise PublicD100Hold("G6B_DISPOSABLE_G5_MARKER_REQUIRED")
    entry = receipt["cases"][case]
    ordered = [Path(n).name for n in entry["ordered"]]
    expected = entry["layer_sha256"]
    if (len(ordered) != 11 or len(set(ordered)) != 11 or ordered[0] != C0 or
            ordered[-1] != "migrated_continuity.i" or set(expected) != set(ordered)):
        raise PublicD100Hold("G6B_EXACT_G5_11_LAYER_ORDER_REQUIRED")
    pinned = {name: sha(checked_bytes(chem / name, expected[name], name))
              for name in ordered}
    if pinned != expected:
        raise PublicD100Hold("G6B_G5_LAYER_RECEIPT_DRIFT")
    from prepare_s6_newonly import JSON_SHA  # pylint: disable=import-outside-toplevel
    from retire_s6_poisson_charge_owners import G5_OUTPUT_C0_SHA, G5_OVERLAY_SHA
    if (expected[C0] != G5_OUTPUT_C0_SHA or
            expected["migrated_continuity.i"] != G5_OVERLAY_SHA[case]):
        raise PublicD100Hold("G6B_G5_ORIGINAL_POISSON_OWNER_SHA_CHANGED")
    mechanism_path = chem / "chemistry" / ("unified_s6_" + case + "_newonly.json")
    mechanism_blob = checked_bytes(mechanism_path, JSON_SHA[case], "G5_MECHANISM")
    mechanism = json.loads(mechanism_blob)
    if (set(mechanism) != {"species", "equations", "reactions",
                           "ion_surface_current", "drift_diffusion_boundaries", "poisson"}
            or mechanism["species"]["e"]["transport_coef"] != {
                "type": "lookup", "file": "../../Issue91_real_qvt_r3/r3_e0/electron_moments.txt",
                "unit": "reduced", "bounds_policy": "clamp"}):
        raise PublicD100Hold("G6B_EXPECT_G5_POISSON_JSON_AND_UNCHANGED_ELECTRON_BINDING")
    table = root / TABLE_RELATIVE
    resolved = (mechanism_path.parent / mechanism["species"]["e"]["transport_coef"]["file"]).resolve()
    if resolved != table.resolve() or resolved == SOURCE_100.resolve():
        raise PublicD100Hold("G6B_RELATIVE_LOOKUP_BINDING_MISMATCH")
    old_blob = checked_bytes(table, OLD_42_SHA256, "G5_42ROW_LOOKUP")
    lookup_contract(old_blob, 42)
    lookup_contract(public_blob, 100)
    grid = time_contract((chem / C0).read_bytes())
    return {"case": case, "table": table, "old_blob": old_blob,
            "layers": pinned, "mechanism_sha256": sha(mechanism_blob),
            "time": grid}


def stage_public_d_100(stage: Path, receipt: dict, source: Path = SOURCE_100) -> dict:
    source_sha = subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    if receipt.get("source_sha") != source_sha or set(receipt.get("cases", {})) != set(CASES):
        raise PublicD100Hold("G6B_EXACT_G5_STAGE_SOURCE_IDENTITY_MISMATCH")
    public_blob = checked_bytes(source, PUBLIC_D_100_SHA256, "ORIGINAL_PUBLICD_100ROW")
    lookup_contract(public_blob, 100)
    checks = {case: preflight_case(stage, receipt, case, public_blob) for case in CASES}
    # Every preflight completes before the first disposable mutation.
    mutated = []
    try:
        for case in CASES:
            table = checks[case]["table"]
            table.write_bytes(public_blob)
            mutated.append(case)
            if sha(table.read_bytes()) != PUBLIC_D_100_SHA256:
                raise PublicD100Hold("G6B_TABLE_READBACK_FAILED")
        for case in CASES:
            check = checks[case]
            chem = stage / "scratch" / case / CHEM_RELATIVE
            if ({name: sha((chem / name).read_bytes()) for name in check["layers"]}
                    != check["layers"]):
                raise PublicD100Hold("G6B_UNEXPECTED_NON_LOOKUP_LAYER_EDIT")
            if sha((chem / "chemistry" / ("unified_s6_" + case + "_newonly.json")).read_bytes()) != check["mechanism_sha256"]:
                raise PublicD100Hold("G6B_UNEXPECTED_JSON_EDIT")
    except Exception:
        for case in reversed(mutated):
            checks[case]["table"].write_bytes(checks[case]["old_blob"])
        raise
    return {"schema": "issue652.g6b.publicd100.stage.v1",
            "source_sha": source_sha, "original_publicd_lookup_sha256": PUBLIC_D_100_SHA256,
            "lookup_rows": 100, "cases": {
                case: {"prior_g5_lookup_sha256": OLD_42_SHA256,
                       "new_lookup_sha256": PUBLIC_D_100_SHA256,
                       "unchanged_11_layer_sha256": checks[case]["layers"],
                       "unchanged_poisson_json_sha256": checks[case]["mechanism_sha256"],
                       "time": checks[case]["time"],
                       "P0": "PASS_SCRATCH_ONLY_100ROW_PROVENANCE",
                       "P2": "NOT_RUN", "P3_100us": "NOT_RUN",
                       "fieldwise_parity": "UNPROVEN", "science": "SCIENCE_HOLD"}
                for case in CASES},
            "protected_rate_data_in_receipt": False, "main_merge": "NOT_AUTHORIZED"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--staged", type=Path, required=True)
    ap.add_argument("--g5-receipt", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    if args.output.exists() or args.output.is_symlink():
        raise PublicD100Hold("G6B_REFUSE_RECEIPT_OVERWRITE")
    result = stage_public_d_100(args.staged, json.loads(args.g5_receipt.read_text()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print("G6B_PUBLICD_ORIGINAL100_SCRATCH_STAGE_PASS 417 941; P3_NOT_RUN SCIENCE_HOLD")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
