#!/usr/bin/env python3
"""#8-A-2 FLOW retirement safety: two original blobs, independent P0/P1/P2 owners.

This checks a pinned historical snapshot plus current candidate files; it does
not certify external caller-zero, GitHub CI success, P3, or science acceptance.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEDGER = Path("ci/baselines/issue541_group_a2_flow_retirement.json")
NATIVE = Path(".github/workflows/issue402-flow-native-p2-regression.yml")
CI = Path(".github/workflows/physics-legacy-audit.yml")
HISTORICAL_CI = Path(".github/workflows/ci.yml")
GUARD = Path("ci/guards/workflow_surface_guard.py")
PIN = "71e112eb05d4645c82aab8861b99d6952ac4ac3e"
DONOR = "d4c5ab58895fe300638fb406a22d0a5f5e06fb49"
OCI = "sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008"
CASES = {
    "A3": {
        "path": ".github/workflows/issue402-rate-coef-ideal-gas-native-once.yml",
        "blob": "64164c097ec8f7831e67b80b317144cd97ba9ee8",
        "branch": "issue-402-rate-coef-ideal-gas",
        "source_sha": "b5aee181c12375d6d2b94cd9a1ff6011943c5370",
        "run": 43464123958,
        "artifact": (14058320821, 1426,
                     "85fb89e0dda2f11fbfea10de2bf964e0b75a9f02f0b52e4fd3823fd759b03c9c"),
        "p0_job": "issue402_ideal_gas_p0",
        "p0_job_id": 132837420423,
    },
    "A4": {
        "path": ".github/workflows/issue402-reaction-material-reduction-p0-once.yml",
        "blob": "5e433b5c56f335808e6a5cbaa771b808eef1ad45",
        "branch": "issue-402-species-functor-naming",
        "source_sha": "238ca2017be6dc24303fca166c0b0f0ed24d4773",
        "run": 43428302896,
        "artifact": None,
        "p0_job": "issue402_reaction_material_p0",
        "p0_job_id": 132837420455,
    },
}


def require(ok: bool, why: str) -> None:
    if not ok:
        raise ValueError(why)


def blob_sha(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def job_content(ci: str, name: str) -> str:
    pattern = r"(?ms)^  " + re.escape(name) + r":\s*\n(.*?)(?=^  [A-Za-z0-9_-]+:\s*$|\Z)"
    match = re.search(pattern, ci)
    require(match is not None, "MISSING_P0_JOB:" + name)
    return match.group(1)


def verify(m: dict, archive: dict[str, bytes], ci: str, native: str,
           surface: str, *, live_branch: str | None = None,
           active_caller: str | None = None,
           original_present: str | None = None) -> None:
    require(m["schema"] == "issue541.group_a2.flow_two_retirement.v1", "SCHEMA")
    owner = m["authority"]
    require(owner == {
        "repo": "HyungseonSong-plasma/moose-test-repo",
        "issue_retirement": 535, "issue_coordination": 541,
        "group": "A-2", "package": "FLOW", "donor_pr": 548,
        "donor_head": DONOR, "baseline_main": PIN,
    }, "AUTHORITY_OR_BASE_CHANGED")
    require(len(m["workflows"]) == 2 and
            {x["id"] for x in m["workflows"]} == set(CASES),
            "MISSING_OR_DUPLICATED_OWNER")
    consumers = m["consumers"]
    require(consumers["original_events"] == "PUSH_SELF_PATH_ONLY" and
            consumers["branch_observation"] == "BOTH_ABSENT_ON_2026_11_16" and
            consumers["default_branch_code_search"] == "ORIGINAL_YAML_ONLY" and
            consumers["external_dynamic_caller_zero"] == "NOT_PROVEN",
            "CALLER_PROOF_OVERCLAIMED")
    for key in ("declared_dispatch", "declared_reusable", "declared_schedule",
                "declared_workflow_run"):
        require(consumers[key] is False, "DECLARED_CALLER:" + key)
    require(live_branch is None and active_caller is None,
            "ACTIVE_BRANCH_OR_CALLER_REQUIRES_REINVESTIGATION")
    routes = m["replacement_route"]
    require(routes["ci"] == str(HISTORICAL_CI) and routes["native"] == str(NATIVE) and
            routes["oci"] == OCI and routes["archive_checkout_sha"] == PIN and
            routes["historical_public_source"] ==
            "29d1acc6ef7969908b86719e4b95c73a1565136d",
            "REPLACEMENT_PROVENANCE")
    require("on:\n  pull_request:\n    branches: [main]" in native and
            "\n  workflow_dispatch:" in native and "\n  push:" not in native,
            "REPLACEMENT_NOT_GOVERNED")
    for mark in ("FLOW_NATIVE_SOURCE_BOUND_P1_PASS",
                 "FLOW_IDEAL_GAS_DIRECT_MATERIAL_NATIVE_P2_PASS",
                 "FLOW_EI10_EI16_FOUR_FIXTURE_NATIVE_P2_PASS",
                 "FLOW_DBASE_LEGACY_P2_RETIRED_NEWONLY_P05_OWNS_417_941",
                 "ref: " + PIN, OCI,
                 "issue541_group_a2_flow_retirement_p0.py --self-test --check"):
        require(mark in native, "REPLACEMENT_NATIVE_OBLIGATION_REMOVED:" + mark)
    require("FLOW_PINNED_DBASE_417_941_NATIVE_P2_PASS" not in native and
            "run_chemistry_s6_p2_only.py" not in native,
            "RETIRED_FLOW_DBASE_REINTRODUCED")
    require("ONE_SHOT_NAME" in surface and "FORBIDDEN_EVENTS" in surface and
            "branches: [main]" in surface, "GLOBAL_GUARD_WEAKENED")

    for item in m["workflows"]:
        key = item["id"]
        expected = CASES[key]
        old = item["original"]
        require(old["path"] == expected["path"] and old["blob"] == expected["blob"] and
                old["branch"] == expected["branch"] and
                old["source_sha"] == expected["source_sha"] and
                old["run_id"] == expected["run"] and old["result"] == "success",
                "HISTORICAL_IDENTITY:" + key)
        require(original_present != key, "OLD_WORKFLOW_REINTRODUCED:" + key)
        original = archive[expected["path"]]
        require(blob_sha(original) == expected["blob"], "HISTORICAL_BYTES_CHANGED:" + key)
        header = original.decode("utf-8").split("permissions:", 1)[0]
        require("on:\n  push:\n    branches: [" + expected["branch"] +
                "]\n    paths: [" + expected["path"] + "]" in header,
                "HISTORICAL_TRIGGER_CHANGED:" + key)
        require(not any(re.search(r"(?m)^  " + x + r":", header)
                        for x in ("workflow_dispatch", "workflow_call",
                                  "workflow_run", "repository_dispatch",
                                  "schedule", "pull_request")),
                "OLD_ACTIVE_EVENT:" + key)
        artifact = expected["artifact"]
        if artifact is None:
            require(old["artifact"] is None, "INVENTED_ORIGINAL_ARTIFACT:" + key)
        else:
            a = old["artifact"]
            require((a["id"], a["bytes"], a["sha256"]) == artifact and
                    a["preservation"] ==
                    "PRIVATE_OWNER_READBACK_REPORTED_PR548_NOT_REHASHED_HERE",
                    "ARTIFACT_CUSTODY_CHANGED:" + key)
        replacement = item["replacement"]
        require(replacement["ci_job"] == expected["p0_job"] and
                replacement["p0_run"] == 43722538508 and
                replacement["p0_job"] == expected["p0_job_id"] and
                replacement["p0_result"] == "success",
                "P0_RECEIPT_CHANGED:" + key)
        body = job_content(ci, expected["p0_job"])
        require("github.event.pull_request.head.sha || github.sha" in body,
                "P0_NOT_EXACT_SOURCE:" + key)
        require("--self-test" in body and "--check" in body,
                "P0_NEGATIVE_CHECK_REMOVED:" + key)
        for path in replacement["required_p0_tests"]:
            require(path in body, "P0_TEST_DROPPED:" + key + ":" + path)
        for command in replacement["required_p0_checkers"]:
            require(command in body, "P0_CHECKER_DROPPED:" + key + ":" + command)
        if key == "A3":
            require(replacement["native_run"] == 43722538507 and
                    replacement["native_job"] == "flow-native-p2" and
                    replacement["native_job_id"] == 132837420226 and
                    replacement["native_artifact"] == 14165840230 and
                    replacement["native_result"] == "success" and
                    set(replacement["required_native_markers"]) ==
                    {"FLOW_NATIVE_SOURCE_BOUND_P1_PASS",
                     "FLOW_IDEAL_GAS_DIRECT_MATERIAL_NATIVE_P2_PASS"},
                    "NATIVE_SOURCE_RECEIPT_CHANGED")
        else:
            require(replacement["native_job"] is None and
                    replacement["native_run"] is None and
                    replacement["native_artifact"] is None and
                    replacement["native_result"] == "NOT_REQUIRED_ORIGINAL_P0_ONLY",
                    "P0_ORIGINAL_WRONGLY_PROMOTED_TO_NATIVE")
        require(item["decision"] == "STAGED_DELETE_KEEP_HOLD_INTEGRATION",
                "PREMATURE_RETIREMENT:" + key)
    gate = m["integration"]
    require(gate["status"] == "PENDING_CONFLICT_FREE_EXACT_HEAD_REVIEW_AND_CI" and
            gate["no_auto_merge"] is True and gate["no_global_guard_waiver"] is True and
            gate["no_original_retarget"] is True and
            gate["rollback"] == "RESTORE_EACH_PINNED_ORIGINAL_GIT_BLOB",
            "INTEGRATION_GATES_WEAKENED")
    safety = m["safety"]
    require(safety == {"P3": "NOT_RUN", "P4": "NOT_RUN",
                       "SCIENCE": "SCIENCE_HOLD",
                       "ARCH_P3_ORIGINALS": "KEEP_HOLD"},
            "SCIENCE_OR_ARCH_HOLD_PROMOTION")


def self_test(m: dict, archives: dict[str, bytes], ci: str,
              native: str, surface: str) -> None:
    verify(m, archives, ci, native, surface)
    count = 0

    def reject(label: str, changed: dict, old: dict[str, bytes] = archives,
               test_ci: str = ci, test_native: str = native,
               test_surface: str = surface, **kwargs: str) -> None:
        nonlocal count
        try:
            verify(changed, old, test_ci, test_native, test_surface, **kwargs)
        except (ValueError, KeyError):
            count += 1
            return
        raise AssertionError("MUTATION_FALSE_PASS:" + label)

    for case in CASES:
        reject("ACTIVE_BRANCH_" + case, m, live_branch=case)
        reject("LIVE_CALLER_" + case, m, active_caller=case)
        reject("REINTRODUCED_" + case, m, original_present=case)
        altered = copy.deepcopy(m)
        record = next(x for x in altered["workflows"] if x["id"] == case)
        record["decision"] = "RETIRED_VERIFIED"
        reject("PREMATURE_ACCEPTANCE_" + case, altered)
        altered = copy.deepcopy(m)
        record = next(x for x in altered["workflows"] if x["id"] == case)
        record["original"]["blob"] = "0" * 40
        reject("HISTORICAL_BLOB_FORGERY_" + case, altered)
        altered = copy.deepcopy(archives)
        altered[CASES[case]["path"]] += b"\n# modified"
        reject("HISTORICAL_BYTES_" + case, m, old=altered)
        record = next(x for x in m["workflows"] if x["id"] == case)
        test = record["replacement"]["required_p0_tests"][0]
        scoped = job_content(ci, CASES[case]["p0_job"])
        require(test in scoped, "SELFTEST_FIXTURE_MISSING:" + case)
        scoped_bad = scoped.replace(test, "REMOVED_HISTORICAL_TEST", 1)
        reject("DROPPED_TEST_" + case, m,
               test_ci=ci.replace(scoped, scoped_bad, 1))
    bad = copy.deepcopy(m)
    bad["consumers"]["declared_dispatch"] = True
    reject("DECLARED_DISPATCH", bad)
    bad = copy.deepcopy(m)
    bad["consumers"]["external_dynamic_caller_zero"] = "PROVEN"
    reject("FABRICATED_CALLER_ZERO", bad)
    bad = copy.deepcopy(m)
    bad["workflows"].pop()
    reject("MISSING_WORKFLOW", bad)
    bad = copy.deepcopy(m)
    bad["safety"]["P3"] = "PASS"
    reject("P3_PROMOTION", bad)
    bad = copy.deepcopy(m)
    bad["workflows"][0]["original"]["artifact"]["sha256"] = "0" * 64
    reject("ARTIFACT_FORGERY", bad)
    reject("NEW_PUSH", m,
           test_native=native.replace("  pull_request:", "  push:", 1))
    reject("LOST_REAL_NATIVE", m,
           test_native=native.replace("FLOW_IDEAL_GAS_DIRECT_MATERIAL_NATIVE_P2_PASS",
                                      "REMOVED_NATIVE_MARKER", 1))
    reject("GUARD_BYPASS", m,
           test_surface=surface.replace("ONE_SHOT_NAME", "REMOVED_GUARD_OWNER"))
    print(f"ISSUE541_GROUP_A2_NEGATIVE_MUTATIONS_{count}_REJECTED")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not (args.self_test or args.check):
        parser.error("specify --self-test or --check")
    try:
        m = json.loads((ROOT / LEDGER).read_text(encoding="utf-8"))
        historic = ROOT.parent / "retired_workflow_archive"
        archives = {spec["path"]: (historic / spec["path"]).read_bytes()
                    for spec in CASES.values()}
        ci = (ROOT / CI).read_text(encoding="utf-8")
        native = (ROOT / NATIVE).read_text(encoding="utf-8")
        surface = (ROOT / GUARD).read_text(encoding="utf-8")
        presence = next((key for key, spec in CASES.items()
                         if (ROOT / spec["path"]).exists()), None)
        if presence is not None:
            raise ValueError("ORIGINAL_REINTRODUCED:" + presence)
        if args.self_test:
            self_test(m, archives, ci, native, surface)
        if args.check:
            verify(m, archives, ci, native, surface)
            print("ISSUE541_GROUP_A2_FLOW_P0_PASS; BOTH_STAGED_DELETE; "
                  "GLOBAL_SURFACE_GUARD_NOT_WAIVED; SCIENCE_HOLD; "
                  "INTEGRATED_HEAD_AND_CALLER_PROOF_PENDING")
    except (KeyError, ValueError, AssertionError, OSError, UnicodeError) as exc:
        print("ISSUE541_GROUP_A2_FLOW_P0_FAIL:", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
