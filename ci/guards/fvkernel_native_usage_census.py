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
