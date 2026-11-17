"""Fail-closed retirement gate for Issue #535 owner-scoped six-caller acceptance.

The operator accepted residual, unobservable external/private/dynamic caller
risk for exactly D2/D3/D4/A3/A4/B on 2026-11-17 (Issue #535 comment
6941923213). This is an explicit *risk acceptance*, not global caller-zero.
Six original verification obligations can be formally retired after exact-
head CI and separate release review; FLOW B source ZIP was independently
re-downloaded from Drive and byte/SHA/CRC verified, not WORM. ARCH DD/S6
original and bounded artifact custody was also checked, but they stay HOLD. No scientific parity,
WORM/Object Lock or automatic expensive P3 is asserted by this contract.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "ci/baselines/issue535_postrelease_eight_hold_gate_20261116.json"
SOURCE_MAIN = "bde6931a0030eb8bd4dfc532a6f9209e639ef275"
OWNER_RECEIPT = 6941923213

ORIGINALS = {
    "D2": "9cfa70c6843fb3e4eeec572dc3df00fd4fe6b611",
    "D3": "f11aa0de000fb05bcc587798400313558a6cb58a",
    "D4": "c6068680c0c7083e38ec03d86c5433eb49db94bf",
    "A3": "64164c097ec8f7831e67b80b317144cd97ba9ee8",
    "A4": "5e433b5c56f335808e6a5cbaa771b808eef1ad45",
    "B": "91313152e7e7df3bd0256a2180f489774cfa6171",
    "DD": "068ef7f78b84b45dbf8c678522ada049d4a42b7a",
    "S6": "485439a723584ca5bbc8632a86c53574b0b1eb9a",
}
APPROVED = frozenset(("D2", "D3", "D4", "A3", "A4", "B"))
SCOPED_RETIRED = frozenset(("D2", "D3", "D4", "A3", "A4", "B"))
FORMAL_HOLD = frozenset(("DD", "S6"))
ARCHIVE = {
    "DD": "docs/development/archive/issue402-dd-json-p3-smoke-once.yml.txt",
    "S6": "docs/development/archive/issue402-hybrid-json-s6-p3-p4-once.yml.txt",
}
REPLAY = {
    "DD": (".github/workflows/issue541-arch-dd-p3-replay.yml",
           "ISSUE541_DD_TWO_STEP_P3_APPROVED"),
    "S6": (".github/workflows/issue541-arch-s6-p3-p4-replay.yml",
           "ISSUE541_S6_400W_100US_BOTH_CASES_APPROVED"),
}
REQUIRED_GATES = {
    "D2": set(), "D3": set(), "D4": set(), "A3": set(), "A4": set(),
    "B": set(),
    "DD": {"EXTERNAL_CALLER_ATTESTATION",
           "IMMUTABLE_CUSTODY_OR_EXPLICIT_APPROVED_RETENTION_ALTERNATIVE"},
    "S6": {"EXTERNAL_CALLER_ATTESTATION",
           "IMMUTABLE_CUSTODY_OR_EXPLICIT_APPROVED_RETENTION_ALTERNATIVE",
           "FULL_400W_100US_REPLAY_EQUIVALENCE_OR_SEPARATE_APPROVED_WAIVER"},
}
REQUIRED_ROUTES = {
    "D2": (".github/workflows/ci.yml#issue402_core_four_p0",
           ".github/workflows/ci.yml#issue402_core_four_native_p2"),
    "D3": (".github/workflows/ci.yml#issue402_core_four_p0",
           ".github/workflows/ci.yml#issue402_core_four_native_p2"),
    "D4": (".github/workflows/ci.yml#issue402_core_four_p0",
           ".github/workflows/ci.yml#issue402_core_four_native_p2"),
    "A3": (".github/workflows/ci.yml#issue402_ideal_gas_p0",
           ".github/workflows/issue402-flow-native-p2-regression.yml#flow-native-p2"),
    "A4": (".github/workflows/ci.yml#issue402_reaction_material_p0",),
    "B": (".github/workflows/issue402-flow-native-p2-regression.yml#flow-native-p2",),
    "DD": (".github/workflows/issue541-arch-dd-p3-replay.yml#bounded-p3",),
    "S6": (".github/workflows/issue541-arch-s6-p3-p4-replay.yml#hybrid-native-s6",),
}


def _load() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _git_blob(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


def _check(data: dict, *, reintroduced: frozenset[str] = frozenset()) -> None:
    assert data["schema"] == "issue535.postrelease_eight_hold_gate.v1"
    assert data["repository"] == "HyungseonSong-plasma/moose-test-repo"
    assert data["source_main"] == SOURCE_MAIN
    assert data["checks"]["main_ci_conclusion"] == "success"
    assert data["checks"]["exact_pr_head_repo_ci_conclusion"] == "success"
    assert data["checks"]["full_p3_dispatched_this_audit"] is False
    assert data["authority"]["no_automatic_formal_promotion"] is True

    assert [x["cases"] for x in data["cycles"]] == [
        ["D2", "D3"], ["D4", "A3"], ["A4", "B"], ["DD", "S6"],
    ]
    assert [x["cases"] for x in data["approval_cycles"]] == [
        ["D2", "D3"], ["D4", "A3"], ["A4", "B"],
    ]
    assert [x["state"] for x in data["approval_cycles"]] == [
        "SCOPED_RETIRED_VERIFIED_AFTER_REQUIRED_CI",
        "SCOPED_RETIRED_VERIFIED_AFTER_REQUIRED_CI",
        "A4_AND_B_SCOPED_RETIRED_VERIFIED_AFTER_INDEPENDENT_B_ZIP_CUSTODY",
    ]

    approval = data["approval"]
    assert approval["comment_id"] == OWNER_RECEIPT, "OWNER_RECEIPT_NOT_PROVEN"
    assert approval["date_utc"] == "2026-11-17"
    assert approval["source"] == "DIRECT_OPERATOR_CHAT_APPROVAL_SCOPED"
    assert approval["owner"] == "repository-operator"
    assert approval["approved_scope"] == ["D2", "D3", "D4", "A3", "A4", "B"]
    assert approval["approval_effect"] == (
        "ACCEPT_RESIDUAL_PRIVATE_DYNAMIC_EXTERNAL_CALLER_RISK_AND_REPLACEMENT_VERIFICATION_HANDOFF_ONLY"
    )
    assert approval["caller_zero_proven"] is False
    for key in ("B_durable_custody_approved", "ARCH_DD_S6_approved",
                "science_approved", "automatic_merging_approved"):
        assert approval[key] is False, "APPROVAL_SCOPE_WIDENED:" + key

    cases = data["cases"]
    assert len(cases) == len(ORIGINALS) == 8
    assert {x["id"] for x in cases} == set(ORIGINALS)
    assert {x["id"] for x in cases if x["formal_disposition"] == "RETIRED_VERIFIED"} == SCOPED_RETIRED
    assert {x["id"] for x in cases if x["formal_disposition"] == "KEEP_HOLD"} == FORMAL_HOLD

    for x in cases:
        ident = x["id"]
        original = x["original"]
        path = original["path"]
        assert path.startswith(".github/workflows/issue402-")
        assert path.endswith("-once.yml")
        assert original["git_blob"] == ORIGINALS[ident]
        assert original["declared_trigger"] == "OLD_BRANCH_PUSH_ONLY"
        assert original["original_executable_absent_main"] is True
        assert not any(original[k] for k in (
            "declared_dispatch", "declared_workflow_call",
            "declared_workflow_run", "declared_schedule",
        ))
        assert path not in reintroduced and not (ROOT / path).exists(), (
            "RETIRED_ORIGINAL_REINTRODUCED:" + ident
        )
        assert original["old_branch_state"] == (
            "BRANCH_PRESENT_ORIGINAL_REMOVED" if ident in ARCHIVE else "BRANCH_ABSENT_404"
        )
        historic = x["historic"]
        assert historic["run_id"] > 0 and re.fullmatch(r"[0-9a-f]{40}", historic["source_sha"])
        assert historic["event"] == "push"
        assert historic["run_conclusion"] == (
            "failure" if ident in ARCHIVE else "success"
        )
        assert len(historic["artifacts"]) == (
            0 if ident == "A4" else 2 if ident == "S6" else 1
        )
        for art in historic["artifacts"]:
            assert art["id"] > 0 and art["bytes"] > 0
            assert re.fullmatch(r"sha256:[0-9a-f]{64}", art["sha256_digest"])
            assert re.fullmatch(r"\d{4}-\d\d-\d\dT.+Z", art["expires_at"])
            assert art["expired"] is False  # Snapshot evidence, not future availability.

        assert x["external_dynamic_caller"] == "UNVERIFIED_ALL_BRANCHES_OFF_PLATFORM"
        assert x["worm_object_lock"] == "NOT_PROVEN"
        assert x["science"] == "SCIENCE_HOLD" and x["p4"] == "NOT_ACCEPTED"
        assert set(x["red_gates"]) == REQUIRED_GATES[ident]
        assert x["issue535_receipt"] > 0

        if ident in APPROVED:
            receipt = x["owner_caller_risk_attestation"]
            assert isinstance(receipt, dict), "MISSING_SCOPED_OPERATOR_ATTESTATION:" + ident
            assert receipt["accepted"] is True
            assert receipt["receipt_id"] == OWNER_RECEIPT
            assert receipt["accepted_utc_date"] == "2026-11-17"
            assert receipt["type"] == "OPERATOR_ACCEPTS_RESIDUAL_UNSEEN_PRIVATE_DYNAMIC_CALLERS"
            assert receipt["not_independent_caller_zero"] is True
            assert receipt["excludes_worm_and_science"] is True
            scope = "ORIGINAL_P0_ONLY" if ident == "A4" else "ORIGINAL_P0_P1_P2_ONLY"
            assert receipt["scope"] == scope and x["retirement_scope"] == scope
            assert x["formal_disposition"] == (
                "RETIRED_VERIFIED" if ident in SCOPED_RETIRED else "KEEP_HOLD"
            ), "UNAUTHORIZED_RETIREMENT:" + ident
        else:
            assert x["owner_caller_risk_attestation"] is None, (
                "ARCH_CALLER_ATTESTATION_NOT_AUTHORIZED:" + ident
            )
            assert x["formal_disposition"] == "KEEP_HOLD", "UNAUTHORIZED_RETIREMENT:" + ident

        assert tuple(x["replacement"]["routes"]) == REQUIRED_ROUTES[ident]
        for ref in x["replacement"]["routes"]:
            file_name, sep, job = ref.partition("#")
            assert sep and job and file_name.startswith(".github/workflows/")
            text = (ROOT / file_name).read_text(encoding="utf-8")
            assert re.search(r"(?m)^  " + re.escape(job) + r":\s*$", text), (
                "REPLACEMENT_JOB_LOST:" + ident + ":" + job
            )

    B = next(x for x in cases if x["id"] == "B")
    original_zip = B["historic"]["artifacts"][0]
    assert original_zip["id"] == 14047452836
    assert original_zip["sha256_digest"] == (
        "sha256:95eca7994c105347a8948f9b06852ac3929eaddb9781cc01bad00ca31c88397b"
    )
    assert original_zip["expires_at"] == "2026-11-27T14:35:35Z"
    readback = B["custody"]["fresh_original_zip_download"]
    assert readback["github_artifact_id"] == original_zip["id"]
    assert readback["sha256"] == original_zip["sha256_digest"].removeprefix("sha256:")
    assert readback["zip_crc"] == "PASS_8_MEMBERS"
    assert readback["issue535_receipt"] == 6933161334
    assert readback["drive_new_upload_success"] is True
    assert readback["durable_redundant_retention"] == "PRIVATE_INDEPENDENT_DRIVE_BYTE_VERIFIED_NOT_WORM"
    assert readback["provider_expiry_utc"] == original_zip["expires_at"]
    assert readback["drive_file_id"] == "11xBcL8q8FLZBm9vsPXemoEbAhIE17Sqd"
    assert readback["drive_size_bytes"] == original_zip["bytes"] == 10401
    assert readback["drive_mime"] == "application/zip"
    assert readback["drive_shared"] is False
    assert readback["download_readback_sha256_match"] is True
    assert readback["download_readback_byte_cmp_match"] is True
    assert readback["download_readback_zip_crc"] == "PASS"
    assert readback["issue535_independent_backup_receipt"] == 6942585396
    assert readback["WORM_object_lock_not_proven"] is True

    assert data["approval_outcome"] == {
        "newly_retired_verified_count": 6,
        "still_hold_count": 2,
        "original_wave1_prior_retired_verified_count": 2,
        "wave1_proposed_formal_retired_verified_count": 8,
        "wave1_proposed_formal_hold_count": 2,
        "source": "USER_APPROVAL_CONDITIONED_ON_PR_EXACT_HEAD_CI_AND_MANUAL_MERGE_GATE",
    }

    # ARCH originals and separately maintained bounded runs are independently
    # private-backed up; source-hash equality does not prove WORM or science.
    custody = data["arch_custody"]
    assert custody["schema"] == "issue535.arch_independent_custody_2026_11_17.v1"
    assert custody["receipt_issue535_comment"] == 6942596277
    assert custody["verified_date_utc"] == "2026-11-17"
    assert custody["original_failed_zip_folder_id"] == "1AngOUYfMWyvgg9jAT2YGFN_04_5NZiZH"
    assert custody["evidence"] == "SIX_PRIVATE_DRIVE_DOWNLOADS_SHA256_MATCH_GITHUB_SOURCE_ZIP_CRC_PASS"
    assert custody["original_files"] == 3 and custody["maintained_bounded_files"] == 3
    assert custody["source_old_workflow_runs_failed"] is True
    assert custody["maintained_bounded_runs_success"] is True
    for flag in ("full_s6_400w_100us_maintained_replay_executed",
                 "immutable_object_lock_proven", "ARCH_external_caller_risk_accepted",
                 "operator_approved_waiver"):
        assert custody[flag] is False, "ARCH_UNAUTHORIZED_GATE_PROMOTION:" + flag
    assert custody["SCIENCE_HOLD"] is True
    assert custody["retirement_disposition"] == {"DD": "KEEP_HOLD", "S6": "KEEP_HOLD"}
    expected_six = {
        "DD_ORIGINAL": (14090046268, 1550, "d7ccb403173ef7a831e3ec9ad31a6c74c49c54dda20dfa839fe11b3331c572a4",
                        "1-2JJR2GeQcvO2aSSl_4H5w2tgY7s2wvQ", "ORIGINAL_FAILED"),
        "S6_417_ORIGINAL": (14117371106, 98686127, "563800ba985c3966d24aa0196fbe8ce46c9e1f5f1a1936685c6b5ff76c77a195",
                            "1ZgnvNpX6LwmY4yG_exuEdHpJFvAvwsCX", "ORIGINAL_FAILED"),
        "S6_941_ORIGINAL": (14120049502, 98635164, "87150a4b7db1647aa6a46731335ea1efa28a2998558cedd83df08d707c210d7e",
                            "1YWmovJU5TOiDp4Lg7gcjN5Vi7j8aNx_z", "ORIGINAL_FAILED"),
        "DD_BOUNDED": (14247572989, 16167, "1e2c52623a0ba1936a8c44ae69a1f2c273526a5b96048325288f6854de1d47da",
                       "1REOmp30hqVl069EqShs_5mR58yOa0L7S", "MAINTAINED_2_STEP_SUCCESS"),
        "S6_417_BOUNDED": (14243685279, 635777, "5ed26e8cd52e1a8b64164c733cd7452850b542f5c3e4e2cab18b6f3e4f8a8bf8",
                           "1X_L6I88FY0oyfj73rmt-8aSlM0vRiSQw", "MAINTAINED_3_STEP_SUCCESS"),
        "S6_941_BOUNDED": (14243116086, 635729, "6f20edfa50d64921af495f21aa9e533d910fe98a5696224f7888c5d1da654098",
                           "1cKDwUi_tF5W1JlccdF9fCiuZetFexT-v", "MAINTAINED_3_STEP_SUCCESS"),
    }
    assert len(custody["files"]) == len(expected_six)
    assert {x["case"] for x in custody["files"]} == set(expected_six)
    for row in custody["files"]:
        exact = expected_six[row["case"]]
        assert (row["github_artifact_id"], row["bytes"], row["git_sha256"],
                row["drive_file_id"], row["kind"]) == exact
        assert row["drive_shared"] is False
        assert row["drive_sha256_re_download_match"] is True
        assert row["zip_crc"] == "PASS"
        assert row["drive_copy_mutable"] is True
        assert re.fullmatch(r"[0-9a-f]{40}", row["source_sha"])
        assert row["run_id"] in (43536220786, 43587161603, 43911477519, 43902067509)

    assert data["global_holds"] == {
        "external_caller_risk": "PARTIAL_CORE_FLOW_ACCEPTED_ARCH_NOT_ACCEPTED",
        "worm": "NOT_PROVEN",
        "science": "SCIENCE_HOLD",
        "s6_p3": "100US_FULL_MAINTAINED_REPLAY_NOT_ACCEPTED",
    }


def _verify_manual_only(text: str, approval: str) -> None:
    event = re.search(r"(?ms)^on:\n(.*?)(?=^\S|\Z)", text)
    assert event, "MISSING_ON_EVENT"
    assert re.findall(r"(?m)^  ([A-Za-z_]+):", event.group(1)) == ["workflow_dispatch"]
    assert approval in text, "NO_EXPLICIT_APPROVAL"
    assert 'test "$REQUESTED_SHA" = "$GITHUB_SHA"' in text, "MISSING_EXACT_SHA_GATE"
    assert 'test "$GITHUB_EVENT_NAME" = "workflow_dispatch"' in text
    assert "SCIENCE_HOLD" in text


def test_owner_scoped_formal_dispositions_and_retained_holds():
    _check(_load())


def test_ARCH_originals_are_identical_nonexecutable_git_blobs():
    for ident, path in ARCHIVE.items():
        assert _git_blob((ROOT / path).read_bytes()) == ORIGINALS[ident]


def test_maintained_ARCH_replay_is_approval_and_source_sha_gated():
    for path, approval in REPLAY.values():
        _verify_manual_only((ROOT / path).read_text(encoding="utf-8"), approval)


def test_negative_reintroducing_each_of_eight_original_workflows_is_detected():
    data = _load()
    for x in data["cases"]:
        with pytest.raises(AssertionError, match="RETIRED_ORIGINAL_REINTRODUCED"):
            _check(data, reintroduced=frozenset({x["original"]["path"]}))


def test_negative_missing_or_forged_operator_approval():
    for ident in APPROVED:
        for violation in ("missing", "wrong_receipt", "fake_caller_zero"):
            data = copy.deepcopy(_load())
            row = next(x for x in data["cases"] if x["id"] == ident)
            if violation == "missing":
                row["owner_caller_risk_attestation"] = None
            elif violation == "wrong_receipt":
                row["owner_caller_risk_attestation"]["receipt_id"] = -1
            else:
                row["external_dynamic_caller"] = "CALLER_ZERO_PROVEN"
            with pytest.raises(AssertionError):
                _check(data)


def test_negative_premature_retirement_ARCH_DD_S6():
    for ident in FORMAL_HOLD:
        data = copy.deepcopy(_load())
        row = next(x for x in data["cases"] if x["id"] == ident)
        row["formal_disposition"] = "RETIRED_VERIFIED"
        with pytest.raises(AssertionError):
            _check(data)


def test_negative_unapproved_ARCH_caller_and_science_claims():
    for ident in ("DD", "S6"):
        data = copy.deepcopy(_load())
        row = next(x for x in data["cases"] if x["id"] == ident)
        row["owner_caller_risk_attestation"] = {
            "accepted": True, "receipt_id": OWNER_RECEIPT,
        }
        with pytest.raises(AssertionError, match="ARCH_CALLER_ATTESTATION_NOT_AUTHORIZED"):
            _check(data)


def test_negative_A4_scope_and_B_independent_backup_tampering():
    data = copy.deepcopy(_load())
    row = next(x for x in data["cases"] if x["id"] == "A4")
    row["retirement_scope"] = "ORIGINAL_P0_P1_P2_ONLY"
    with pytest.raises(AssertionError):
        _check(data)
    for key, value in (("drive_new_upload_success", False),
                       ("durable_redundant_retention", "WORM_VERIFIED"),
                       ("drive_file_id", "WRONG_ID"),
                       ("drive_shared", True),
                       ("drive_size_bytes", 0),
                       ("download_readback_sha256_match", False),
                       ("WORM_object_lock_not_proven", False)):
        data = copy.deepcopy(_load())
        row = next(x for x in data["cases"] if x["id"] == "B")
        row["custody"]["fresh_original_zip_download"][key] = value
        with pytest.raises(AssertionError):
            _check(data)


def test_negative_manual_approval_and_exact_source_sha_gates():
    for path, approval in REPLAY.values():
        text = (ROOT / path).read_text(encoding="utf-8")
        with pytest.raises(AssertionError, match="NO_EXPLICIT_APPROVAL"):
            _verify_manual_only(text.replace(approval, "REMOVED_APPROVAL"), approval)
        with pytest.raises(AssertionError, match="MISSING_EXACT_SHA_GATE"):
            _verify_manual_only(text.replace('test "$REQUESTED_SHA" = "$GITHUB_SHA"',
                                             'test "1" = "1"'), approval)


def test_negative_source_identity_and_replacement_routing():
    for ident in ORIGINALS:
        data = copy.deepcopy(_load())
        row = next(x for x in data["cases"] if x["id"] == ident)
        row["original"]["git_blob"] = "0" * 40
        with pytest.raises(AssertionError):
            _check(data)
        data = copy.deepcopy(_load())
        row = next(x for x in data["cases"] if x["id"] == ident)
        row["replacement"]["routes"] = []
        with pytest.raises(AssertionError):
            _check(data)


def test_negative_false_WORM_science_or_scope_promotion():
    for ident in ORIGINALS:
        data = copy.deepcopy(_load())
        row = next(x for x in data["cases"] if x["id"] == ident)
        row["worm_object_lock"] = "PROVEN"
        row["science"] = "SCIENCE_ACCEPTED"
        with pytest.raises(AssertionError):
            _check(data)
    for field in ("B_durable_custody_approved", "ARCH_DD_S6_approved",
                  "science_approved", "automatic_merging_approved"):
        data = copy.deepcopy(_load())
        data["approval"][field] = True
        with pytest.raises(AssertionError, match="APPROVAL_SCOPE_WIDENED"):
            _check(data)


def test_negative_ARCH_independent_custody_is_not_WORM_or_replay_waiver():
    for flag in ("full_s6_400w_100us_maintained_replay_executed",
                 "immutable_object_lock_proven",
                 "ARCH_external_caller_risk_accepted",
                 "operator_approved_waiver"):
        data = copy.deepcopy(_load())
        data["arch_custody"][flag] = True
        with pytest.raises(AssertionError, match="ARCH_UNAUTHORIZED_GATE_PROMOTION"):
            _check(data)
    for field, invalid in (("git_sha256", "0" * 64),
                           ("drive_file_id", "fake"),
                           ("bytes", 42),
                           ("drive_shared", True),
                           ("drive_copy_mutable", False),
                           ("drive_sha256_re_download_match", False)):
        data = copy.deepcopy(_load())
        data["arch_custody"]["files"][0][field] = invalid
        with pytest.raises(AssertionError):
            _check(data)
    data = copy.deepcopy(_load())
    data["arch_custody"]["files"].pop()
    with pytest.raises(AssertionError):
        _check(data)
