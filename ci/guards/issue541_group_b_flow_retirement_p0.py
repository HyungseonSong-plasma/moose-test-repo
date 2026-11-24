#!/usr/bin/env python3
"""Fail-closed retirement gate for Issue 541 Group B FLOW Native one-shot.

P0 evidence is distinct from source-matched real P1/P2 and scientific P3.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REL = ".github/workflows/issue402-reaction-reduction-native-once.yml"
REPLACEMENT = ".github/workflows/issue402-flow-native-p2-regression.yml"
MANIFEST = "ci/baselines/issue541_group_b_flow_reaction_retirement.json"
OLD_BLOB = "91313152e7e7df3bd0256a2180f489774cfa6171"
OLD_REF = "71e112eb05d4645c82aab8861b99d6952ac4ac3e"
OLD_ARTIFACT_SHA = "95eca7994c105347a8948f9b06852ac3929eaddb9781cc01bad00ca31c88397b"
OCI_DIGEST = "sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008"


def require(ok: bool, label: str) -> None:
    if not ok:
        raise ValueError(label)


def blob_sha(text: str) -> str:
    raw = text.encode("utf-8")
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def verify(m: dict, original: str, maintained: str, surface: str,
           *, historical_branch_live: bool = False,
           original_present_in_candidate: bool = False) -> None:
    require(m["schema"] == "issue541.group_b.flow_native_retirement.v1", "SCHEMA")
    own = m["authority"]
    require(own["repo"] == "HyungseonSong-plasma/moose-test-repo" and
            own["package"] == "FLOW" and own["group"] == "B" and
            own["issue_retirement"] == 535 and own["issue_coordination"] == 541,
            "OWNER")
    old = m["original"]
    require(old["path"] == REL and old["git_blob_sha"] == OLD_BLOB and
            old["ref"] == "main@" + OLD_REF, "ORIGINAL_ID")
    require(blob_sha(original) == OLD_BLOB, "ORIGINAL_BYTES_CHANGED")
    require(old["event"] == "push" and
            old["branch"] == "issue-402-species-functor-naming" and
            old["branch_observation"] == "ABSENT_ON_2026_11_16" and
            old["path_filter"] == "MULTI_PATH_SOURCE_AND_SELF" and
            old["other_events"] == "NONE", "ORIGINAL_TRIGGER_LEDGER")
    require("on:\n  push:\n    branches: [issue-402-species-functor-naming]\n    paths:\n" in original,
            "ORIGINAL_TRIGGER_CHANGED")
    require("      - " + REL in original, "SELF_PATH_MISSING")
    for event in ("workflow_dispatch", "workflow_call", "schedule",
                  "workflow_run", "repository_dispatch"):
        require("\n  " + event + ":" not in original, "ORIGINAL_EXTERNALLY_CALLABLE_" + event)
    call = m["consumers"]
    require(not historical_branch_live and
            call["live_invocable_trigger"] == "NONE_WITH_CURRENT_ABSENT_BRANCH",
            "ACTIVE_HISTORICAL_BRANCH_PRESENT")
    require(all(call[k] is False for k in ("declared_dispatch",
                  "declared_reusable", "declared_schedule", "declared_workflow_run")),
            "ACTIVE_CALLER_DECLARED")
    require(call["external_or_future_dynamic_intent"] == "NOT_PROVEN",
            "FALSE_EXTERNAL_CALLER_CERTAINTY")
    require(not original_present_in_candidate, "PREMATURE_REINTRODUCTION")
    require(old["historical_run_id"] == 43442652933 and
            old["historical_result"] == "SUCCESS", "HISTORICAL_RUN")
    artifact = old["artifact"]
    require(artifact["id"] == 14047452836 and artifact["bytes"] == 10401 and
            artifact["sha256"] == OLD_ARTIFACT_SHA and
            artifact["backup"] == "OWNER_PRIVATE_ZIP_BYTES_REDOWNLOADED_SHA256_MATCH",
            "ORIGINAL_ARTIFACT_NOT_PRESERVED")
    replace = m["replacement"]
    require(replace["path"] == REPLACEMENT and
            replace["pinned_original_workflow_checkout_sha"] == OLD_REF and
            replace["prior_exact_head"] == own["source_head"] and
            replace["prior_exact_run"] == 43722538507 and
            replace["prior_result"] == "SUCCESS", "REPLACEMENT_PIN")
    require(replace["build_base_digest"] == OCI_DIGEST and
            replace["historical_public_source_sha"] ==
            "29d1acc6ef7969908b86719e4b95c73a1565136d",
            "NATIVE_IDENTITY_PIN")
    require(set(replace["four_fixture_ids"]) ==
            {"R2_EI16", "R3_EI10", "E8_EI10", "E8_EI16"} and
            set(replace["dbase_cases"]) == {"417", "941"},
            "REPLACEMENT_CASE_SET")
    require(set(replace["required_markers"]) ==
            {"FLOW_EI10_EI16_FOUR_FIXTURE_NATIVE_P2_PASS",
             "FLOW_PINNED_DBASE_417_941_NATIVE_P2_PASS"},
            "P2_MARKER_SET")
    require("on:\n  pull_request:\n    branches: [main]" in maintained and
            "\n  workflow_dispatch:" in maintained and
            "\n  push:" not in maintained, "MAINTAINED_EVENT")
    for required in (
        "FLOW_EI10_EI16_FOUR_FIXTURE_NATIVE_P2_PASS",
        "FLOW_DBASE_LEGACY_P2_RETIRED_NEWONLY_P05_OWNS_417_941",
        "check_issue402_reaction_reduction_p2_only",
        OLD_BLOB, OLD_REF, OCI_DIGEST,
        "'"+REL+"'",
    ):
        require(required in maintained, "MAINTAINED_OBLIGATION_MISSING:" + required)
    require("FLOW_PINNED_DBASE_417_941_NATIVE_P2_PASS" not in maintained and
            "run_chemistry_s6_p2_only.py" not in maintained,
            "RETIRED_FLOW_DBASE_REINTRODUCED")
    assert_claim = m["retirement"]
    require(assert_claim["action"] == "STAGED_DELETE_IN_ISOLATED_DRAFT" and
            assert_claim["acceptance"] ==
            "PENDING_NEW_EXACT_HEAD_NATIVE_P2_AND_INTEGRATION" and
            assert_claim["original_git_blob_rollback"] == OLD_BLOB and
            assert_claim["no_automatic_merge"] is True, "PREMATURE_RETIREMENT_CLAIM")
    safety = m["safety"]
    require(safety["P3"] == "NOT_RUN" and safety["P4"] == "NOT_RUN" and
            safety["SCIENCE"] == "SCIENCE_HOLD" and
            safety["other_arch_originals"] == "KEEP_HOLD" and
            safety["no_policy_waiver"] is True, "SCIENCE_OR_POLICY_PROMOTION")
    require("ONE_SHOT_NAME" in surface and "branches: [main]" in surface and
            "FORBIDDEN_EVENTS" in surface, "WORKFLOW_GUARD_WEAKENED")


def loaded():
    m = json.loads((ROOT / MANIFEST).read_text(encoding="utf-8"))
    archived = ROOT.parent / "retired_workflow_archive" / REL
    return (m, archived.read_text(encoding="utf-8"),
            (ROOT / REPLACEMENT).read_text(encoding="utf-8"),
            (ROOT / "ci/guards/workflow_surface_guard.py").read_text(encoding="utf-8"),
            (ROOT / REL).exists())


def self_test(m: dict, old: str, replacement: str, surface: str) -> None:
    verify(m, old, replacement, surface)
    def must_reject(label: str, altered: dict, orig: str = old,
                    maintained: str = replacement, guard: str = surface,
                    **kwargs) -> None:
        try:
            verify(altered, orig, maintained, guard, **kwargs)
        except ValueError:
            return
        raise AssertionError("NEGATIVE_MUTATION_ACCEPTED:" + label)

    must_reject("ACTIVE_BRANCH", m, historical_branch_live=True)
    must_reject("SOURCE_REINTRODUCED", m, original_present_in_candidate=True)
    for field in ("declared_dispatch", "declared_reusable",
                  "declared_schedule", "declared_workflow_run"):
        bad = copy.deepcopy(m)
        bad["consumers"][field] = True
        must_reject("ACTIVE_CALLER_" + field, bad)
    bad = copy.deepcopy(m)
    bad["original"]["artifact"]["sha256"] = "0" * 64
    must_reject("ORIGINAL_ARCHIVE_TAMPER", bad)
    bad = copy.deepcopy(m)
    bad["retirement"]["acceptance"] = "RETIRED_VERIFIED"
    must_reject("UNPROVEN_RETIREMENT", bad)
    bad = copy.deepcopy(m)
    bad["safety"]["P3"] = "PASS"
    must_reject("SCIENCE_PROMOTION", bad)
    must_reject("ORIGINAL_BLOB", m, orig=old + "\n# tampered")
    must_reject("P2_MARKER_REMOVED", m,
                maintained=replacement.replace(
                    "FLOW_EI10_EI16_FOUR_FIXTURE_NATIVE_P2_PASS",
                    "UNVERIFIED_REPLACEMENT", 1))
    must_reject("REPLACEMENT_TRIGGER", m,
                maintained=replacement.replace(
                    "  pull_request:", "  push:", 1))
    must_reject("GUARD_REMOVAL", m, guard=surface.replace(
                    "ONE_SHOT_NAME", "REMOVED_POLICY_OWNER"))
    print("ISSUE541_GROUP_B_FLOW_NEGATIVE_MUTATIONS_13_REJECTED")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if not (args.check or args.self_test):
        ap.error("choose --self-test and/or --check")
    try:
        m, old, maintained, surface, present = loaded()
        if args.self_test:
            self_test(m, old, maintained, surface)
        if args.check:
            verify(m, old, maintained, surface,
                   original_present_in_candidate=present)
            print("ISSUE541_GROUP_B_FLOW_RETIREMENT_P0_PASS; P1_P2_EXACT_HEAD_CI_REQUIRED; SCIENCE_HOLD")
    except (KeyError, ValueError, AssertionError, OSError) as exc:
        print("ISSUE541_GROUP_B_FLOW_RETIREMENT_P0_FAIL:", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
