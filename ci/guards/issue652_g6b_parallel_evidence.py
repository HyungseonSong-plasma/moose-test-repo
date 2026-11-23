#!/usr/bin/env python3
"""Independent G6-B 417/941 Native 3ns evidence for branch-only matrix runs.

Neither a zero exit code nor this summary approves full 100us or scientific
parity. Never accepts unredacted rates, traces, logs or private staging.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys

CASES = ("417", "941")
SOURCE_100_SHA = "994f6b1deece3c53be7fb3e7f9526555d0f9314fd58749bea6346639f08aa387"
OCI = ("ghcr.io/hyungseonsong-plasma/physics-build-base@"
       "sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008")
SHA40 = re.compile("[0-9a-f]{40}\\Z")
SHA64 = re.compile("[0-9a-f]{64}\\Z")


class ParallelEvidenceHold(ValueError):
    pass


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ParallelEvidenceHold("MISSING_OR_SYMLINK_RECEIPT")
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ParallelEvidenceHold("UNREADABLE_RECEIPT") from exc
    if not isinstance(result, dict):
        raise ParallelEvidenceHold("RECEIPT_NOT_OBJECT")
    return result


def verify_bundle(manifest: Path, source_sha: str) -> dict:
    if not SHA40.fullmatch(source_sha):
        raise ParallelEvidenceHold("EXPECTED_SOURCE_SHA_INVALID")
    value = load(manifest)
    if (value.get("schema_version") != 1 or value.get("source_sha") != source_sha
            or value.get("oci_ref") != OCI or
            set(value.get("files", {})) != {
                "physics_app/physics-opt",
                "physics_app/g6_owner_tracer.so",
                "physics_app/lib/libphysics-opt.so.0",
                "physics_app/test/lib/libphysics_test-opt.so.0",
            } or
            any(not isinstance(digest, str) or not SHA64.fullmatch(digest)
                for digest in value["files"].values())):
        raise ParallelEvidenceHold("P1_EXACT_BINARY_MANIFEST_INVALID")
    return value


def validate_case(public: dict, native: dict, manifest: dict,
                  case: str, expected_source: str) -> dict:
    if case not in CASES or not SHA40.fullmatch(expected_source):
        raise ParallelEvidenceHold("UNAPPROVED_CASE_OR_SOURCE")
    if (public.get("schema") != "issue652.g6b.publicd100.stage.v1"
            or public.get("source_sha") != expected_source
            or public.get("original_publicd_lookup_sha256") != SOURCE_100_SHA
            or public.get("lookup_rows") != 100
            or public.get("protected_rate_data_in_receipt") is not False
            or set(public.get("cases", {})) != set(CASES)):
        raise ParallelEvidenceHold("PUBLIC_D100_P0_PROVENANCE")
    public_case = public["cases"][case]
    grid = public_case.get("time", {})
    if (public_case.get("new_lookup_sha256") != SOURCE_100_SHA
            or public_case.get("P0") != "PASS_SCRATCH_ONLY_100ROW_PROVENANCE"
            or public_case.get("science") != "SCIENCE_HOLD"
            or public_case.get("P3_100us") != "NOT_RUN"
            or len(public_case.get("unchanged_11_layer_sha256", {})) != 11
            or grid.get("time_points") != 461
            or grid.get("intervals") != 460
            or grid.get("end_time_seconds") != 1e-4):
        raise ParallelEvidenceHold("CASE_PUBLIC100_OR_100US_GRID_DRIFT")
    if (native.get("schema") != "issue652.g6.registration_p3.v1"
            or native.get("source_sha") != expected_source
            or native.get("oci") != OCI
            or native.get("binary_sha256") != manifest["files"]["physics_app/physics-opt"]
            or native.get("observer_sha256") != manifest["files"]["physics_app/g6_owner_tracer.so"]
            or native.get("raw_private_rates_in_artifact") is not False
            or native.get("science") != "SCIENCE_HOLD"
            or native.get("P4_100us") != "NOT_RUN"
            or native.get("registration") != "PASS_TYPED_15_OWNERS"
            or native.get("P3_3ns") != "PASS_FINITE_3NS_NO_BASELINE_PARITY"
            or set(native.get("cases", {})) != {case}):
        raise ParallelEvidenceHold("NATIVE_CASE_IDENTITY_OR_SCOPE")
    case_result = native["cases"][case]
    reg = case_result.get("registration")
    p3 = case_result.get("P3_3ns")
    if (not isinstance(reg, dict) or reg.get("status") != "EXPECTED_15_GENERATED_OWNERS_TRACE_PASS"
            or len(reg.get("observed_expected_owners", {})) != 15
            or case_result.get("P2_syntax_ok") is not True
            or case_result.get("P2_trace_return_code") != 0
            or case_result.get("P3_return_code") != 0
            or not isinstance(p3, dict) or p3.get("status") != "SHORT_3NS_POSTPROCESSORS_FINITE"
            or type(p3.get("time_rows")) is not int or p3["time_rows"] < 4
            or not isinstance(p3.get("final_seconds"), (float, int))
            or not math.isfinite(p3["final_seconds"])
            or abs(p3["final_seconds"] - 3e-9) > 1e-12
            or p3.get("baseline_semantic_parity") != "NOT_EVALUATED"
            or p3.get("charge_conservation_residual") != "NOT_MEASURED"):
        raise ParallelEvidenceHold("NATIVE_P2_OR_3NS_EVIDENCE_NOT_COMPLETE")
    return {
        "schema_version": 1, "case_id": case, "source_sha": expected_source,
        "oci_ref": OCI, "build_manifest_sha256": None,
        "execution_status": "EXIT_ZERO_UNVERIFIED", "exit_code": 0,
        "end_time_s_contract": 3e-9, "intervals_contract": 3,
        "solver_time_coverage_verified": False, "scientific_status": "HOLD",
        "native_3ns_time_rows": p3["time_rows"],
        "native_3ns_final_seconds": p3["final_seconds"],
        "public_100us_intervals": 460, "P4_100us": "NOT_RUN",
    }


def make_case_receipt(*, public_path: Path, native_path: Path, manifest_path: Path,
                      case: str, source_sha: str, output: Path) -> dict:
    manifest = verify_bundle(manifest_path, source_sha)
    result = validate_case(load(public_path), load(native_path), manifest, case, source_sha)
    result["build_manifest_sha256"] = sha(manifest_path)
    if output.exists() or output.is_symlink():
        raise ParallelEvidenceHold("RECEIPT_OVERWRITE_DENIED")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def aggregate(*, folder: Path, manifest: Path, source_sha: str,
              output: Path, harness_root: Path) -> dict:
    if output.exists() or output.is_symlink():
        raise ParallelEvidenceHold("SUMMARY_OVERWRITE_DENIED")
    build = verify_bundle(manifest, source_sha)
    expected_manifest_sha = sha(manifest)
    if not harness_root.is_dir():
        raise ParallelEvidenceHold("PINNED_HARNESS_NOT_PRESENT")
    # Pinned reviewed v0.1 workflow package: do not duplicate orchestration
    # aggregation policy in this physics-case-specific evidence validator.
    sys.path.insert(0, str(harness_root.resolve()))
    from physics_harness.workflow.spec import WorkflowSpec
    from physics_harness.workflow.aggregator import aggregate as aggregate_cases
    spec = WorkflowSpec.from_dict({
        "schema_version": 1, "name": "Issue652 G6B 417 and 941 P2 P3 3ns",
        "profile": "parallel_cases", "source_sha": source_sha,
        "oci_ref": OCI, "cases": [{"id": "417"}, {"id": "941"}],
        "max_parallel": 2, "timeout_minutes": 90,
        "artifact_prefix": "issue652-g6b-parallel-3ns",
        "end_time_s": 3e-9, "intervals": 3,
    })
    # Original raw receipts are independently rechecked; a runner's
    # self-declared normalized receipt cannot promote its own evidence.
    import tempfile
    with tempfile.TemporaryDirectory(prefix="issue652-aggregator-") as staging:
        normalized = Path(staging)
        for case in CASES:
            receipt = validate_case(
                load(folder / ("g6b-public100-" + case + ".json")),
                load(folder / ("g6b-native3ns-" + case + ".json")),
                build, case, source_sha)
            receipt["build_manifest_sha256"] = expected_manifest_sha
            (normalized / ("physics-case-receipt-" + case + ".json")).write_text(
                json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        summary = aggregate_cases(spec, normalized)
    if summary["execution_status"] != "EXIT_ZERO_UNVERIFIED":
        raise ParallelEvidenceHold("NOT_ALL_TWO_CASES_VERIFIED")
    summary.update({
        "g6b_native_registration": "PASS_TYPED_15_OWNERS_PER_CASE",
        "g6b_p3_3ns": "PASS_FINITE_3NS_PER_CASE",
        "P4_100us": "NOT_RUN", "science_status": "SCIENCE_HOLD",
        "original_public_d_lookup_sha256": SOURCE_100_SHA,
        "production_owner_source": source_sha,
    })
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="operation", required=True)
    for name in ("case", "aggregate"):
        p = sub.add_parser(name)
        p.add_argument("--manifest", type=Path, required=True)
        p.add_argument("--source-sha", required=True)
        p.add_argument("--output", type=Path, required=True)
        if name == "case":
            p.add_argument("--case", choices=CASES, required=True)
            p.add_argument("--public", type=Path, required=True)
            p.add_argument("--native", type=Path, required=True)
        else:
            p.add_argument("--receipts", type=Path, required=True)
            p.add_argument("--harness-root", type=Path, required=True)
    args = ap.parse_args()
    if args.operation == "case":
        r = make_case_receipt(public_path=args.public, native_path=args.native,
                              manifest_path=args.manifest, case=args.case,
                              source_sha=args.source_sha, output=args.output)
        print("G6B_MATRIX_CASE_VERIFIED", r["case_id"], "3NS", "SCIENCE_HOLD")
    else:
        r = aggregate(folder=args.receipts, manifest=args.manifest,
                      source_sha=args.source_sha, output=args.output,
                      harness_root=args.harness_root)
        print("G6B_MATRIX_BOTH_CASES_VERIFIED", r["g6b_p3_3ns"], "SCIENCE_HOLD")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
