#!/usr/bin/env python3
"""Code3 active-consumer pre-retirement census, exact Git HEAD only (#817).

No consumer-zero, Native science, or C/H deletion claim. This phase must
FAIL CLOSED if active expected consumers disappear without a migration gate.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
TARGET = "PhysicsFVElectronReactionSource"
SRC = "physics_app/src/fvkernels/PhysicsFVElectronReactionSource.C"
HDR = "physics_app/include/fvkernels/PhysicsFVElectronReactionSource.h"
SRC_BLOB = "35ded0eab65ad7bed85baa0104261c90bc26bf3d"
HDR_BLOB = "5250b3500d6694481158e2abb896c7e1c6f349e9"
RUNNER = "experiments/Code3_electron_source_retirement/run.py"
RUNNER_BLOB = "0975c89f3072b782894566d43c5d2057afd9132f"
TEST = "tests/test_code3_electron_source_retirement.py"
TEST_BLOB = "5d4433f3e08a714129efd824dcae9521626c68d1"
SCHEMA = "issue817.code3.consumer_cut.v0.2"
HISTORIC_GENERATOR = "experiments/historical_recipe_support/issue192_s5r.py"
LIVE_IMPORTER = "experiments/Issue192_s5r_representative/run.py"
REQUIRED_REFERENCES = (
    "physics_app/ci/check_stage5_h05_runtime.py",
    "physics_app/ci/check_r2_o2_ionization_implementation.py",
    "physics_app/ci/check_issue402_json_rate_native_p2.py",
    "physics_app/ci/ei01_attachment_runtime_smoke.i",
    HISTORIC_GENERATOR,
)
REGEX_HEAD = re.compile(r"[0-9a-f]{40}\Z")
TYPE_TOKEN = re.compile(r"\b" + re.escape(TARGET) + r"\b")


def demand(cond: bool, code: str) -> None:
    if not cond:
        raise ValueError("ISSUE817_" + code)


def git(root: Path, *args: str, empty_ok: bool = False) -> bytes:
    r = subprocess.run(["git", "-C", str(root), *args],
                       capture_output=True, check=False, timeout=90)
    if r.returncode and not (empty_ok and r.returncode == 1):
        raise ValueError("ISSUE817_GIT_READ_FAILED:" + args[0])
    return r.stdout


def classify(path: str) -> str:
    if path in (SRC, HDR):
        return "SOURCE_DEFINITION"
    if path.endswith(".i"):
        return "MOOSE_INPUT_CONSUMER"
    if path.startswith("physics_app/ci/") and path.endswith((".py", ".sh")):
        return "ACTIVE_CI_CONSUMER_OR_GUARD"
    if path.startswith(("experiments/", "scripts/")) and path.endswith((".py", ".sh")):
        return "GENERATOR_POTENTIAL_UNRESOLVED"
    if path.startswith(("physics_app/src/", "physics_app/include/")):
        return "OTHER_CPP_CONSUMER"
    if path.startswith((".github/workflows/", "ci/workflow_templates/")):
        return "WORKFLOW_REFERENCE"
    if path.startswith("tests/"):
        return "TEST_REFERENCE"
    if path.startswith(("ci/guards/", "ci/baselines/")):
        return "EVIDENCE_OR_GUARD_REFERENCE"
    if path.startswith("docs/"):
        return "DOC_REFERENCE"
    return "OTHER_TRACKED_REFERENCE"


def check_pre_retirement(tracked: dict[str, dict], refs: dict[str, dict]) -> None:
    for p, sha in ((SRC, SRC_BLOB), (HDR, HDR_BLOB),
                   (RUNNER, RUNNER_BLOB), (TEST, TEST_BLOB)):
        demand(tracked.get(p, {}).get("sha") == sha and
               tracked[p]["mode"] in ("100644", "100755"),
               "SOURCE_OR_CANDIDATE_BLOB_DRIFT:" + p)
    for p in REQUIRED_REFERENCES:
        demand(p in refs and
               refs[p]["class"] in
               ("ACTIVE_CI_CONSUMER_OR_GUARD", "MOOSE_INPUT_CONSUMER",
                "GENERATOR_POTENTIAL_UNRESOLVED"),
               "REQUIRED_LIVE_OR_GENERATED_CONSUMER_MISSING:" + p)
    demand(LIVE_IMPORTER in tracked and HISTORIC_GENERATOR in refs,
           "HISTORICAL_GENERATOR_LIVE_IMPORTER_UNVERIFIED")



# This pre-cut validator is retained only to verify the immutable original
# diagnostic contract in its synthetic negative tests.
ARCHIVE = "ci/baselines/code3_historical_source_retirement.json"
ALLOWED_ACTIVE_HISTORICAL_ASSERTIONS = {
    "physics_app/ci/check_e8_ei16_energy_contract.py",
    "physics_app/ci/check_stage5_s5r_preflight.py",
    "physics_app/ci/check_stage5_ei18_runtime.py",
    "physics_app/ci/check_e8_elastic_ei19_runtime.py",
    "physics_app/ci/check_stage5_s5d_heavy_reactions.py",
}
CURRENT_POSITIVE_ROUTES = {
    "physics_app/ci/ei01_attachment_runtime_smoke.i": (
        "type = FVCoupledForce", "v = ei01_electron_number_source", "coef = 1"),
    "physics_app/ci/check_stage5_h05_runtime.py": (
        "type = FVCoupledForce", "v = S_e_h05", "coef = 1"),
    "physics_app/ci/check_r2_o2_ionization_implementation.py": (
        "type = FVCoupledForce", "v = electron_ionization_number_source", "coef = 1"),
    "physics_app/ci/check_stage5_ei20_runtime.py": (
        "type = FVCoupledForce", "v = electron_ei20_number_source", "coef = 1"),
    "physics_app/ci/check_e8_ei16_energy_runtime.py": (
        "type = FVCoupledForce", "v = electron_ionization_number_source", "coef = 1"),
    "physics_app/ci/check_stage5_edetach_runtime.py": (
        "type=FVCoupledForce", "v=electron_edetach_number_source", "coef=1"),
    "physics_app/ci/check_standard_moose_energy_projection.py": (
        "type = FVCoupledForce", "v = electron_ionization_number_source", "coef = 1"),
    HISTORIC_GENERATOR: (
        "type = FVCoupledForce", "v = S_e_s5r", "coef = {1.0 / n_ref:.17g}"),
}

def check_post_retirement(root: Path, tracked: dict[str, dict], refs: dict[str, dict]) -> dict:
    demand(SRC not in tracked and HDR not in tracked,
           "RETIRED_CODE3_CPP_REINTRODUCED")
    demand(ARCHIVE in tracked and LIVE_IMPORTER in tracked,
           "HISTORICAL_PROVENANCE_OR_IMPORTER_MISSING")
    archive = json.loads(git(root, "show", "HEAD:" + ARCHIVE))
    demand(archive.get("legacy_source_git_blob_sha") == SRC_BLOB and
           archive.get("legacy_header_git_blob_sha") == HDR_BLOB and
           archive.get("old_signed_physical_residual") == "-S_e" and
           archive.get("old_signed_normalized_residual") == "-S_e/n_ref",
           "RETIREMENT_HISTORY_HASH_OR_SIGN_DRIFT")
    for path, needles in CURRENT_POSITIVE_ROUTES.items():
        demand(path in tracked, "MIGRATED_CONSUMER_MISSING:" + path)
        source = git(root, "show", "HEAD:" + path).decode("utf-8")
        demand(TARGET not in source, "OLD_FACTORY_IN_LIVE_CONSUMER:" + path)
        for token in needles:
            demand(token in source, "STANDARD_OWNER_OR_SIGNED_FUNCTOR_MISSING:" + path)
    disallowed = []
    for path, row in refs.items():
        cls = row["class"]
        if path.startswith("experiments/Code3_electron_source_retirement/"):
            continue  # archived offline A/B fixture; never an active Factory
        if path in ALLOWED_ACTIVE_HISTORICAL_ASSERTIONS:
            continue  # legacy provenance or explicit negative absence control
        if cls in ("ACTIVE_CI_CONSUMER_OR_GUARD",
                   "MOOSE_INPUT_CONSUMER", "OTHER_CPP_CONSUMER",
                   "WORKFLOW_REFERENCE"):
            disallowed.append(path)
        elif path.startswith("experiments/") and path.endswith((".py", ".i")):
            disallowed.append(path)
    demand(not disallowed, "OLD_FACTORY_ACTIVE_REFERENCE:" + ",".join(sorted(disallowed)))
    return {
        "retired_cpp_absent": True,
        "archived_legacy_blob_sha_verified": True,
        "migrated_consumer_count": len(CURRENT_POSITIVE_ROUTES),
        "old_factory_active_references": [],
        "negative_or_frozen_contract_references": sorted(
            p for p in refs if p in ALLOWED_ACTIVE_HISTORICAL_ASSERTIONS),
    }

def audit(root: Path, expected_head: str) -> dict:
    root = root.resolve()
    demand(bool(REGEX_HEAD.fullmatch(expected_head)), "BAD_HEAD")
    actual_head = git(root, "rev-parse", "HEAD").decode().strip()
    demand(actual_head == expected_head, "EXACT_HEAD_MISMATCH")
    tracked = {}
    for entry in git(root, "ls-tree", "-r", "-z", "HEAD").split(b"\0"):
        if not entry:
            continue
        meta, path = entry.split(b"\t", 1)
        mode, kind, sha = meta.decode().split()
        name = path.decode("utf-8")
        demand(name not in tracked, "DUPLICATE_TRACKED_PATH")
        tracked[name] = {"mode": mode, "kind": kind, "sha": sha}
    demand(len(tracked) > 1500, "INCOMPLETE_NEWONLY_TREE")
    raw = git(root, "grep", "-n", "-F", "-I", TARGET, "HEAD", "--",
              empty_ok=True).decode("utf-8")
    refs = {}
    for line in raw.splitlines():
        items = line.split(":", 3)
        demand(len(items) == 4 and items[0] == "HEAD",
               "MALFORMED_SOURCE_REFERENCE")
        _, path, lineno, value = items
        demand(path in tracked and lineno.isdecimal(),
               "REFERENCE_NOT_IN_EXACT_TREE")
        if not TYPE_TOKEN.search(value):
            continue
        row = refs.setdefault(path, {"path": path, "class": classify(path),
                                     "blob_sha": tracked[path]["sha"],
                                     "line_numbers": []})
        row["line_numbers"].append(int(lineno))
    postcut = check_post_retirement(root, tracked, refs)
    counts = dict(sorted(Counter(r["class"] for r in refs.values()).items()))
    return {
        "schema": SCHEMA,
        "source_head": actual_head,
        "source_tree": git(root, "rev-parse", "HEAD^{tree}").decode().strip(),
        "tracked_paths": len(tracked),
        "target": TARGET,
        "source_blob_sha": SRC_BLOB,
        "header_blob_sha": HDR_BLOB,
        "PR707_candidate_runner_blob_sha": RUNNER_BLOB,
        "PR707_candidate_test_blob_sha": TEST_BLOB,
        "reference_count_by_class": counts,
        "references": sorted(refs.values(), key=lambda x: x["path"]),
        "live_importer_path": LIVE_IMPORTER,
        "import_activation": "NOT_RUNTIME_OBSERVED",
        "actual_Newonly_417_941_use": "NOT_INFERRED_FROM_TRACKED_TEXT",
        "external_dynamic_consumers": "NOT_CLOSED",
        "replacement_physical_coefficient": "1",
        "replacement_normalized_coefficient": "1/n_ref",
        "P0_electron_only_input_diff": "SEPARATE_RUNNER",
        "P1_P2_P3_AD_parity": "NOT_TESTED_BY_THIS_GUARD",
        "active_consumer_migration": "TRACKED_NEWONLY_CONSUMERS_MIGRATED_PENDING_NATIVE",
        "post_cut_contract": postcut,
        "source_cut_applied": True,
        "safe_delete": False,
        "merge_to_main": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = audit(ROOT, args.expected_head)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    except (ValueError, UnicodeError, OSError) as exc:
        print("ISSUE817_CODE3_P0=FAIL:" + str(exc))
        return 1
    print("ISSUE817_CODE3_P0=PASS_TRACKED_FACTORY_CUT_NATIVE_SCIENCE_HOLD")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
