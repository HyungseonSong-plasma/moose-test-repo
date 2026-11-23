#!/usr/bin/env python3
"""#774/#811: exact-HEAD retired Factory audit and frozen FDEG provenance.

Source/registration/archival validation only. Does not assert global consumer
zero, legacy input compatibility, P3/P4 physics parity, or release approval.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fvkernel_native_usage_census import source_owners

HISTORY_ROOT = "docs/development/archive/issue774_retired_factories/"
ORIGINALS = {
    "physics_app/src/fvkernels/PhysicsFVThermalDiffusion.C":
        "6887710910c95f37f5f6ed94d4344384b297b4e0",
    "physics_app/include/fvkernels/PhysicsFVThermalDiffusion.h":
        "1845a3c793eefe72b8fbe22ba33df5324da26f36",
    "physics_app/src/fvkernels/PhysicsFVHeavyMassElectromigrationCorrection.C":
        "79bf6045942369bb483ab4e7480a08a5d1040d65",
    "physics_app/include/fvkernels/PhysicsFVHeavyMassElectromigrationCorrection.h":
        "57a56a1e5e3c7297283705b7d2d1dc1acdcd9ff2",
}
PINNED_HISTORICAL_CONSUMERS = {
    "experiments/historical_recipe_support/issue192_s5r.py":
        "be9838b77dc2920b27a1f7065648062b630eacb5",
    "experiments/Issue282_e2a_rz_bridge/research_type_bridge.py":
        "fe82208e49c6f89b127f74fd54cf85cbb91f8fa4",
    "physics_app/ci/audit_issue402_initial_composition_routes.py":
        "858f75f6a64596ccc7386b044fa8278caf8f8b78",
}
FACTORIES = ("PhysicsFVThermalDiffusion",
             "PhysicsFVHeavyMassElectromigrationCorrection")
TOKEN = re.compile(r"\b(?:" + "|".join(FACTORIES) + r")\b")
SHA = re.compile(r"[0-9a-f]{40}\Z")
P6 = {"p6_newonly_s6_build", "p6_newonly_s6_native_p2",
      "p6_public_d_100row_native_p2"}


def need(test: bool, code: str):
    if not test:
        raise ValueError("ISSUE774_MAIN_RETIRE_" + code)


def blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def verify_archive_bytes(archived: dict[str, bytes]):
    """Negative mutation target: a changed historical C/H byte fails."""
    verified = {}
    for rel, expected in ORIGINALS.items():
        archive = HISTORY_ROOT + Path(rel).name + ".txt"
        need(archive in archived and blob(archived[archive]) == expected,
             "HISTORICAL_CPP_BLOB_DRIFT_" + rel)
        need(FACTORIES[0] in archived[archive].decode("utf-8") or
             FACTORIES[1] in archived[archive].decode("utf-8"),
             "HISTORICAL_FACTORY_IDENTITY_MISSING_" + rel)
        verified[rel] = {"archive": archive, "blob_sha": expected,
                         "content_bytes": len(archived[archive])}
    return verified


def live_surface(path: str):
    """Narrow active current-binary consumer surfaces, never a global claim."""
    if path in PINNED_HISTORICAL_CONSUMERS:
        return None
    if path.endswith(".i"):
        return "MOOSE_INPUT"
    if path.startswith(("physics_app/src/", "physics_app/include/")) and \
            path.endswith((".C", ".h", ".cc", ".hpp")):
        return "PHYSICS_CPP"
    if path.startswith((".github/workflows/", "ci/workflow_templates/")) and \
            path.endswith((".yml", ".yaml")):
        return "LIVE_WORKFLOW"
    if path.startswith(("experiments/", "physics_app/ci/", "scripts/")) and \
            path.endswith((".py", ".json", ".sh")):
        return "RUNTIME_GENERATOR"
    return None


def check_inventory(rows: list[dict], paths: set[str]):
    need(all(path not in paths for path in ORIGINALS), "RETIRED_CPP_REINTRODUCED")
    need(len(rows) == 11, "FV_SOURCE_COUNT_NOT_ELEVEN")
    seen = [name for row in rows for name in row["registered_factory_types"]]
    need(len(seen) == 16 and len(set(seen)) == 16 and
         not set(FACTORIES).intersection(seen), "FV_FACTORY_COUNT_NOT_SIXTEEN")
    counts = {x["source_file"]: len(x["registered_factory_types"]) for x in rows}
    need(counts.get("physics_app/src/fvkernels/PhysicsFVLogMolarElectronTransport.C") == 4,
         "ELECTRON_SHARED_OWNER_COUNT_DRIFT")
    need(counts.get("physics_app/src/fvkernels/FVLogMolarTransport.C") == 3,
         "GENERIC_SHARED_OWNER_COUNT_DRIFT")
    return {"source_files": len(rows), "registered_factory_types": len(seen)}


def audit(root: Path, expected_head: str):
    root = root.resolve()
    need(bool(SHA.fullmatch(expected_head)), "EXPECTED_HEAD_NOT_SHA")
    actual = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    need(actual == expected_head, "EXACT_HEAD_MISMATCH")
    tree = subprocess.check_output(
        ["git", "-C", str(root), "ls-tree", "-r", "HEAD"], text=True)
    paths = {}
    for line in tree.splitlines():
        metadata, path = line.split("\t", 1)
        mode, kind, sha = metadata.split()
        need(path not in paths, "DUPLICATE_TREE_PATH")
        paths[path] = (mode, kind, sha)
    need(all(path not in paths for path in ORIGINALS),
         "RETIRED_CPP_REINTRODUCED")
    archived = {}
    for name in ORIGINALS:
        rel = HISTORY_ROOT + Path(name).name + ".txt"
        need(rel in paths and paths[rel][1] == "blob", "ARCHIVE_FILE_MISSING")
        data = (root / rel).read_bytes()
        need(blob(data) == paths[rel][2], "ARCHIVE_WORKTREE_DIRTY")
        archived[rel] = data
    original_receipts = verify_archive_bytes(archived)
    for path, sha in PINNED_HISTORICAL_CONSUMERS.items():
        need(path in paths and paths[path][2] == sha,
             "HISTORICAL_CONSUMER_NOT_PINNED_" + path)
    rows = source_owners(root / "physics_app/src/fvkernels")
    for row in rows:
        p = row["source_file"]
        need(p in paths and row["source_blob_sha"] == paths[p][2],
             "EXACT_FACTORY_SOURCE_NOT_CHECKED_OUT_" + p)
    counts = check_inventory(rows, set(paths))
    actual_sources = []
    for rel, (mode, kind, sha) in paths.items():
        if kind != "blob" or live_surface(rel) is None:
            continue
        raw = (root / rel).read_bytes()
        need(blob(raw) == sha, "ACTIVE_SOURCE_DIRTY_" + rel)
        if TOKEN.search(raw.decode("utf-8", errors="replace")):
            actual_sources.append({"path": rel, "category": live_surface(rel)})
    need(not actual_sources, "RETIRED_FACTORY_ACTIVE_SOURCE_REFERENCE_" +
         ",".join(x["path"] for x in actual_sources[:5]))
    native = (root / ".github/workflows/physics-native-ci.yml").read_text()
    code = (root / ".github/workflows/physics-code-ci.yml").read_text()
    general = (root / ".github/workflows/ci.yml").read_bytes()
    template = (root / "ci/workflow_templates/general-ci.yml").read_bytes()
    need(general == template, "GENERAL_CI_TEMPLATE_DRIFT")
    need("\njobs:\n" in native, "NATIVE_JOBS_MISSING")
    jobs = set(re.findall(r"(?m)^  ([a-z][a-z0-9_-]*):\s*$",
                          native.split("\njobs:\n", 1)[1]))
    need(P6 <= jobs and "issue541_arch_dd_native_p2" in jobs and
         "issue402_core_four_native_p2" in jobs,
         "P6_OR_ARCH_RETAINED_NATIVE_REMOVED")
    need("issue541_arch_s6_hybrid_native_p2" not in jobs,
         "RETIRED_ARCH_DUPLICATE_JOB_RETURNED")
    need("issue774_main_retirement.py" in code and
         "fdeg_retirement_evidence.py --mode capture --target" not in code,
         "FDEG_POST_CUT_CI_STILL_CAPTURES_REMOVED_CPP")
    return {
        "schema": "issue774.main_thermal_heavy_retirement.v0.1",
        "source_head": actual,
        "source_tree": subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD^{tree}"],
            text=True).strip(),
        "deleted_factories": list(FACTORIES),
        "historical_original_blobs": original_receipts,
        "historical_consumer_blobs": PINNED_HISTORICAL_CONSUMERS,
        "current_newonly": counts,
        "current_active_retired_symbol_references": actual_sources,
        "core_and_split_native_ci_preserved": True,
        "p3_p4_scientific_parity": "NOT_EVALUATED",
        "global_external_callers_zero": "NOT_ATTESTED",
        "old_binary_input_compatibility": "EXPLICITLY_NOT_REQUIRED",
        "release_authorization": "INDEPENDENT_REVIEW_HOLD",
    }


def self_test():
    names = [HISTORY_ROOT + Path(p).name + ".txt" for p in ORIGINALS]
    source = {n: (ROOT / n).read_bytes() for n in names}
    verify_archive_bytes(source)
    for name in names:
        broken = dict(source)
        broken[name] = broken[name] + b"\n# modified historical evidence\n"
        try:
            verify_archive_bytes(broken)
        except ValueError:
            pass
        else:
            raise AssertionError("ARCHIVE_MUTATION_UNDETECTED_" + name)
    need(live_surface("experiments/newonly/reintroduced.i") == "MOOSE_INPUT",
         "INPUT_CONSUMER_CLASSIFIER_LOST")
    need(live_surface("physics_app/src/fvkernels/NewSource.C") == "PHYSICS_CPP",
         "CPP_CONSUMER_CLASSIFIER_LOST")
    need(live_surface("experiments/historical_recipe_support/issue192_s5r.py") is None,
         "ARCHIVE_RESEARCH_EXCEPTION_LOST")
    try:
        check_inventory([], set())
    except ValueError:
        pass
    else:
        raise AssertionError("MISSING_SOURCE_INVENTORY_ACCEPTED")
    print("ISSUE774_MAIN_RETIRE_ARCHIVE_AND_CONSUMER_NEGATIVES_PASS")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--expected-head", required=True)
    ap.add_argument("--output-dir", type=Path)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    try:
        if args.self_test:
            self_test()
        result = audit(ROOT, args.expected_head)
        if args.output_dir:
            args.output_dir.mkdir(parents=True, exist_ok=True)
            (args.output_dir / "manifest.json").write_text(
                json.dumps(result, sort_keys=True, indent=2) + "\n")
        print("ISSUE774_MAIN_RETIRE_FACTORY_P0_PASS")
        print("ISSUE774_MAIN_RETIRE_P3_P4_SCIENCE_HOLD")
    except (OSError, ValueError, AssertionError, subprocess.CalledProcessError) as exc:
        print("ISSUE774_MAIN_RETIRE_FACTORY_P0_FAIL", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
