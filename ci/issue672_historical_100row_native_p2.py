#!/usr/bin/env python3
"""Actual historical source P1/P2 with original 100-row electron lookup preserved.

Caller has pinned two independent checkouts:
  /work/control      PR #578 exact candidate source
  /work/historical   pinned original 400W historical source + mesh
Only those checkouts' disposable generated files and TemporaryDirectory Scratch
are used. The historical electron_moments.txt is NEVER replaced with the
42-row Public P2 test alternative. Source and binary remain separately pinned.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

CONTROL_SHA = "1efdd922096df10239cff8adc132e8f3811c1a63"
HISTORY_SHA = "29d1acc6ef7969908b86719e4b95c73a1565136d"
ORIGINAL_SHA = "994f6b1deece3c53be7fb3e7f9526555d0f9314fd58749bea6346639f08aa387"
ALTERNATE_SHA = "35534a522fa48ccb5222339c5040040630eef31e623e1c53f1e1c4540d2d653b"
ORIGINAL = "experiments/Issue91_real_qvt_r3/r3_e0/electron_moments.txt"
ALTERNATE = ".github/oxygen25_eedf/initial_mixture_23xsec_transport.txt"
OCI = ("ghcr.io/hyungseonsong-plasma/physics-build-base@"
       "sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008")


def digest(file: Path) -> str:
    h = hashlib.sha256()
    with file.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def head(path: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()


def lookup(path: Path, expected: str, count: int) -> dict:
    actual = digest(path)
    rows = [line for line in path.read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")]
    if actual != expected or len(rows) != count:
        raise ValueError(
            f"LOOKUP_IMMUTABILITY_FAILED:{path.name}:SHA={actual}:ROWS={len(rows)}")
    parts = [line.split() for line in rows]
    if any(len(x) != 3 for x in parts):
        raise ValueError("LOOKUP_THREE_COLUMNS_REQUIRED")
    return {"sha256": actual, "rows": len(rows),
            "first_mean_eV": parts[0][0], "last_mean_eV": parts[-1][0]}


def run(control: Path, historical: Path, out: Path):
    control, historical = control.resolve(), historical.resolve()
    out.mkdir(parents=True, exist_ok=True)
    receipt = {
        "schema": "issue672.historical100.native_P2_real.v1",
        "control_PR578_sha": CONTROL_SHA,
        "historical_source_sha": HISTORY_SHA,
        "source_mode": "HISTORICAL_EXACT_CANDIDATE__ORIGINAL_100ROW",
        "data_authority": "UNMODIFIED_HISTORICAL_100_ROW",
        "42row_science_validity": "SEPARATE_USER_CONFIRMED_PHYSICAL_USE_NOT_NUMERIC_IDENTICAL",
        "cases": {},
        "P3": "NOT_RUN", "P4": "NOT_RUN", "science": "SCIENCE_HOLD",
    }
    (out / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    if head(control) != CONTROL_SHA or head(historical) != HISTORY_SHA:
        raise ValueError("CONTROL_OR_HISTORY_SOURCE_HEAD_MISMATCH")
    reference = historical / ORIGINAL
    alternate = historical / ALTERNATE
    receipt["original_100row_pre"] = lookup(reference, ORIGINAL_SHA, 100)
    receipt["alternate_42row_untouched"] = lookup(alternate, ALTERNATE_SHA, 42)
    if reference.samefile(alternate):
        raise ValueError("ORIGINAL_AND_ALTERNATE_ARE_HARDLINKED")
    mesh = historical / "experiments/Issue395_powered_chemistry_ladder/baseline_plasma_plus_unstructured_cover_plus_wafer.msh"
    if not mesh.is_file() or not mesh.stat().st_size:
        raise ValueError("HISTORICAL_PARENT_MESH_MISSING")
    receipt["real_parent_mesh_sha256"] = digest(mesh)

    pilot = control / "experiments/Issue402_plasma_dsl_g1"
    app = control / "physics_app/physics-opt"
    evidence = pilot / "evidence"
    binary_receipt = evidence / "native_p1_identity.json"
    if not app.is_file() or not binary_receipt.is_file():
        raise ValueError("SOURCE_MATCHED_PHYSICS_BINARY_P1_NOT_PRESENT")
    binary = json.loads(binary_receipt.read_text())
    if (binary.get("source_sha") != CONTROL_SHA or binary.get("oci_image") != OCI
            or binary.get("binary_sha256") != digest(app)
            or binary.get("build_log_sha256") != digest(evidence / "native_build.log")
            or binary.get("P1") != "PASS"):
        raise ValueError("HISTORICAL_100ROW_BINARY_PROVENANCE_MISMATCH")
    receipt["binary_sha256_independently_rehashed"] = digest(app)
    receipt["binary_build_source"] = CONTROL_SHA

    importer = importlib.util.spec_from_file_location("historical_public_option", pilot / "public_option_s6_p2.py")
    if importer is None or importer.loader is None:
        raise ValueError("HISTORICAL_PUBLIC_DRIVER_IMPORT_FAILED")
    obj = importlib.util.module_from_spec(importer)
    importer.loader.exec_module(obj)
    if obj.HISTORICAL_SHA != HISTORY_SHA:
        raise ValueError("HISTORICAL_SOURCE_PIN_CHANGED")
    original_stage = obj.p2.stage
    custody: dict[str, dict] = {}

    def pinned_stage(control_arg, hist_arg, case, variant, folder, manifest, **kw):
        # Do not change the algorithm or any input bytes: wrap only its readback.
        if Path(hist_arg).resolve() != historical:
            raise ValueError("STAGED_FROM_DIFFERENT_HISTORY")
        if lookup(reference, ORIGINAL_SHA, 100)["sha256"] != ORIGINAL_SHA:
            raise ValueError("HISTORICAL_LOOKUP_CHANGED_DURING_STAGING")
        ordered = original_stage(control_arg, hist_arg, case, variant, folder, manifest, **kw)
        stage = Path(folder) / ORIGINAL
        observed = lookup(stage, ORIGINAL_SHA, 100)
        if lookup(Path(folder) / ALTERNATE, ALTERNATE_SHA, 42)["sha256"] != ALTERNATE_SHA:
            raise ValueError("ALTERNATE_LOOKUP_CHANGED_IN_STAGE")
        key = str(case) + "_" + ("B" if variant == "B" else "D")
        custody[key] = {"table": observed, "input_layer_count": len(ordered),
                        "staged_original_100row_path": ORIGINAL,
                        "original_Historical_checkout_sha256": digest(reference)}
        return ordered

    obj.p2.stage = pinned_stage
    try:
        result = obj.execute(historical, app, CONTROL_SHA, evidence, timeout_seconds=900)
        receipt["historical_runner_status"] = result.get("status")
        receipt["historical_runner_p2"] = result.get("P2")
        receipt["historical_runner_cleanup"] = result.get("cleanup")
        receipt["historical_driver_receipt_sha256"] = digest(evidence / "issue402_option_s6_p2_status.json")
        for case in ("417", "941"):
            for variant in ("B", "D"):
                key = case + "_" + variant
                meta = result.get("checks", {}).get(case, {}).get(variant, {})
                entry = dict(custody.get(key, {}))
                log = evidence / f"S6_{key}_P2.log"
                entry.update({
                    "P2": meta.get("P2", "NOT_RUN"),
                    "exit_code": meta.get("exit_code"),
                    "classification": meta.get("classification", "UNKNOWN"),
                    "syntax_ok": meta.get("syntax_ok", False),
                    "log_sha256": digest(log) if log.is_file() else None,
                    "native_log_sha_consistency": (log.is_file() and
                      digest(log) == meta.get("log_sha256")),
                    "error": meta.get("error", meta.get("blocker")),
                })
                receipt["cases"][key] = entry
    finally:
        # Check immutable authority, even if one Native case or scratch cleanup fails.
        receipt["original_100row_post"] = lookup(reference, ORIGINAL_SHA, 100)
        receipt["alternate_42row_post"] = lookup(alternate, ALTERNATE_SHA, 42)
        receipt["original_100row_unchanged"] = (
            receipt["original_100row_pre"] == receipt["original_100row_post"])
        receipt["historical_100row_cases_verified"] = sum(
            1 for value in custody.values()
            if value["table"]["sha256"] == ORIGINAL_SHA)
        receipt["historical_four_way_real_p2"] = (
            len(receipt["cases"]) == 4
            and all(value["P2"] == "PASS"
                    and value["exit_code"] == 0
                    and value["syntax_ok"]
                    and value["native_log_sha_consistency"]
                    and value.get("table", {}).get("sha256") == ORIGINAL_SHA
                    for value in receipt["cases"].values()))
        receipt["P2"] = "PASS_HISTORICAL_100ROW_ONLY" if receipt["historical_four_way_real_p2"] else "HOLD"
        receipt["never_promote_to_newonly_P05"] = True
        (out / "receipt.json").write_text(
            json.dumps(receipt, sort_keys=True, indent=2) + "\n")
    return receipt


if __name__ == "__main__":
    args = argparse.ArgumentParser()
    args.add_argument("--control", required=True, type=Path)
    args.add_argument("--historical", required=True, type=Path)
    args.add_argument("--out", required=True, type=Path)
    a = args.parse_args()
    try:
        d = run(a.control, a.historical, a.out)
    except Exception as exc:
        path = a.out / "receipt.json"
        if path.is_file():
            data = json.loads(path.read_text())
            data["fatal_error"] = type(exc).__name__ + ":" + str(exc)[:500]
            data["P2"] = "HOLD"
            path.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n")
        raise
    print(json.dumps({"P2": d.get("P2"),
                      "cases": d["cases"],
                      "original_100row_unchanged": d["original_100row_unchanged"]},
                     sort_keys=True))
    if d["P2"] != "PASS_HISTORICAL_100ROW_ONLY":
        raise SystemExit("HISTORICAL_100ROW_P2_NOT_FOUR_WAY_PASS")
