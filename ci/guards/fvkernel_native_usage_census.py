"""Sanitized real-Native FVKernel source usage from the existing P05 observer.

One trace comes from FEProblemBase::addFVKernel/addFVBC/addBoundaryCondition
after the original function returns. No raw object names or protected data
are exported. This is not a whole-Warehouse or safe-deletion proof.
"""
from __future__ import annotations

from collections import Counter
import hashlib
from pathlib import Path
import re

REGISTER = re.compile(r'register(?:AD)?MooseObject\s*\(\s*"PhysicsApp"\s*,\s*([A-Za-z_]\w*)\s*\)')
CLASS = re.compile(r"[A-Za-z_]\w{0,127}\Z")
HEAD = re.compile(r"[a-f0-9]{40}\Z")
SHA = re.compile(r"[a-f0-9]{64}\Z")
FAMILIES = ("FVKernel", "FVBC", "FEBoundaryCondition")


def source_owners(source_dir: Path) -> list[dict]:
    if source_dir.is_symlink() or not source_dir.is_dir():
        raise ValueError("SOURCE_DIRECTORY_UNAVAILABLE")
    files = sorted(source_dir.glob("*.C"))
    if not files:
        raise ValueError("SOURCE_FILES_UNAVAILABLE")
    owners = set()
    result = []
    for path in files:
        if path.is_symlink() or not path.is_file():
            raise ValueError("SOURCE_FILE_UNSAFE")
        raw = path.read_bytes()
        types = REGISTER.findall(raw.decode("utf-8"))
        if not types or len(types) != len(set(types)):
            raise ValueError("SOURCE_FACTORY_AMBIGUOUS")
        if any(t in owners for t in types):
            raise ValueError("DUPLICATE_FACTORY_OWNER")
        owners.update(types)
        git_sha = hashlib.sha1(
            b"blob " + str(len(raw)).encode() + b"\0" + raw
        ).hexdigest()
        result.append({
            "source_file": "physics_app/src/fvkernels/" + path.name,
            "source_blob_sha": git_sha,
            "registered_factory_types": sorted(types),
        })
    return result


def summarize_clean_registration_trace(
    raw: bytes, source_dir: Path, *, source_head: str,
    binary_sha256: str, registration_log_sha256: str,
    reported_event_count: int,
) -> dict:
    if (not isinstance(raw, bytes) or not raw or len(raw) > 1048576
            or not raw.endswith(b"\n")):
        raise ValueError("REGISTRATION_TRACE_SIZE_OR_FORMAT")
    if not HEAD.fullmatch(source_head) or not SHA.fullmatch(binary_sha256):
        raise ValueError("SOURCE_OR_BINARY_IDENTITY")
    if not SHA.fullmatch(registration_log_sha256):
        raise ValueError("INVALID_TRACE_IDENTITY")
    digest = hashlib.sha256(raw).hexdigest()
    if digest != registration_log_sha256:
        raise ValueError("REGISTRATION_TRACE_SHA_MISMATCH")
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeError as exc:
        raise ValueError("REGISTRATION_TRACE_NOT_UTF8") from exc
    markers = 0
    family_counts = Counter()
    type_counts = Counter()
    events = 0
    for line in lines:
        if line == "P5X_PRELOAD_READY":
            markers += 1
            continue
        tokens = line.split("\t")
        if (len(tokens) != 4 or tokens[0] != "P5X_REGISTER"
                or tokens[1] not in FAMILIES
                or not tokens[2] or len(tokens[2]) > 256
                or not tokens[3] or len(tokens[3]) > 256
                or not tokens[3].isprintable()):
            raise ValueError("INVALID_REGISTRATION_EVENT")
        family_counts[tokens[1]] += 1
        type_counts[(tokens[1], tokens[3])] += 1
        events += 1
    # The preload constructor can execute in more than one loader process.
    # Require evidence that the observer loaded, but never infer a single
    # process from a shared trace. The P05 caller independently checks the
    # per-object registration uniqueness and exact event count.
    if (markers < 1 or not isinstance(reported_event_count, int)
            or events != reported_event_count or not family_counts["FVKernel"]):
        raise ValueError("REGISTRATION_EVENT_COUNT_OR_OBSERVER_MARKER_MISMATCH")

    rows = source_owners(source_dir)
    local = set()
    for item in rows:
        counts = {t: type_counts["FVKernel", t]
                  for t in item["registered_factory_types"]}
        item["observed_factory_counts"] = {
            t: n for t, n in counts.items() if n
        }
        item["observed_fvkernel_instances"] = sum(counts.values())
        item["run_usage"] = ("OBSERVED_VIA_FEProblemBase_addFVKernel"
                             if item["observed_fvkernel_instances"]
                             else "NOT_OBSERVED_IN_INSTRUMENTED_API")
        item["deletion_approved"] = False
        local.update(item["registered_factory_types"])
    all_fv = {t: count for (family, t), count in sorted(type_counts.items())
              if family == "FVKernel"}
    return {
        "schema": "fvkernel.native_source_usage.v0.1",
        "source_head": source_head,
        "binary_sha256": binary_sha256,
        "registration_log_sha256": digest,
        "observed_all_events": events,
        "observer_marker_count": markers,
        "trace_scope": "POST_ORIGINAL_CALLS_NOT_WHOLE_WAREHOUSE",
        "event_family_counts": {t: family_counts[t] for t in FAMILIES},
        "fvkernel_type_counts": all_fv,
        "other_source_or_framework_type_counts": {
            t: n for t, n in all_fv.items() if t not in local
        },
        "source_files": rows,
        "source_file_count": len(rows),
        "local_registered_factory_types": len(local),
        "safe_to_delete": False,
        "global_consumer_closed": False,
        "native_physics_parity": "NOT_EVALUATED",
        "raw_names_exported": False,
        "protected_data_exported": False,
    }

THERMAL_SOURCE = "physics_app/src/fvkernels/PhysicsFVThermalDiffusion.C"
THERMAL_BLOB = "6887710910c95f37f5f6ed94d4344384b297b4e0"


def compare_p05_source_usage(before: dict, after: dict) -> dict:
    """A/B actual P05 registration parity, fail closed; never science approval."""
    for label, receipt in (("A", before), ("B", after)):
        if (receipt.get("status") != "PASS_16_INTENDED_NATIVE_REJECTIONS"
                or receipt.get("native_tests_completed") != 16
                or receipt.get("native_expected_rejections") != 16
                or receipt.get("science") != "SCIENCE_HOLD"
                or receipt.get("private_data_in_artifacts") is not False
                or receipt.get("tmpfs_cleanup_verified") is not True):
            raise ValueError("D5_AB_" + label + "_CLEAN_OR_PRIVATE_PROVENANCE_INVALID")
        w1 = receipt.get("one_build_bundle", {})
        if (w1.get("source_head") != receipt.get("source_head")
                or w1.get("W1_elf_sha256") != receipt.get("binary_sha256")
                or w1.get("build_count") != 1):
            raise ValueError("D5_AB_" + label + "_ONE_BUILD_IDENTITY_INVALID")
    if (before["source_head"] == after["source_head"]
            or before.get("OCI") != after.get("OCI")):
        raise ValueError("D5_AB_SOURCE_HEAD_OR_OCI_INVALID")
    cases = {}
    for case in ("417", "941"):
        ac = before["cases"][case]
        bc = after["cases"][case]
        for key in ("source_layer_sha256", "JSON_sha256", "parent_mesh_sha256"):
            if ac.get(key) != bc.get(key):
                raise ValueError("D5_AB_INPUT_SHA_MISMATCH:" + case + ":" + key)
        if (len(ac.get("source_layer_sha256", {})) != 11
                or len(bc.get("source_layer_sha256", {})) != 11
                or ac.get("clean_syntax_ok") is not True
                or bc.get("clean_syntax_ok") is not True
                or ac.get("clean_exit") != 0 or bc.get("clean_exit") != 0
                or ac.get("source_restoration") != "SHA_ALL_PUBLIC_FILES_UNCHANGED"
                or bc.get("source_restoration") != "SHA_ALL_PUBLIC_FILES_UNCHANGED"):
            raise ValueError("D5_AB_CLEAN_INPUT_INTEGRITY_INVALID:" + case)
        a = before["full_fvkernel_source_usage"][case]
        b = after["full_fvkernel_source_usage"][case]
        for label, r, parent in (("A", a, before), ("B", b, after)):
            if (r.get("schema") != "fvkernel.native_source_usage.v0.1"
                    or r.get("source_head") != parent["source_head"]
                    or r.get("binary_sha256") != parent["binary_sha256"]
                    or r.get("trace_scope") != "POST_ORIGINAL_CALLS_NOT_WHOLE_WAREHOUSE"
                    or r.get("safe_to_delete") is not False
                    or r.get("global_consumer_closed") is not False
                    or r.get("protected_data_exported") is not False
                    or r.get("observed_all_events") !=
                    parent["owner_registration"][case]["recorded_all_events"]
                    or not isinstance(r.get("observer_marker_count"), int)
                    or r["observer_marker_count"] < 1):
                raise ValueError("D5_AB_" + label + "_CENSUS_INVALID:" + case)
        for field in ("observed_all_events", "event_family_counts",
                      "fvkernel_type_counts", "other_source_or_framework_type_counts"):
            if a[field] != b[field]:
                raise ValueError("D5_AB_FULL_REGISTRATION_MISMATCH:" + case + ":" + field)
        for key in ("observed_FVKernel", "observed_FVBC", "observed_electron_FE_BC",
                    "actual_registered_count"):
            if before["owner_registration"][case][key] != after["owner_registration"][case][key]:
                raise ValueError("D5_AB_FILTERED_OWNER_MISMATCH:" + case + ":" + key)
        ar = {x["source_file"]: x for x in a["source_files"]}
        br = {x["source_file"]: x for x in b["source_files"]}
        therm = ar.get(THERMAL_SOURCE)
        if therm is None or therm.get("source_blob_sha") != THERMAL_BLOB:
            raise ValueError("D5_AB_THERMAL_PRECUT_SOURCE_IDENTITY_INVALID")
        if therm.get("observed_fvkernel_instances") != 0:
            raise ValueError("D5_AB_THERMAL_RUNTIME_OBSERVED")
        if THERMAL_SOURCE in br or set(ar) - {THERMAL_SOURCE} != set(br):
            raise ValueError("D5_AB_SOURCE_SET_DIFF_NOT_ONLY_THERMAL")
        if len(ar) != 13 or len(br) != 12:
            raise ValueError("D5_AB_SOURCE_INVENTORY_COUNT")
        for path, row in br.items():
            if ar[path] != row:
                raise ValueError("D5_AB_OTHER_SOURCE_OR_FACTORY_CHANGED:" + path)
        if a.get("local_registered_factory_types") != 18 or b.get("local_registered_factory_types") != 17:
            raise ValueError("D5_AB_FACTORY_REGISTRY_COUNT")
        cases[case] = {
            "clean_input_source_shas_identical": True,
            "full_fvkernel_type_counts_identical": True,
            "observed_all_registration_events": a["observed_all_events"],
            "thermal_factory_instances_before": 0,
            "other_source_factory_counts_identical": True,
        }
    return {
        "schema": "fvkernel.native_thermal_ab_comparison.v0.1",
        "status": "PASS_SCOPE_ONLY_NOT_DELETION_APPROVAL",
        "before_source_head": before["source_head"],
        "after_source_head": after["source_head"],
        "before_elf_sha256": before["binary_sha256"],
        "after_elf_sha256": after["binary_sha256"],
        "oci": before["OCI"],
        "cases": cases,
        "p2_registration_parity": "PASS_INSTRUMENTED_API_ONLY",
        "actual_P3_parity": "NOT_TESTED",
        "global_caller_zero": "NOT_PROVEN",
        "safe_to_delete": False,
    }


def _main_ab() -> int:
    import argparse
    import json
    parser = argparse.ArgumentParser(description="Exact Native P05 A/B source usage comparison")
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        a = json.loads(args.before.read_text())
        b = json.loads(args.after.read_text())
        result = compare_p05_source_usage(a, b)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print("D5_NATIVE_AB=HOLD:" + str(exc))
        return 1
    print("D5_NATIVE_AB=PASS_SCOPE_ONLY_NOT_DELETION_APPROVAL")
    print("D5_NATIVE_AB_SUMMARY=" + str(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main_ab())
