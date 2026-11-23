"""Aggregate all required case receipts without conferring scientific acceptance."""
from __future__ import annotations

import json
from pathlib import Path

from physics_harness.workflow.validator import WorkflowValidationError


def aggregate(spec, directory: Path) -> dict:
    root = Path(directory)
    cases: dict[str, str] = {}
    provenance = set()
    for case in spec.cases:
        path = root / ("physics-case-receipt-" + case.id + ".json")
        if not path.is_file() or path.is_symlink():
            cases[case.id] = "MISSING"
            continue
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cases[case.id] = "INVALID"
            continue
        if not isinstance(entry, dict) or (
            entry.get("case_id") != case.id
            or entry.get("source_sha") != spec.source_sha
            or entry.get("oci_ref") != spec.oci_ref
            or entry.get("science_status") != "HOLD"
            or entry.get("schema_version") != 1
        ):
            cases[case.id] = "IDENTITY_MISMATCH"
            continue
        build_sha = entry.get("build_manifest_sha256")
        if not isinstance(build_sha, str) or len(build_sha) != 64 or any(x not in "0123456789abcdef" for x in build_sha):
            cases[case.id] = "BUILD_PROVENANCE_INVALID"
            continue
        provenance.add(build_sha)
        cases[case.id] = ("EXECUTED_UNVERIFIED"
                          if entry.get("exit_code") == 0 and
                          entry.get("execution_status") == "EXIT_ZERO_UNVERIFIED"
                          else "FAILED_OR_UNVERIFIED")
    coherent = len(provenance) == 1
    complete = coherent and all(s == "EXECUTED_UNVERIFIED" for s in cases.values())
    return {
        "schema_version": 1, "source_sha": spec.source_sha,
        "oci_ref": spec.oci_ref, "cases": cases, "shared_build_sha_coherent": coherent,
        "execution_status": "EXIT_ZERO_UNVERIFIED" if complete else "HOLD",
        "science_status": "HOLD", "time_coverage_status": "UNVERIFIED",
    }


def write_summary(spec, directory: Path, output: Path) -> dict:
    summary = aggregate(spec, directory)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary
