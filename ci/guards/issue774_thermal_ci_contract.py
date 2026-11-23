#!/usr/bin/env python3
"""#774: fail-closed CI migration contract for a retired PhysicsApp FVKernel.

This checks live CI/registry/source and immutable historical evidence separately.
A PASS proves CI migration within the tracked tree, never global caller-zero,
Native science parity, third-party approval, or main-merge authorization.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

import yaml

import fdeg_structural as structural
import fdeg_thermal_archive as archive

POLICY = "ci/baselines/issue774_thermal_retirement_ci_contract.json"
TARGET = "PhysicsFVThermalDiffusion"
SOURCE = "physics_app/src/fvkernels/PhysicsFVThermalDiffusion.C"
HEADER = "physics_app/include/fvkernels/PhysicsFVThermalDiffusion.h"
WORKFLOW = ".github/workflows/physics-code-ci.yml"
ARCHIVE = "reports/issue774/archive/fdeg-retirement-code7-45148961276-1.zip"
ANCHOR = "reports/issue774/fdeg_thermal_historical_anchor_v0_1.json"
FUNCTIONAL = "ci/baselines/fdeg_functional_contracts.json"
TRANSITION = "ci/baselines/fdeg_transition_contracts.json"
SCHEMA = "fvkernel.thermal_retired_ci_contract.v0.1"
LIVE_FDEG_STEPS = (
    "Validate FDEG Structural Evidence P0",
    "Validate FDEG Functional Contract P0",
    "Validate FDEG Transition Evidence P0",
    "Validate FDEG Harness A-D P0",
    "Validate FDEG Scan Cache P0",
)
VERIFY_STEP = "Verify pinned historical FDEG code7 archive (no live source)"
UPLOAD_STEP = "Upload historical FDEG code7 verification"
_TOKEN = re.compile(r"\bPhysicsFVThermalDiffusion\b")


def _require(test: bool, message: str) -> None:
    if not test:
        raise ValueError("ISSUE774_THERMAL_CI_" + message)


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *args],
                            capture_output=True, timeout=45, check=False)
    _require(result.returncode == 0, "GIT_SOURCE_UNAVAILABLE")
    return result.stdout.decode("utf-8", "strict")


def validate_policy(policy: dict) -> None:
    _require(isinstance(policy, dict) and policy.get("schema") == SCHEMA,
             "POLICY_SCHEMA")
    _require(policy.get("issue") == 774 and policy.get("target") == TARGET,
             "POLICY_TARGET")
    _require(policy.get("support_contract") == "NEW_ONLY"
             and policy.get("legacy_input_support") == "NOT_REQUIRED",
             "LEGACY_SUPPORT_NOT_WAIVED")
    ref = policy.get("requester_policy_ref")
    _require(isinstance(ref, str) and ref.startswith(
        "https://github.com/HyungseonSong-plasma/moose-test-repo/issues/774#issuecomment-"),
        "REQUESTER_DECISION_REFERENCE_MISSING")
    _require(policy.get("active_factory", {}).get("source") == SOURCE
             and policy.get("active_factory", {}).get("header") == HEADER
             and policy["active_factory"].get("expected_present") is False,
             "FACTORY_SOURCE_POLICY")
    hist = policy.get("historical_archive", {})
    _require(hist.get("path") == ARCHIVE and hist.get("anchor") == ANCHOR
             and hist.get("retained_immutable") is True,
             "HISTORICAL_ARCHIVE_POLICY")
    _require(policy.get("active_fdeg", {}).get("number_of_other_profiles") == 9
             and policy.get("active_fdeg", {}).get("retired_profile_present") is False,
             "ACTIVE_FDEG_POLICY")
    _require(policy.get("canonical_ci", {}).get("workflow") == WORKFLOW
             and policy["canonical_ci"].get("source_bound_live_capture_allowed") is False,
             "ACTIVE_WORKFLOW_POLICY")
    _require(policy.get("safe_to_delete") is False
             and policy.get("final_code_retirement_authorized") is False
             and policy.get("requested_merge_to_main") is False
             and policy.get("global_consumer_closed") is False,
             "FALSE_RETIREMENT_APPROVAL")


def validate_registries(root: Path, functional: dict, transition: dict) -> list[str]:
    _require(functional.get("schema") == "fdeg.functional_registry.v0.2"
             and transition.get("schema") == "fdeg.transition_policy.v0.1",
             "REGISTRY_SCHEMAS")
    fp, tp = functional.get("profiles"), transition.get("profiles")
    _require(isinstance(fp, dict) and isinstance(tp, dict), "MISSING_PROFILES")
    _require(TARGET not in fp and TARGET not in tp, "ACTIVE_RETIRED_PROFILE")
    _require(len(fp) == 9 and set(fp) == set(tp), "NINE_SURVIVING_PROFILES_MISMATCH")
    for name, profile in fp.items():
        source = profile.get("source", {})
        path, expected = source.get("path"), source.get("blob_sha")
        _require(isinstance(path, str) and path.startswith("physics_app/src/fvkernels/")
                 and path.endswith(".C") and ".." not in Path(path).parts
                 and isinstance(expected, str) and re.fullmatch(r"[0-9a-f]{40}", expected)
                 is not None, "SURVIVOR_SOURCE_RECORD_INVALID")
        file = root / path
        _require(file.is_file() and not file.is_symlink()
                 and structural.blob_sha(file.read_bytes()) == expected,
                 "SURVIVOR_SOURCE_SHA_MISMATCH:" + name)
    return sorted(fp)


def validate_workflow(doc: dict) -> None:
    _require(isinstance(doc, dict) and isinstance(doc.get("jobs"), dict)
             and "physics_code_validate" in doc["jobs"], "MISSING_PHYSICS_CODE_JOB")
    # The archive gate is only meaningful if archive/policy edits actually
    # start this Workflow. Avoid broad reports/** and ci/baselines/** triggers.
    triggers = doc.get("on")
    _require(isinstance(triggers, dict), "MISSING_WORKFLOW_TRIGGERS")
    critical = {POLICY, FUNCTIONAL, TRANSITION, ARCHIVE, ANCHOR}
    for event in ("push", "pull_request"):
        block = triggers.get(event)
        paths = block.get("paths") if isinstance(block, dict) else None
        _require(isinstance(paths, list) and critical <= set(paths),
                 "FDEG_CONTRACT_CHANGE_NOT_TRIGGERED:" + event)
    steps = doc["jobs"]["physics_code_validate"].get("steps")
    _require(isinstance(steps, list), "INVALID_WORKFLOW_STEPS")
    labels = [step.get("name", "") for step in steps if isinstance(step, dict)]
    for label in (*LIVE_FDEG_STEPS, VERIFY_STEP, UPLOAD_STEP):
        _require(labels.count(label) == 1, "MISSING_OR_DUPLICATE_FDEG_STEP:" + label)
    idx = {label: labels.index(label) for label in (*LIVE_FDEG_STEPS, VERIFY_STEP, UPLOAD_STEP)}
    _require(max(idx[label] for label in LIVE_FDEG_STEPS) < idx[VERIFY_STEP]
             < idx[UPLOAD_STEP], "ARCHIVE_VERIFY_UPLOAD_ORDER")
    entries = {step.get("name"): step for step in steps if isinstance(step, dict)}
    verifier = entries[VERIFY_STEP].get("run", "")
    _require(isinstance(verifier, str)
             and "ci/guards/fdeg_thermal_archive.py" in verifier
             and "--archive-zip " + ARCHIVE in verifier
             and "fdeg-retirement-code7/archive-validation.log" in verifier,
             "HISTORICAL_VERIFY_COMMAND_MISSING")
    _require("ci/guards/issue774_thermal_ci_contract.py --output" in verifier
             and "fdeg-retirement-code7/ci-contract.json" in verifier,
             "RETIREMENT_CI_RECEIPT_NOT_IN_HISTORICAL_ARTIFACT")
    upload = entries[UPLOAD_STEP]
    with_args = upload.get("with")
    _require(upload.get("uses") == "actions/upload-artifact@v4"
             and upload.get("if") == "success()"
             and isinstance(with_args, dict)
             and str(with_args.get("name", "")).startswith("fdeg-historical-code7-")
             and "fdeg-retirement-code7/" in str(with_args.get("path", "")),
             "HISTORICAL_ARTIFACT_UPLOAD_ORPHAN")
    for job in doc["jobs"].values():
        _require(isinstance(job, dict), "INVALID_JOB")
        for item in job.get("steps", []):
            command = item.get("run", "") if isinstance(item, dict) else ""
            _require(isinstance(command, str)
                     and not ("fdeg_retirement_evidence.py" in command and "--mode capture" in command)
                     and not ("--target " + TARGET in command),
                     "STALE_LIVE_SOURCE_CAPTURE")
    _require(TARGET not in json.dumps(doc), "LIVE_WORKFLOW_REFERENCES_RETIRED_FACTORY")


def active_reference_hits(tracked: dict[str, str]) -> list[str]:
    """Search actionable input/code, not archive/test/docs or a different QPX Factory."""
    hits: list[str] = []
    for path, content in sorted(tracked.items()):
        active = (
            path.endswith(".i")
            or (path.startswith(("physics_app/src/", "physics_app/include/"))
                and path.endswith((".C", ".cc", ".cpp", ".h", ".hpp")))
            or (path.startswith(".github/workflows/")
                and path.endswith((".yml", ".yaml")))
            or (path.startswith(("physics_app/ci/", "experiments/", "scripts/",
                                 "automation/"))
                and path.endswith((".py", ".sh")))
        )
        if active and _TOKEN.search(content):
            hits.append(path)
    return hits


def audit(root: Path) -> dict:
    root = root.resolve()
    head = _git(root, "rev-parse", "--verify", "HEAD").strip()
    _require(re.fullmatch(r"[0-9a-f]{40}", head) is not None, "NON_SHA_HEAD")
    policy = json.loads((root / POLICY).read_text())
    validate_policy(policy)
    _require(not (root / SOURCE).exists() and not (root / HEADER).exists(),
             "RETIRED_FACTORY_SOURCE_REINTRODUCED")
    funcs = json.loads((root / FUNCTIONAL).read_text())
    trans = json.loads((root / TRANSITION).read_text())
    profiles = validate_registries(root, funcs, trans)
    workflow = yaml.load((root / WORKFLOW).read_text(), Loader=yaml.BaseLoader)
    validate_workflow(workflow)
    manifest = _git(root, "ls-files", "-z").split("\0")
    tracked = {}
    for path in sorted(filter(None, manifest)):
        # Only the relevant supported active text surfaces are read.
        active = (path.endswith(".i")
                  or path.startswith(("physics_app/src/", "physics_app/include/",
                                      "physics_app/ci/", ".github/workflows/",
                                      "experiments/", "scripts/", "automation/")))
        if not active:
            continue
        file = root / path
        _require(file.is_file() and not file.is_symlink(),
                 "ACTIVE_SOURCE_UNAVAILABLE:" + path)
        if file.suffix in {".i", ".C", ".cc", ".cpp", ".h", ".hpp", ".py", ".sh",
                           ".yml", ".yaml"}:
            tracked[path] = file.read_text(encoding="utf-8", errors="replace")
    hits = active_reference_hits(tracked)
    _require(not hits, "ACTIVE_RETIRED_CONSUMER:" + ",".join(hits[:12]))
    anchor = json.loads((root / ANCHOR).read_text())
    bundle = (root / ARCHIVE)
    _require(bundle.is_file() and not bundle.is_symlink(), "MISSING_PINNED_ARCHIVE")
    archival = archive.verify_archive_bytes(bundle.read_bytes(), anchor)
    _require(archival["archive_integrity"] == "PASS"
             and archival["safe_delete"] is False
             and archival["global_consumer_closed"] is False, "HISTORICAL_PROVENANCE")
    return {
        "schema": "issue774.thermal_ci_cleanup_receipt.v0.1",
        "source_head": head, "old_input_supported": False,
        "requester_policy_ref": policy["requester_policy_ref"],
        "surviving_active_profiles": profiles,
        "active_registry_count": len(profiles),
        "archive_sha256": hashlib.sha256(bundle.read_bytes()).hexdigest(),
        "archive_verification": "PASS", "live_capture_steps": 0,
        "historical_archive_verify_steps": 1, "historical_archive_upload_steps": 1,
        "active_retired_type_references": hits,
        "tracked_active_candidate_files": len(tracked),
        "CI_MIGRATION": "PASS_WITHIN_TRACKED_SOURCE_SCOPE",
        "global_consumer_closed": False, "science": "SCIENCE_HOLD",
        "safe_to_delete": False, "main_merged": False,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    try:
        report = audit(args.root)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    except (ValueError, OSError, KeyError, TypeError, yaml.YAMLError) as error:
        print("ISSUE774_THERMAL_CI_CLEANUP=FAIL:" + str(error))
        return 1
    print("ISSUE774_THERMAL_CI_CLEANUP=PASS_WITHIN_TRACKED_SOURCE_SCOPE")
    print("ISSUE774_RETIREMENT_AUTHORIZATION=HOLD")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
