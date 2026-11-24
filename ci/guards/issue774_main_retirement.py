#!/usr/bin/env python3
"""#774/#817/#713: exact-HEAD six retired Factory audit and frozen FDEG provenance.

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
    "physics_app/src/fvkernels/FVElectronResponseBandedCorrection.C":
        "1e58703a7794ddd8eed3cba28ed9e5a1e39a141f",
    "physics_app/include/fvkernels/FVElectronResponseBandedCorrection.h":
        "9446a9d5d7863fb83a2c65af8b127bbd08573ad6",
    "physics_app/src/fvkernels/PhysicsFVElectronEnergyJouleHeating.C":
        "07ecd234871c659b04389c87bff6f52fae7f800e",
    "physics_app/include/fvkernels/PhysicsFVElectronEnergyJouleHeating.h":
        "1d2afa9ba448041c664fdc1822ede5472b93551e",
    "physics_app/src/fvkernels/PhysicsFVElectronReactionSource.C":
        "35ded0eab65ad7bed85baa0104261c90bc26bf3d",
    "physics_app/include/fvkernels/PhysicsFVElectronReactionSource.h":
        "5250b3500d6694481158e2abb896c7e1c6f349e9",
    "physics_app/src/fvkernels/PhysicsFVElectrostaticDrift.C":
        "8d61a535b4e0fbf0a008fabb98d45e723affe999",
    "physics_app/include/fvkernels/PhysicsFVElectrostaticDrift.h":
        "db061f6b5fd3e82039f6e1bb887a944603052c09",
}
PINNED_HISTORICAL_CONSUMERS = {
    "experiments/Issue282_e2a_rz_bridge/research_type_bridge.py":
        "fe82208e49c6f89b127f74fd54cf85cbb91f8fa4",
    "physics_app/ci/audit_issue402_initial_composition_routes.py":
        "858f75f6a64596ccc7386b044fa8278caf8f8b78",
    "experiments/fem_fvm_plasma_discriminator/prepare_cases.py":
        "69ec14c58b502a953c9024c46d332494cad61e6c",
    "experiments/Issue351_frozen_heavy_driver_parity/control.py":
        "6d7efcb4ea94b2011782aba2c9cab40238756312",
}
FACTORIES = ("PhysicsFVThermalDiffusion",
             "PhysicsFVHeavyMassElectromigrationCorrection",
             "PhysicsFVElectronEnergyJouleHeating",
             "FVElectronResponseBandedCorrection",
             "PhysicsFVElectronReactionSource",
             "PhysicsFVElectrostaticDrift")
CODE3 = FACTORIES[4]
CODE4 = FACTORIES[5]
S5R = "experiments/historical_recipe_support/issue192_s5r.py"
JOULE_SMOKE = "physics_app/ci/electron_energy_joule_smoke.i"
PINNED_PROVENANCE = {
    "ci/baselines/fdeg_functional_contracts.json": "6f1a2948a852a9de9045e74fda72c99d105378aa",
    "ci/baselines/fdeg_transition_contracts.json": "1bd17e05f17e8ac5942b946dfd45f6d023f1403f",
    "ci/baselines/fdeg_historical_profiles_code1.json": "9a8b0d60a9511fe089ef6cb3d900f902123ee742",
    "docs/provenance/issue814_code2/electron_energy_joule_smoke.i.txt": "6c4901f843a98b74b450cc3a1fab09e8e1873b2c",
    "docs/provenance/issue817_code3/issue192_s5r_pre_migration.py.txt": "be9838b77dc2920b27a1f7065648062b630eacb5",
    S5R: "7dc29e5773b145d9f052d9898901eec61c904344",
}
CODE3_ASSERTIONS = {
    "physics_app/ci/check_r2_o2_ionization_implementation.py":
        'assert "type = PhysicsFVElectronReactionSource" not in RUNTIME_INPUT',
    "physics_app/ci/check_stage5_s5r_preflight.py":
        'if h05_row.get("electron_particle_projection") != "PhysicsFVElectronReactionSource":',
    "physics_app/ci/check_e8_ei16_energy_contract.py":
        'assert own["electron_particle_projector"] == "PhysicsFVElectronReactionSource"',
    "physics_app/ci/check_e8_elastic_ei19_runtime.py":
        '"PhysicsFVElectronReactionSource",',
    "physics_app/ci/check_stage5_ei18_runtime.py":
        'if "PhysicsFVElectronReactionSource" in text:',
    "physics_app/ci/check_stage5_s5d_heavy_reactions.py":
        '"reaction_source_", "PhysicsFVElectronReactionSource",',
}
# Exact historical construction/projection/assertion lines, not a current
# runtime compatibility waiver. Entire blobs are pinned.
CODE4_HISTORICAL = {
    S5R: (
        "7dc29e5773b145d9f052d9898901eec61c904344",
        ('"FVKernels/n_e_drift": "PhysicsFVElectrostaticDrift",',
         'f"FVKernels/{species}_electrostatic_drift": "PhysicsFVElectrostaticDrift"'),
    ),
    "experiments/Issue282_e2a_rz_bridge/research_type_bridge.py": (
        "fe82208e49c6f89b127f74fd54cf85cbb91f8fa4",
        ('"QPXFVElectrostaticDrift": "PhysicsFVElectrostaticDrift",',),
    ),
    ".github/scripts/issue213_wall_drift.py": (
        "b72a785760276508926bacb343ed6b8a0771c63a",
        ('== "PhysicsFVElectrostaticDrift",',),
    ),
    "experiments/Issue27_surface_reactions/controlled_wall/issue215_sheath_particle_core.py": (
        "10c83ef8dcaf0e8efa60a96508da2da872d3a7cc",
        ('== "PhysicsFVElectrostaticDrift",',),
    ),
}
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
        need(any(factory in archived[archive].decode("utf-8") for factory in FACTORIES),
             "HISTORICAL_FACTORY_IDENTITY_MISSING_" + rel)
        verified[rel] = {"archive": archive, "blob_sha": expected,
                         "content_bytes": len(archived[archive])}
    return verified


def live_surface(path: str):
    """Narrow active current-binary consumer surfaces, never a global claim."""
    if path.endswith(".i"):
        return "MOOSE_INPUT"
    if path.startswith(("physics_app/src/", "physics_app/include/")) and \
            path.endswith((".C", ".h", ".cc", ".hpp")):
        return "PHYSICS_CPP"
    if path.startswith((".github/workflows/", "ci/workflow_templates/")) and \
            path.endswith((".yml", ".yaml")):
        return "LIVE_WORKFLOW"
    if path.startswith(("experiments/", "physics_app/ci/", "scripts/", "automation/")) and \
            path.endswith((".py", ".json", ".sh")):
        return "RUNTIME_GENERATOR"
    return None


def code4_surface(path: str):
    if path.startswith(".github/scripts/") and path.endswith((".py", ".sh", ".json")):
        return "RUNTIME_GENERATOR"
    return live_surface(path)


def reference_surface(path: str, line: str):
    tokens = set(TOKEN.findall(line))
    if CODE4 in tokens:
        if tokens == {CODE4} and line.strip() in CODE4_HISTORICAL.get(path, ("", ()))[1]:
            return None
        return code4_surface(path)
    if path == S5R and tokens == {FACTORIES[1]}:
        return None  # original and migrated blobs pinned independently
    if tokens == {CODE3} and CODE3_ASSERTIONS.get(path) == line.strip():
        return None
    if path in PINNED_HISTORICAL_CONSUMERS and CODE3 not in tokens:
        return None  # complete reviewed blob checked by audit
    return live_surface(path)


def check_inventory(rows: list[dict], paths: set[str]):
    need(all(path not in paths for path in ORIGINALS), "RETIRED_CPP_REINTRODUCED")
    need(len(rows) == 7, "FV_SOURCE_COUNT_NOT_SEVEN")
    seen = [name for row in rows for name in row["registered_factory_types"]]
    need(len(seen) == 12 and len(set(seen)) == 12 and
         not set(FACTORIES).intersection(seen), "FV_FACTORY_COUNT_NOT_TWELVE")
    counts = {x["source_file"]: len(x["registered_factory_types"]) for x in rows}
    need(counts.get("physics_app/src/fvkernels/PhysicsFVLogMolarElectronTransport.C") == 4,
         "ELECTRON_SHARED_OWNER_COUNT_DRIFT")
    need(counts.get("physics_app/src/fvkernels/FVLogMolarTransport.C") == 3,
         "GENERIC_SHARED_OWNER_COUNT_DRIFT")
    return {"source_files": len(rows), "registered_factory_types": len(seen)}


def verify_post_cut_fdeg_capture(workflow: str):
    """Accept retained shared electron FDEG; refuse capture of all retired Factories."""
    stem = "fdeg_retirement_evidence.py --mode capture --target "
    live_target = stem + "PhysicsFVLogMolarElectronReactionSource"
    need("issue774_main_retirement.py" in workflow and
         live_target in workflow and
         all(stem + factory not in workflow for factory in FACTORIES),
         "FDEG_POST_CUT_CI_STILL_CAPTURES_REMOVED_CPP")


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
    for path, sha in {**PINNED_HISTORICAL_CONSUMERS, **PINNED_PROVENANCE}.items():
        need(path in paths and paths[path][2] == sha,
             "HISTORICAL_CONSUMER_NOT_PINNED_" + path)
        need(blob((root / path).read_bytes()) == sha, "HISTORICAL_WORKTREE_DIRTY_" + path)
    for path, (expected, lines) in CODE4_HISTORICAL.items():
        need(path in paths and paths[path][2] == expected,
             "CODE4_HISTORICAL_BLOB_DRIFT_" + path)
        raw = (root / path).read_bytes()
        need(blob(raw) == expected, "CODE4_HISTORICAL_WORKTREE_DIRTY_" + path)
        actual_lines = [line.strip() for line in raw.decode("utf-8").splitlines()
                        if CODE4 in TOKEN.findall(line)]
        need(sorted(actual_lines) == sorted(lines), "CODE4_HISTORICAL_LINE_DRIFT_" + path)
    need(JOULE_SMOKE not in paths, "RETIRED_JOULE_SMOKE_REINTRODUCED")
    rows = source_owners(root / "physics_app/src/fvkernels")
    for row in rows:
        p = row["source_file"]
        need(p in paths and row["source_blob_sha"] == paths[p][2],
             "EXACT_FACTORY_SOURCE_NOT_CHECKED_OUT_" + p)
    counts = check_inventory(rows, set(paths))
    actual_sources = []
    reviewed_assertions = {path: 0 for path in CODE3_ASSERTIONS}
    for rel, (mode, kind, sha) in paths.items():
        if kind != "blob" or code4_surface(rel) is None:
            continue
        raw = (root / rel).read_bytes()
        need(blob(raw) == sha, "ACTIVE_SOURCE_DIRTY_" + rel)
        for line in raw.decode("utf-8", errors="replace").splitlines():
            if not TOKEN.search(line):
                continue
            if live_surface(rel) is None and CODE4 not in TOKEN.findall(line):
                continue  # preserve earlier retired-owner audit scope
            if CODE3_ASSERTIONS.get(rel) == line.strip():
                reviewed_assertions[rel] += 1
            surface = reference_surface(rel, line)
            if surface is not None:
                actual_sources.append({"path": rel, "category": surface})
    need(all(count == 1 for count in reviewed_assertions.values()),
         "CODE3_ASSERTION_INVENTORY_DRIFT")
    need(not actual_sources, "RETIRED_FACTORY_ACTIVE_SOURCE_REFERENCE_" +
         ",".join(x["path"] for x in actual_sources[:5]))
    grep = subprocess.run(
        ["git", "-C", str(root), "grep", "-n", "-I", "-w", "-e", CODE4, "HEAD", "--"],
        text=True, capture_output=True)
    need(grep.returncode in (0, 1), "CODE4_TRACKED_TOKEN_INVENTORY_FAILED")
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
    verify_post_cut_fdeg_capture(code)
    return {
        "schema": "issue774.main_combined_retirement.v0.3",
        "source_head": actual,
        "source_tree": subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD^{tree}"],
            text=True).strip(),
        "deleted_factories": list(FACTORIES),
        "historical_original_blobs": original_receipts,
        "historical_consumer_blobs": PINNED_HISTORICAL_CONSUMERS,
        "pinned_provenance_blobs": PINNED_PROVENANCE,
        "reviewed_code3_assertions": reviewed_assertions,
        "code4_historical_references": CODE4_HISTORICAL,
        "code4_exact_tracked_text_inventory": grep.stdout.splitlines(),
        "current_newonly": counts,
        "current_active_retired_symbol_references": actual_sources,
        "core_and_split_native_ci_preserved": True,
        "p3_p4_scientific_parity": "NOT_EVALUATED",
        "global_external_callers_zero": "NOT_ATTESTED",
        "old_binary_input_compatibility": "THERMAL_WAIVER_ONLY_OTHER_SCOPE_HOLD",
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
    need(reference_surface(S5R, "type = " + FACTORIES[1]) is None,
         "PINNED_S5R_RESEARCH_EXCEPTION_LOST")
    need(reference_surface(S5R, "type = " + CODE3) is not None,
         "S5R_CODE3_REINTRODUCTION_ACCEPTED")
    for path, assertion in CODE3_ASSERTIONS.items():
        need(reference_surface(path, assertion) is None, "ASSERTION_CLASSIFIER_LOST")
        need(reference_surface(path, "type = " + CODE3) is not None,
             "ACTIVE_CODE3_REINTRODUCTION_ACCEPTED")
    for path, (_, lines) in CODE4_HISTORICAL.items():
        for line in lines:
            need(reference_surface(path, line) is None, "CODE4_PINNED_LINE_REJECTED")
        need(reference_surface(path, "type = " + CODE4) is not None,
             "CODE4_NEW_CONSUMER_ACCEPTED")
    need(reference_surface(".github/scripts/new_consumer.py", "type = " + CODE4)
         == "RUNTIME_GENERATOR", "CODE4_SCRIPT_SCOPE_LOST")
    need(reference_surface("experiments/newonly/reintroduced.i", "type = " + CODE4)
         == "MOOSE_INPUT", "CODE4_INPUT_SCOPE_LOST")
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
