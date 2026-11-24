#!/usr/bin/env python3
"""Reconstruct actual S6-417/941 P1 -> P2 -> P3-X -> P4-X New-only input.

Use exactly the archived P1-0 and P3-X CI ZIPs. Only disposable tempfile
Scratch is written. This is full PRODUCTION SOURCE STAGING, not Native MOOSE.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from zipfile import ZipFile
from io import BytesIO

CHEM = Path(__file__).resolve().parents[1] / "experiments/Issue402_plasma_dsl_g1/chemistry"
sys.path.insert(0, str(CHEM))
from prepare_s6_newonly import prepare_newonly  # noqa: E402

P1_OUTER_SHA = "584fd8eff989ab1f7f0a7582ae72b4dc2429f84b8b05ed91c1a46f89df88da5e"
P1_NESTED_SHA = "9923c7c875dff975ec203610e58797be7abbfe6a92be2173f1fbe525f49f1172"
P3X_SHA = "592a7c82834bab841f6a2e1807db305d0eff1e953f50a0dcc6d7e21ff8820111"
EXPECTED_C0_BEFORE = "d78a084434eca25b9ece07138c49bf93800845f5947f5ec327bfc81334daa17a"
EXPECTED_C0_AFTER = "2c3bab8a8e28b360dcd54775d91ba13c97401364c709944bc21d6bf0b6d79490"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def checked_zip(file: Path, expected_sha: str):
    data = file.read_bytes()
    if sha(data) != expected_sha:
        raise ValueError("P4X_E2E_ZIP_PIN_MISMATCH:" + file.name)
    z = ZipFile(BytesIO(data))
    if z.testzip() is not None:
        raise ValueError("P4X_E2E_ZIP_CRC_FAILED:" + file.name)
    return z


def verify(p1_outer: Path, p3x: Path) -> dict:
    cases = {}
    with checked_zip(p1_outer, P1_OUTER_SHA) as p1z, checked_zip(p3x, P3X_SHA) as p3z:
        raw_inner = p1z.read("p1_0_final_11_layer_inputs.zip")
        if sha(raw_inner) != P1_NESTED_SHA:
            raise ValueError("P4X_E2E_NESTED_SOURCE_SHA_MISMATCH")
        with ZipFile(BytesIO(raw_inner)) as p1:
            if p1.testzip() is not None:
                raise ValueError("P4X_E2E_P1_INNER_CRC_FAILED")
            for case in ("417", "941"):
                prefix = f"cases/{case}/experiments/"
                with tempfile.TemporaryDirectory() as temporary:
                    base = Path(temporary) / "experiments"
                    stage = base / "Issue395_powered_chemistry_ladder"
                    stage.mkdir(parents=True)
                    (stage / ".issue633_disposable_scratch").write_text("issue633-scratch-only\n")
                    ordered = json.loads(p3z.read(f"cases/{case}/ordered.json"))
                    manifest = json.loads(p3z.read(f"cases/{case}/case_manifest.json"))
                    receipt = json.loads(p3z.read(f"cases/{case}/newonly_stage_receipt.json"))
                    if len(ordered) != 11 or len(set(ordered)) != 11:
                        raise ValueError("P4X_E2E_ORDERED_ELEVEN_INVALID")
                    before = {}
                    for item in ordered:
                        name = Path(item).name
                        blob = p1.read(case + "/" + name)
                        (stage / name).write_bytes(blob)
                        before[name] = sha(blob)
                    if set(before) != set(receipt["layers_before_sha256"]) or any(
                        before[name] != receipt["layers_before_sha256"][name] for name in before
                    ):
                        raise ValueError("P4X_E2E_P1_INPUT_FILE_SHA_MISMATCH")

                    auxiliary = (
                        "Issue395_powered_chemistry_ladder/rf_elastic_multiapp_maxwell_400w_100us_dt1000ns_child.i",
                        "Issue395_powered_chemistry_ladder/issue397_maxwell_steady_abs1e11.i",
                        "Issue395_powered_chemistry_ladder/rf_elastic_multiapp_maxwell_400w_100us_dt1000ns_overlay.i",
                        "Issue18_qvt_plasma_mapping/qvt.msh",
                        "Issue91_real_qvt_r3/r3_e0/electron_moments.txt",
                    )
                    for rel in auxiliary:
                        dest = base / rel
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        dest.write_bytes(p3z.read(prefix + rel))
                    electron = base / "Issue91_real_qvt_r3/r3_e0/electron_moments.txt"
                    result = prepare_newonly(stage, ordered, case, manifest, electron)

                    if result["p4_x_duplicate_producers"]["output_c0_sha256"] != EXPECTED_C0_AFTER:
                        raise ValueError("P4X_E2E_OWNER_C0_RECEIPT_MISMATCH")
                    if result["p4_x_duplicate_producers"]["input_c0_sha256"] != EXPECTED_C0_BEFORE:
                        raise ValueError("P4X_E2E_P3X_C0_RECEIPT_MISMATCH")
                    changed = [Path(x).name for x in ordered]
                    actual = {name: sha((stage / name).read_bytes()) for name in changed}
                    expected = dict(receipt["layers_after_sha256"])
                    if expected[list(expected)[0]] is None:
                        raise ValueError("P4X_E2E_BAD_EXPECTED_MANIFEST")
                    c0 = changed[0]
                    if expected[c0] != EXPECTED_C0_BEFORE:
                        raise ValueError("P4X_E2E_STALE_SOURCE_MANIFEST")
                    expected[c0] = EXPECTED_C0_AFTER
                    if actual != expected:
                        raise ValueError("P4X_E2E_FINAL_11_LAYER_SHA_MISMATCH")
                    if result["retired_native_ion_owners"] != 26 or result["p3_x_electron"]["removed_native_electron_owners"] != 10:
                        raise ValueError("P4X_E2E_P2_P3_CUTOVER_CHANGED")
                    if result["p4_x_duplicate_producers"]["retired_source_materials"] != 6:
                        raise ValueError("P4X_E2E_SIX_OWNER_RETIREMENT_MISSING")
                    jsfile = stage / "chemistry" / f"unified_s6_{case}_newonly.json"
                    original_json = p3z.read(prefix + f"Issue395_powered_chemistry_ladder/chemistry/unified_s6_{case}_newonly.json")
                    if jsfile.read_bytes() != original_json:
                        raise ValueError("P4X_E2E_JSON_DIFF")
                    for name in changed[1:]:
                        if actual[name] != receipt["layers_after_sha256"][name]:
                            raise ValueError("P4X_E2E_NON_C0_LAYER_CHANGED:" + name)
                    cases[case] = {
                        "original_P1_layer_SHA_count": 11,
                        "newonly_P4X_layer_SHA_count": 11,
                        "C0_from_P3_X": EXPECTED_C0_BEFORE,
                        "C0_post_P4_X": EXPECTED_C0_AFTER,
                        "remaining_original_ion_owners": 0,
                        "retired_original_ion_objects": 26,
                        "retired_original_electron_objects": 10,
                        "retired_duplicate_functor_materials": 6,
                        "carrier_one_retained": True,
                        "untouched_other_input_layers": 10,
                        "json_byte_identical": True,
                        "native_p2": "NOT_RUN",
                    }
    return {"schema": "issue670.p4x.production_source_end_to_end.v1",
            "original_P1_artifact_outer_sha256": P1_OUTER_SHA,
            "original_P1_nested_inputs_sha256": P1_NESTED_SHA,
            "P3_X_artifact_sha256": P3X_SHA,
            "cases": cases, "status": "PASS_SOURCE_ONLY_417_941_NO_NATIVE_RUNTIME",
            "science": "SCIENCE_HOLD"}


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--p1-outer", type=Path, required=True)
    cli.add_argument("--p3x-artifact", type=Path, required=True)
    cli.add_argument("--report", type=Path)
    args = cli.parse_args()
    output = verify(args.p1_outer, args.p3x_artifact)
    if args.report:
        args.report.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps(output, sort_keys=True))
