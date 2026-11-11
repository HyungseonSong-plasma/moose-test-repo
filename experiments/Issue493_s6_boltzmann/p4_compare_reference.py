#!/usr/bin/env python3
"""P4: independently compare retained B and newly computed C to public reference.

This is NOT a B/C numerical-equivalence gate. Compare each archived arm with
the same versioned 400 W reference; retain scientific HOLD without approved
reference acceptance tolerances. No solver is launched by this script.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from compare_native_reference import analyze as compare_to_reference, sha256
from p4_compare_public_bc import CASES, load_arm

SOURCE = "29d1acc6ef7969908b86719e4b95c73a1565136d"
CANDIDATE = "bebaf47a33ff5ee1d6b933d9691bf48f5ec0f947"
OCI = ("ghcr.io/hyungseonsong-plasma/physics-build-base@"
       "sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008")
B_RUN = 42925621978
C_HANDOFF_RUN = 42992475581
C_HANDOFF_HEAD = "f5880e27ea32facdf4c6a4486c482ea242ce415c"
C_BINARY_SHA = {
    "417": "dc23d693ecdaf4dbf4ce86e0bd104e254e82bfb7d78761b650c8030a138c5058",
    "941": "12e4cfd750d4cb66a959d30691baa27c116d447c5de1388cf9810df72d04dc01",
}


def provenance(case: str, arm: str, manifest: dict) -> None:
    if (manifest.get("source_sha") != SOURCE
            or manifest.get("candidate_sha") != CANDIDATE
            or manifest.get("oci_image") != OCI
            or not isinstance(manifest.get("mesh_sha256"), str)
            or len(manifest["mesh_sha256"]) != 64):
        raise ValueError(f"REFERENCE_P4_PROVENANCE_MISMATCH_{case}_{arm}")
    if arm == "C" and manifest.get("p1_binary_sha256") != C_BINARY_SHA[case]:
        raise ValueError(f"REFERENCE_P4_C_HANDOFF_BINARY_MISMATCH_{case}")


def ratio_or_none(current: float, baseline: float) -> float | None:
    return current / baseline if baseline > 0 else None


def analyze(*, artifacts_root: Path, reference_root: Path,
            output: Path, time_us: float = 100.0) -> dict:
    if output.exists():
        raise ValueError("REFERENCE_P4_OUTPUT_EXISTS")
    ref_vertical = reference_root / "reference_vertical.csv"
    ref_horizontal = reference_root / "reference_horizontal.csv"
    if not ref_vertical.is_file() or not ref_horizontal.is_file():
        raise ValueError("REFERENCE_P4_INPUTS_MISSING")

    # Validate every B/C arm and every SHA before generating any comparisons.
    files: dict[tuple[str, str], tuple[dict, dict]] = {}
    for case in CASES:
        for arm in ("B", "C"):
            manifest, inputs = load_arm(artifacts_root, case, arm)
            provenance(case, arm, manifest)
            files[(case, arm)] = manifest, inputs
        # The physical mesh must agree across the same source/candidate.
        # The executable SHA is *not* an equivalence requirement against a
        # common external reference; record it separately for traceability.
        if files[(case, "B")][0]["mesh_sha256"] != files[(case, "C")][0]["mesh_sha256"]:
            raise ValueError(f"REFERENCE_P4_MESH_MISMATCH_{case}")

    report = {
        "schema": "issue493_public_reference_p4_v1",
        "method": "B_AND_C_EACH_AGAINST_PUBLIC_REFERENCE",
        "not_performed": "B_VS_C_EXODUS_FIELD_EQUIVALENCE",
        "reference_time": "UNKNOWN",
        "native_time_us": time_us,
        "reference_sha256": {
            "vertical": sha256(ref_vertical),
            "horizontal": sha256(ref_horizontal),
        },
        "source_B_run_id": B_RUN,
        "source_C_binary_handoff_run_id": C_HANDOFF_RUN,
        "source_C_binary_handoff_commit": C_HANDOFF_HEAD,
        "P4_MEASUREMENTS": "PASS_IF_ALL_FOUR_ARMS_HASH_VERIFIED_AND_INTERPOLATED",
        "REFERENCE_NUMERICAL_EQUIVALENCE": "HOLD_NO_APPROVED_ACCEPTANCE_TOLERANCES",
        "science": "SCIENCE_HOLD",
        "cases": {},
    }
    output.mkdir(parents=True, mode=0o700)
    for case in CASES:
        summaries = {}
        for arm in ("B", "C"):
            manifest, inputs = files[(case, arm)]
            comparison = compare_to_reference(
                exodus=inputs["exodus"], csv_file=inputs["csv"],
                manifest_file=artifacts_root / f"issue493-public-{case}-{arm}-results" / "manifest.json",
                vertical_reference=ref_vertical, horizontal_reference=ref_horizontal,
                output=output / f"S6-{case}-{arm}", label=f"S6-{case}/{arm}",
                time_us=time_us,
            )
            summaries[arm] = comparison
        report["cases"][case] = {
            "B_binary_sha256": files[(case, "B")][0]["p1_binary_sha256"],
            "C_binary_sha256": files[(case, "C")][0]["p1_binary_sha256"],
            "B_comparison": summaries["B"],
            "C_comparison": summaries["C"],
            "C_over_B_vertical_reference_rmse": ratio_or_none(
                summaries["C"]["vertical"]["rmse_over_reference_peak"],
                summaries["B"]["vertical"]["rmse_over_reference_peak"]),
            "C_over_B_horizontal_reference_rmse": ratio_or_none(
                summaries["C"]["horizontal"]["rmse_over_reference_peak"],
                summaries["B"]["horizontal"]["rmse_over_reference_peak"]),
            "comparison_basis": "COMMON_EXTERNAL_REFERENCE_NOT_B_C_IDENTITY",
        }
    (output / "p4_reference_metrics.json").write_text(
        json.dumps(report, sort_keys=True, indent=2) + "\n")
    return report


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--artifacts-root", type=Path, required=True)
    p.add_argument("--reference-root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--time-us", type=float, default=100.0)
    args = p.parse_args()
    try:
        summary = analyze(artifacts_root=args.artifacts_root,
                          reference_root=args.reference_root, output=args.output,
                          time_us=args.time_us)
    except (ValueError, OSError, KeyError, TypeError, ImportError, RuntimeError) as exc:
        print("ISSUE493_REFERENCE_P4_HOLD", type(exc).__name__, str(exc)[:180],
              file=sys.stderr)
        return 2
    print(json.dumps({"event": "ISSUE493_REFERENCE_P4_MEASURED",
                      "cases": list(summary["cases"]),
                      "equivalence": summary["REFERENCE_NUMERICAL_EQUIVALENCE"],
                      "science": summary["science"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
