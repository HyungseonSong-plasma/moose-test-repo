#!/usr/bin/env python3
"""Independent source-only dual-case P4-X owner regression on real P3-X ZIP.

Usage: python3 ci/check_issue670_p4_x_owner_cutover.py --artifact <artifact14406746397.zip>
No native MOOSE execution, no private EI rate bytes, no original mutation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments/Issue402_plasma_dsl_g1/chemistry"))
from retire_s6_p4_duplicate_owners import (  # noqa: E402
    C0, BEFORE_SHA, AFTER_SHA, CutoverError,
    plan_p4_duplicate_owner_cutover, retire_p4_duplicate_owners,
)

ZIP_SHA = "592a7c82834bab841f6a2e1807db305d0eff1e953f50a0dcc6d7e21ff8820111"


def digest(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def verify(artifact: Path) -> dict:
    if digest(artifact.read_bytes()) != ZIP_SHA:
        raise CutoverError("P4X_TEST_SOURCE_ARTIFACT_SHA_CHANGED")
    result = {"source_artifact_sha256": ZIP_SHA, "cases": {}, "negative_rejected": 0,
              "native_p2": "NOT_RUN", "science": "SCIENCE_HOLD"}
    with ZipFile(artifact) as z:
        if z.testzip() is not None:
            raise CutoverError("P4X_TEST_ZIP_CRC_FAILED")
        for case in ("417", "941"):
            prefix = f"cases/{case}/experiments/Issue395_powered_chemistry_ladder/"
            ordered = [Path(name).name for name in json.loads(z.read(f"cases/{case}/ordered.json"))]
            layers = {name: z.read(prefix + name) for name in ordered}
            mechanism = json.loads(z.read(prefix + f"chemistry/unified_s6_{case}_newonly.json"))
            manifest = json.loads(z.read(f"cases/{case}/newonly_stage_receipt.json"))
            expected = manifest["layers_after_sha256"]
            if len(ordered) != 11 or any(digest(layers[n]) != expected[n] for n in ordered):
                raise CutoverError("P4X_TEST_ELEVEN_INPUT_SHA_MISMATCH")
            after, receipt = plan_p4_duplicate_owner_cutover(
                layers, ordered, mechanism, post_p3_layer_sha=expected)
            if digest(layers[C0]) != BEFORE_SHA or digest(after) != AFTER_SHA:
                raise CutoverError("P4X_TEST_C0_SHA_MISMATCH")
            with tempfile.TemporaryDirectory() as temp:
                folder = Path(temp) / "experiments" / "Issue395_powered_chemistry_ladder"
                folder.mkdir(parents=True)
                (folder / ".issue633_disposable_scratch").write_text("issue633-scratch-only\n")
                for name, blob in layers.items():
                    (folder / name).write_bytes(blob)
                report = retire_p4_duplicate_owners(
                    folder, ordered, mechanism, post_p3_layer_sha=expected)
                if report["output_c0_sha256"] != AFTER_SHA:
                    raise CutoverError("P4X_TEST_WRITE_RECEIPT_CHANGED")
                if digest((folder / C0).read_bytes()) != AFTER_SHA:
                    raise CutoverError("P4X_TEST_WRITE_READBACK_CHANGED")
                if any((folder / n).read_bytes() != layers[n] for n in ordered[1:]):
                    raise CutoverError("P4X_TEST_NON_TARGET_CHANGED")

            negatives = {}
            def rejected(label, *, layer=None, js=None, order=None, hashes=None):
                try:
                    plan_p4_duplicate_owner_cutover(
                        layer if layer is not None else layers,
                        order if order is not None else ordered,
                        js if js is not None else mechanism,
                        post_p3_layer_sha=hashes if hashes is not None else expected)
                except (CutoverError, ValueError, TypeError, KeyError):
                    negatives[label] = "REJECTED"
                    return
                raise AssertionError("P4X_NEGATIVE_WRONGLY_ACCEPTED:" + label)

            for name, original, changed in (
                ("carrier_one", b"carrier_one", b"carrier_zero"),
                ("ion_wall_missing", b"  [ion_wall_flux]", b"  [other_wall_flux]"),
                ("current_missing", b"  [cover_surface_current]", b"  [cover_surface_currenx]"),
                ("mobility", b"Om_mobility", b"Om_negmobility"),
            ):
                changed_layers = dict(layers)
                changed_layers[C0] = layers[C0].replace(original, changed, 1)
                rejected(name, layer=changed_layers)
            changed_layers = dict(layers)
            changed_layers[C0] += b"  [ion_wall_flux]\n    type = Bad\n  []\n"
            rejected("duplicate_wall", layer=changed_layers)
            changed_layers = dict(layers)
            changed_layers[ordered[1]] += b"#extra"
            rejected("non_target_tamper", layer=changed_layers)

            for label, modify in (
                ("charge", lambda j: j["species"]["Om"].__setitem__("charge_number", 1)),
                ("transport", lambda j: j["species"]["Op"]["transport_coef"].__setitem__("mobility", 11)),
                ("electron_flux", lambda j: j["ion_surface_current"].__setitem__("electron_wall_number_flux", "invalid")),
                ("missing_wafer", lambda j: j["drift_diffusion_boundaries"].pop("plasma_wafer")),
                ("missing_bc", lambda j: j["drift_diffusion_boundaries"]["plasma_cover"].pop("Om_cover_dielectric")),
                ("wrong_bc_type", lambda j: j["drift_diffusion_boundaries"]["plasma_wafer"]["O2p_wafer_dielectric"].__setitem__("type", "Bad")),
            ):
                mutated = json.loads(json.dumps(mechanism))
                modify(mutated)
                rejected(label, js=mutated)
            rejected("missing_layer", layer={k: v for k, v in layers.items() if k != ordered[1]})
            rejected("wrong_order", order=ordered[::-1])
            changed_sha = dict(expected)
            changed_sha[C0] = "0" * 64
            rejected("wrong_manifest_SHA", hashes=changed_sha)
            if len(negatives) != 15:
                raise AssertionError("P4X_NEGATIVE_COUNT_DRIFT")
            result["negative_rejected"] += len(negatives)
            result["cases"][case] = {
                "input_layer_sha256_verified": 11,
                "C0_before_sha256": BEFORE_SHA, "C0_after_sha256": AFTER_SHA,
                "non_target_layers_byte_identical": 10,
                "carrier_one_preserved": True, "old_source_materials_removed": 6,
                "negative_tests": negatives,
                "native_warehouse": "NOT_RUN",
            }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = verify(args.artifact)
    print(json.dumps(result, sort_keys=True))
    if args.report is not None:
        args.report.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
