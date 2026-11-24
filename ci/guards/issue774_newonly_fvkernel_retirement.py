#!/usr/bin/env python3
"""New-only Factory retirement CI contract for #774 (source/CI, not science).

The five retired Thermal, heavy mass-correction, Joule, Banded and electron-source Factory types are
unsupported in New-only. Frozen legacy recipes remain SHA-pinned. No blanket
legacy CI suppression, and no claim of external caller
zero. Preserve D5's original sanitized A/B registration receipts separately.

This guard reads the exact Git HEAD tree, never a dirty working tree fallback.
It is deliberately self-contained for the New-only ancestry, which does not
have the historical FDEG Functional/Transition/Physics Code CI modules.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess

from fvkernel_native_usage_census import source_owners

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "issue774.newonly_retired_factory_ci.v0.1"
REPO = "HyungseonSong-plasma/moose-test-repo"
RETIRED = "PhysicsFVThermalDiffusion"
SOURCE = "physics_app/src/fvkernels/PhysicsFVThermalDiffusion.C"
HEADER = "physics_app/include/fvkernels/PhysicsFVThermalDiffusion.h"
HEAVY = "PhysicsFVHeavyMassElectromigrationCorrection"
HEAVY_SOURCE = "physics_app/src/fvkernels/PhysicsFVHeavyMassElectromigrationCorrection.C"
HEAVY_HEADER = "physics_app/include/fvkernels/PhysicsFVHeavyMassElectromigrationCorrection.h"
JOULE = "PhysicsFVElectronEnergyJouleHeating"
JOULE_SOURCE = "physics_app/src/fvkernels/PhysicsFVElectronEnergyJouleHeating.C"
JOULE_HEADER = "physics_app/include/fvkernels/PhysicsFVElectronEnergyJouleHeating.h"
JOULE_SMOKE = "physics_app/ci/electron_energy_joule_smoke.i"
JOULE_ARCHIVE = "docs/provenance/issue814_code2/electron_energy_joule_smoke.i.txt"
JOULE_SMOKE_BLOB = "6c4901f843a98b74b450cc3a1fab09e8e1873b2c"
CODE1 = "FVElectronResponseBandedCorrection"
CODE1_SOURCE = "physics_app/src/fvkernels/FVElectronResponseBandedCorrection.C"
CODE1_HEADER = "physics_app/include/fvkernels/FVElectronResponseBandedCorrection.h"
CODE1_ARCHIVE = "ci/baselines/fdeg_historical_profiles_code1.json"
CODE1_ARCHIVE_BLOB = "9a8b0d60a9511fe089ef6cb3d900f902123ee742"
CODE1_HISTORIC_GENERATOR = "experiments/Issue351_frozen_heavy_driver_parity/control.py"
CODE1_HISTORIC_SHA = "6d7efcb4ea94b2011782aba2c9cab40238756312"
CODE3 = "PhysicsFVElectronReactionSource"
CODE3_SOURCE = "physics_app/src/fvkernels/PhysicsFVElectronReactionSource.C"
CODE3_HEADER = "physics_app/include/fvkernels/PhysicsFVElectronReactionSource.h"
S5R = "experiments/historical_recipe_support/issue192_s5r.py"
S5R_ARCHIVE = "docs/provenance/issue817_code3/issue192_s5r_pre_migration.py.txt"
S5R_ORIGINAL_BLOB = "be9838b77dc2920b27a1f7065648062b630eacb5"
S5R_MIGRATED_BLOB = "7dc29e5773b145d9f052d9898901eec61c904344"
RETIRED_FACTORIES = (RETIRED, HEAVY, JOULE, CODE1, CODE3)
RETIRED_PATHS = (SOURCE, HEADER, HEAVY_SOURCE, HEAVY_HEADER, JOULE_SOURCE,
                 JOULE_HEADER, CODE1_SOURCE, CODE1_HEADER, CODE3_SOURCE, CODE3_HEADER)
CODE3_ASSERTIONS = {
    "physics_app/ci/check_r2_o2_ionization_implementation.py":
        'assert "type = PhysicsFVElectronReactionSource" not in RUNTIME_INPUT',
    "physics_app/ci/check_stage5_s5r_preflight.py":
        'if h05_row.get("electron_particle_projection") != "PhysicsFVElectronReactionSource":',
    # Frozen EI16 ownership receipt, not a current input owner.
    "physics_app/ci/check_e8_ei16_energy_contract.py":
        'assert own["electron_particle_projector"] == "PhysicsFVElectronReactionSource"',
    # Existing absence tests: never allow a whole source file as an exception.
    "physics_app/ci/check_e8_elastic_ei19_runtime.py":
        '"PhysicsFVElectronReactionSource",',
    "physics_app/ci/check_stage5_ei18_runtime.py":
        'if "PhysicsFVElectronReactionSource" in text:',
    "physics_app/ci/check_stage5_s5d_heavy_reactions.py":
        '"reaction_source_", "PhysicsFVElectronReactionSource",',
}
# These are frozen historical/research references, not supported New-only inputs.
# Their tracked Git blobs must remain exact or this explicit exception fails closed.
HISTORICAL_ALLOWED = {
    "experiments/Issue282_e2a_rz_bridge/research_type_bridge.py":
        "fe82208e49c6f89b127f74fd54cf85cbb91f8fa4",
    "physics_app/ci/audit_issue402_initial_composition_routes.py":
        "858f75f6a64596ccc7386b044fa8278caf8f8b78",
    "experiments/fem_fvm_plasma_discriminator/prepare_cases.py":
        "69ec14c58b502a953c9024c46d332494cad61e6c",
    "experiments/Issue351_frozen_heavy_driver_parity/control.py":
        "6d7efcb4ea94b2011782aba2c9cab40238756312",
}
EXPECTED_SOURCE_COUNT = 8
EXPECTED_REGISTERED_COUNT = 13
EXPECTED_SHARED_SOURCE_OWNERS = {
    "physics_app/src/fvkernels/PhysicsFVLogMolarElectronTransport.C": 4,
    "physics_app/src/fvkernels/FVLogMolarTransport.C": 3,
}
OLD_HISTORICAL_CI = (
    ".github/workflows/physics-code-ci.yml",
    "ci/baselines/fdeg_functional_contracts.json",
    "ci/baselines/fdeg_transition_contracts.json",
    "ci/guards/fdeg_retirement_evidence.py",
    "ci/guards/fdeg_thermal_archive.py",
    "tests/test_fdeg_harness_abcd.py",
)
TEXT = re.compile(r"\b(?:" + "|".join(re.escape(t) for t in RETIRED_FACTORIES) + r")\b")
HEAD = re.compile(r"[0-9a-f]{40}\Z")
REGISTRATIONS = re.compile(
    r'register(?:AD)?MooseObject\s*\(\s*"PhysicsApp"\s*,\s*([A-Za-z_]\w*)\s*\)'
)
NEWONLY_CI = ".github/workflows/ci.yml"
TEMPLATE = "ci/workflow_templates/general-ci.yml"
SAFETY = "ci/guards/p6_ci_workflow_safety_guard.py"
EXISTING_TEST = "tests/test_fvkernel_native_usage_census.py"
NEW_TEST = "tests/test_issue774_newonly_fvkernel_retirement.py"
SELF = "ci/guards/issue774_newonly_fvkernel_retirement.py"


def require(condition: bool, code: str) -> None:
    if not condition:
        raise ValueError("ISSUE774_NEWONLY_" + code)


def git(root: Path, *args: str, missing_ok: bool = False) -> bytes:
    command = ["git", "-C", str(root), *args]
    result = subprocess.run(command, capture_output=True, timeout=90, check=False)
    if result.returncode and not (missing_ok and result.returncode == 1):
        raise ValueError("ISSUE774_NEWONLY_GIT_SOURCE_UNAVAILABLE")
    return result.stdout


def active_surface(path: str) -> str | None:
    """Disallow an old Factory token in executable New-only source/CI inputs.

    An archived negative fixture or code7 provenance document is not a live
    physics consumer, but it remains represented in the audit inventory.
    """
    if path in HISTORICAL_ALLOWED:
        return None
    if path.endswith(".i"):
        return "MOOSE_INPUT"
    if path.startswith(("physics_app/src/", "physics_app/include/")) and \
            path.endswith((".C", ".cc", ".cpp", ".h", ".hpp")):
        return "PHYSICS_CPP"
    if path.startswith((".github/workflows/", "ci/workflow_templates/")) and \
            path.endswith((".yml", ".yaml")):
        return "LIVE_CI_OR_TEMPLATE"
    if path.startswith(("physics_app/ci/", "experiments/", "scripts/",
                        "automation/")) and \
            path.endswith((".py", ".sh", ".json")):
        return "GENERATOR_OR_RUNTIME_JSON"
    return None


def reference_surface(path: str, line: str) -> str | None:
    tokens = set(TEXT.findall(line))
    if path == S5R and tokens == {HEAVY}:
        return None  # exact original and migrated Git blobs checked separately
    if tokens == {CODE3} and CODE3_ASSERTIONS.get(path) == line.strip():
        return None  # negative or frozen provenance assertion, not a Factory consumer
    if CODE3 in tokens and path in HISTORICAL_ALLOWED:
        # Existing exemptions cover the original retired types only.
        return "CODE3_REFERENCE_REQUIRES_DISPOSITION"
    return active_surface(path)


def check_route_rows(rows: list[dict]) -> dict:
    """Pure classifier; never count docs/tests as active input consumers."""
    active = [r for r in rows if r["active_surface"] is not None]
    counts = dict(sorted(Counter(r["active_surface"] or "NON_ACTIVE_REFERENCE"
                                 for r in rows).items()))
    require(not active, "ACTIVE_RETIRED_FACTORY_REINTRODUCED:" +
            ",".join(r["path"] for r in active[:8]))
    return {
        "matched_tracked_text_paths": len(rows),
        "reference_classes": counts,
        "active_retired_type_references": [],
    }


def check_historical_sources(tracked: dict) -> dict:
    """Pinned historical recipe/bridge audits may mention the retired type."""
    for path, expected_blob in HISTORICAL_ALLOWED.items():
        require(path in tracked and tracked[path]["sha"] == expected_blob,
                "HISTORICAL_SOURCE_PIN_DRIFT:" + path)
    return dict(sorted(HISTORICAL_ALLOWED.items()))


def check_s5r_lineage(tracked: dict) -> dict:
    require(tracked.get(S5R_ARCHIVE, {}).get("sha") == S5R_ORIGINAL_BLOB,
            "S5R_ORIGINAL_ARCHIVE_DRIFT")
    require(tracked.get(S5R, {}).get("sha") == S5R_MIGRATED_BLOB,
            "S5R_MIGRATED_SOURCE_DRIFT")
    return {"original": S5R_ORIGINAL_BLOB, "migrated": S5R_MIGRATED_BLOB}


def check_factory_inventory(root: Path, tracked: dict) -> dict:
    require(all(path not in tracked for path in
                RETIRED_PATHS),
            "RETIRED_SOURCE_OR_HEADER_REINTRODUCED")
    folder = root / "physics_app/src/fvkernels"
    entries = source_owners(folder)
    require(len(entries) == EXPECTED_SOURCE_COUNT,
            "SOURCE_TRANSLATION_UNIT_COUNT_DRIFT")
    registered = sorted(t for row in entries for t in row["registered_factory_types"])
    require(len(registered) == EXPECTED_REGISTERED_COUNT
            and len(set(registered)) == EXPECTED_REGISTERED_COUNT
            and not set(RETIRED_FACTORIES).intersection(registered),
            "FACTORY_REGISTRATION_COUNT_OR_ALIAS_DRIFT")
    for row in entries:
        path = row["source_file"]
        require(path in tracked and row["source_blob_sha"] == tracked[path]["sha"],
                "EXACT_TREE_SOURCE_BLOB_MISMATCH:" + path)
    counts = {row["source_file"]: len(row["registered_factory_types"])
              for row in entries}
    for name, count in EXPECTED_SHARED_SOURCE_OWNERS.items():
        require(counts.get(name) == count,
                "SHARED_SOURCE_REGISTRATION_OWNER_DRIFT:" + name)
    return {"source_files": len(entries), "registered_factory_types": len(registered),
            "shared_owners": {k: counts[k] for k in sorted(EXPECTED_SHARED_SOURCE_OWNERS)},
            "registered_types": registered}


def check_ci_tree(root: Path, tracked: dict) -> dict:
    require(JOULE_SMOKE not in tracked, "JOULE_LEGACY_SMOKE_STILL_ACTIVE")
    require(JOULE_ARCHIVE in tracked and
            tracked[JOULE_ARCHIVE]["sha"] == JOULE_SMOKE_BLOB,
            "JOULE_ARCHIVE_EXACT_BLOB_MISMATCH")
    for path in OLD_HISTORICAL_CI:
        require(path not in tracked, "HISTORICAL_FDEG_CI_IMPORTED:" + path)
    for path in (NEWONLY_CI, TEMPLATE, SAFETY, EXISTING_TEST, NEW_TEST, SELF):
        require(path in tracked, "CI_OWNER_MISSING:" + path)
    current = git(root, "show", "HEAD:" + NEWONLY_CI)
    template = git(root, "show", "HEAD:" + TEMPLATE)
    require(current == template, "CI_WORKFLOW_TEMPLATE_BYTES_DRIFT")
    for marker in (
        "python3 ci/guards/p6_ci_workflow_safety_guard.py --self-test --check",
        "python3 -m unittest discover -s tests -p test_fvkernel_native_usage_census.py -v",
        "python3 -m unittest discover -s tests -p test_issue774_newonly_fvkernel_retirement.py -v",
        "PUBLIC_D_COMPLETE_SUPPORT_DELTA_PASS",
    ):
        require(current.count(marker.encode()) == 1, "CI_CONTRACT_STEP_MISSING:" + marker)
    # No new broad CI owner: the retirement test is part of the existing P6
    # trigger/artifact/P05 invariant step, which runs before expensive builds.
    return {"canonical_workflow": NEWONLY_CI, "template": TEMPLATE,
            "workflow_template_bytes_equal": True,
            "newonly_retirement_test_steps": 1,
            "historical_fdeg_ci_imported": False,
            "source_safety_guard_retained": True}


def check_code1_archive(root: Path, tracked: dict) -> dict:
    """Keep exact #337/#351 source-attested history after retiring Factory code."""
    require(tracked.get(CODE1_ARCHIVE, {}).get("sha") == CODE1_ARCHIVE_BLOB,
            "CODE1_ARCHIVE_BLOB_DRIFT")
    require(tracked.get(CODE1_HISTORIC_GENERATOR, {}).get("sha") == CODE1_HISTORIC_SHA,
            "CODE1_HISTORICAL_GENERATOR_CHANGED")
    archive = json.loads(git(root, "show", "HEAD:" + CODE1_ARCHIVE))
    capture = archive.get("capture", {})
    require(archive.get("schema") == "fdeg.historical_profiles.v0.1"
            and capture.get("target") == CODE1
            and capture.get("source_file") ==
            {"path": CODE1_SOURCE, "blob_sha": "1e58703a7794ddd8eed3cba28ed9e5a1e39a141f"}
            and capture.get("header_file") ==
            {"path": CODE1_HEADER, "blob_sha": "9446a9d5d7863fb83a2c65af8b127bbd08573ad6"}
            and capture.get("historical_qualification_scope") ==
            "BOTH_LANES_USED_KERNEL_NOT_KERNEL_REMOVAL_PARITY"
            and sorted(row.get("run_id") for row in capture.get("qualified_runs", [])) ==
            [36163219902, 36496470116]
            and archive.get("functional_profile", {}).get("target") == CODE1
            and archive.get("transition_profile", {}).get("target") == CODE1,
            "CODE1_ARCHIVE_CONTRACT_INVALID")
    return {"archive_path": CODE1_ARCHIVE, "archive_blob_sha": CODE1_ARCHIVE_BLOB,
            "historical_generator_blob_sha": CODE1_HISTORIC_SHA,
            "historical_runs": [36163219902, 36496470116],
            "current_binary_legacy_replay_proven": False,
            "historic_on_off_removal_parity_proven": False}


def audit(root: Path, *, expected_head: str) -> dict:
    root = root.resolve()
    require(isinstance(expected_head, str) and HEAD.fullmatch(expected_head),
            "BAD_EXACT_SOURCE_HEAD")
    actual = git(root, "rev-parse", "--verify", "HEAD").decode().strip()
    require(actual == expected_head, "EXACT_HEAD_MISMATCH")
    entries = git(root, "ls-tree", "-r", "-l", "-z", "HEAD").split(b"\0")
    tracked = {}
    nonregular_entries = 0
    for entry in entries:
        if not entry:
            continue
        meta, pathbytes = entry.split(b"\t", 1)
        mode, kind, digest, size = meta.decode().split()
        path = pathbytes.decode("utf-8")
        require(path not in tracked, "DUPLICATE_TRACKED_SOURCE")
        tracked[path] = {"mode": mode, "kind": kind, "sha": digest,
                         "size": size}
        if kind != "blob" or mode not in ("100644", "100755"):
            nonregular_entries += 1
    require(len(tracked) > 0 and all(x in tracked for x in
            ("physics_app/dependencies.lock", NEWONLY_CI, TEMPLATE)),
            "INCOMPLETE_NEWONLY_CHECKOUT")
    # This checkout is exact-HEAD for tracked bytes, no uncommitted source
    # mutation can stand in for a verified Git blob.
    require(not git(root, "diff", "--name-only", "HEAD", "--",
                    "physics_app/src/fvkernels", "physics_app/include/fvkernels"),
            "MODIFIED_WORKTREE_FACTORY_SOURCE")
    facts = check_factory_inventory(root, tracked)
    ci = check_ci_tree(root, tracked)
    raw = git(root, "grep", "-n", "-F", "-I",
              *(arg for name in RETIRED_FACTORIES for arg in ("-e", name)),
              "HEAD", "--", missing_ok=True)
    rows = []
    for line in raw.decode("utf-8").splitlines():
        parts = line.split(":", 3)
        require(len(parts) == 4 and parts[0] == "HEAD", "INVALID_GIT_GREP_RECORD")
        _, path, lineno, source_line = parts
        require(path in tracked and lineno.isdecimal(),
                "SOURCE_MISSING_FROM_EXACT_GIT_TREE")
        if not TEXT.search(source_line):
            continue
        rows.append({"path": path, "line": int(lineno),
                     "source_blob_sha": tracked[path]["sha"],
                     "active_surface": reference_surface(path, source_line)})
    by_path = {}
    for row in rows:
        path = row["path"]
        entry = by_path.setdefault(path, {"path": path,
                   "source_blob_sha": row["source_blob_sha"],
                   "line_numbers": [], "active_surface": row["active_surface"]})
        entry["line_numbers"].append(row["line"])
        if row["active_surface"] is not None:
            entry["active_surface"] = row["active_surface"]
    reference = check_route_rows(list(by_path.values()))
    # Keep the reviewed exception inventory visible; actual assembled inputs
    # are checked independently by the Code3 migration guard.
    assertion_counts = Counter()
    for line in raw.decode("utf-8").splitlines():
        _, path, _, source_line = line.split(":", 3)
        if CODE3_ASSERTIONS.get(path) == source_line.strip():
            assertion_counts[path] += 1
    require(set(assertion_counts) == set(CODE3_ASSERTIONS)
            and all(count == 1 for count in assertion_counts.values()),
            "CODE3_ASSERTION_INVENTORY_DRIFT")
    reference["code3_reviewed_assertions"] = dict(sorted(assertion_counts.items()))
    historical = check_historical_sources(tracked)
    code1_archive = check_code1_archive(root, tracked)
    s5r_lineage = check_s5r_lineage(tracked)
    return {
        "schema": SCHEMA,
        "source_head": actual,
        "source_tree": git(root, "rev-parse", "HEAD^{tree}").decode().strip(),
        "tracked_paths": len(tracked),
        "nonregular_git_entries": nonregular_entries,
        "binary_git_blob_content_scan": "EXCLUDED_BY_GIT_GREP_I_NOT_COUNTED_AS_REGULAR_TEXT",
        "retired_factory": RETIRED,
        "retired_factories": list(RETIRED_FACTORIES),
        "pinned_historical_sources": historical,
        "code1_historical_archive": code1_archive,
        "s5r_lineage": s5r_lineage,
        "code1_source_cut_applied": True,
        "legacy_inputs_supported": False,
        "current_newonly_factory": facts,
        "newonly_ci": ci,
        "reference_audit": {
            **reference,
            "references": sorted(by_path.values(), key=lambda x: x["path"]),
            "scope": "TRACKED_EXACT_TOKEN_ONLY_NO_DYNAMIC_OR_EXTERNAL_CALLER_PROOF",
        },
        "d5_native_ab_source": {
            "A": "6c4eef073038ad69a0710e7c8555b5e03b9ad6ba",
            "B": "c77d2f773eee96c30eeca49d7486fea22ea8e557",
            "ab_verdict": "417_941_P05_SCOPE_ONLY",
            "native_rerun_on_this_head": False,
        },
        "global_dynamic_and_external_consumers": "NOT_INDEPENDENTLY_ATTESTED",
        "science_P3_P4": "NOT_EVALUATED",
        "current_binary_old_input_compatibility": "EXPLICITLY_NOT_REQUIRED",
        "safe_to_delete": False, "merge_to_main": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = audit(args.root, expected_head=args.expected_head)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    except (OSError, ValueError, KeyError, UnicodeError) as exc:
        print("ISSUE774_NEWONLY_RETIREMENT_CI=FAIL:" + str(exc))
        return 1
    print("ISSUE774_NEWONLY_RETIREMENT_CI=PASS_SCOPE_ONLY")
    print("ISSUE774_NEWONLY_GLOBAL_CALLER_ZERO=NOT_ATTESTED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
