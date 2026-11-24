"""Fail-closed retirement gate for Issue #535 owner-scoped six-caller acceptance.

The operator accepted residual, unobservable external/private/dynamic caller
risk for exactly D2/D3/D4/A3/A4/B on 2026-11-17 (Issue #535 comment
6941923213). This is an explicit *risk acceptance*, not global caller-zero.
Six CORE/FLOW original obligations were retired after source verification.
ARCH DD and S6 owner scoped caller risk and user-managed mutable Drive custody
were separately approved (Issue #535 comment 6943043495). DD two-step P3
operational retirement is proposed after CI; S6 full 400W 100us two-case P3
was actually DISPATCHED under exact main SHA via workflow_dispatch run
44050874900 (both 417/941 approval steps PASS and execution in progress at
receipt). S6 remains HOLD until full execution/Artifact verification; neither
WORM nor scientific parity is claimed.
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
ARCH_RECEIPT = 6943043495

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
SCOPED_RETIRED = frozenset(("D2", "D3", "D4", "A3", "A4", "B", "DD"))
FORMAL_HOLD = frozenset(("S6",))
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
    "DD": set(),
    "S6": {"FULL_400W_100US_REPLAY_EQUIVALENCE_OR_SEPARATE_APPROVED_WAIVER"},
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

    # New ARCH scope is independent of the earlier CORE/FLOW sign-off.
    arch_approval = data["arch_owner_approval"]
    assert arch_approval["comment_id"] == ARCH_RECEIPT, "ARCH_OWNER_RECEIPT_NOT_PROVEN"
    assert arch_approval["accepted_utc_date"] == "2026-11-17"
    assert arch_approval["operator"] == "repository-operator"
    assert arch_approval["source"] == "DIRECT_USER_APPROVAL_RECORDED_IN_ISSUE535"
    assert arch_approval["scope"] == ["DD", "S6"]
    assert arch_approval["accepted_unknown_external_private_dynamic_caller_risk"] is True
    assert arch_approval["independent_caller_zero_proven"] is False
    assert arch_approval["retention_mode"] == (
        "USER_MANAGED_PRIVATE_GOOGLE_DRIVE_INDEPENDENT_SHA256_CRC_BACKUP"
    )
    assert arch_approval["retention_owner_mutable"] is True
    assert arch_approval["object_lock_or_worm_required_for_operational_retirement"] is False
    assert arch_approval["object_lock_or_worm_proven"] is False
    assert arch_approval["full_s6_original_scope_p3_authorized"] is True
    assert arch_approval["full_s6_execution_is_science_acceptance"] is False
    assert arch_approval["source_main_at_approval"] == "8263fbc1801f213b98183ba4876299041cd01dac"

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
            assert ident in ARCHIVE
            receipt = x["owner_caller_risk_attestation"]
            assert isinstance(receipt, dict), "ARCH_OPERATOR_ATTESTATION_MISSING:" + ident
            assert receipt["accepted"] is True and receipt["receipt_id"] == ARCH_RECEIPT
            assert receipt["accepted_utc_date"] == "2026-11-17"
            assert receipt["type"] == "OPERATOR_ACCEPTS_RESIDUAL_PRIVATE_DYNAMIC_CALLER_RISK"
            assert receipt["not_independent_caller_zero"] is True
            assert receipt["excludes_science_equivalence"] is True
            assert receipt["scope"] == (
                "DD_ORIGINAL_BOUNDARY_TWO_STEP_P3_ONLY" if ident == "DD"
                else "S6_417_941_FULL_400W_100US_P3_ORIGINAL_SCOPE"
            )
            assert x["retirement_scope"] == (
                "DD_ORIGINAL_BOUNDARY_TWO_STEP_P3_ONLY" if ident == "DD"
                else "S6_417_941_FULL_400W_100US_P3_PENDING_FULL_SOURCE_RUN"
            )
            retention = x["custody"]["operator_accepted_private_drive_alternative"]
            assert retention == {
                "receipt_id": ARCH_RECEIPT,
                "mode": "USER_MANAGED_MUTABLE_PRIVATE_DRIVE",
                "sha256_and_crc_verified": True,
                "object_lock_proven": False,
            }
            assert x["formal_disposition"] == (
                "RETIRED_VERIFIED" if ident == "DD" else "KEEP_HOLD"
            ), "UNAUTHORIZED_ARCH_RETIREMENT:" + ident

        assert tuple(x["replacement"]["routes"]) == REQUIRED_ROUTES[ident]
        for ref in x["replacement"]["routes"]:
            file_name, sep, job = ref.partition("#")
            assert sep and job and file_name.startswith(".github/workflows/")
            # Preserve the immutable historic route receipt, but require
            # the migrated job to exist at its current owner (#749).
            live = file_name
            if file_name == ".github/workflows/ci.yml":
                live = (
                    ".github/workflows/physics-native-ci.yml"
                    if job == "issue402_core_four_native_p2"
                    else ".github/workflows/physics-legacy-audit.yml"
                )
            text = (ROOT / live).read_text(encoding="utf-8")
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
                 "immutable_object_lock_proven", "operator_approved_waiver"):
        assert custody[flag] is False, "ARCH_UNAUTHORIZED_GATE_PROMOTION:" + flag
    assert custody["ARCH_external_caller_risk_accepted"] is True
    assert custody["owner_approved_retention_alternative"] is True
    assert custody["owner_approved_retention_method"] == "USER_MANAGED_MUTABLE_PRIVATE_GOOGLE_DRIVE"
    assert custody["SCIENCE_HOLD"] is True
    assert custody["retirement_disposition"] == {"DD": "RETIRED_VERIFIED", "S6": "KEEP_HOLD"}
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


    dispatch = data["arch_p3_dispatch_approval"]
    assert dispatch["receipt_id"] == ARCH_RECEIPT
    assert dispatch["approved_utc_date"] == "2026-11-17"
    assert dispatch["workflow_path"] == ".github/workflows/issue541-arch-s6-p3-p4-replay.yml"
    assert dispatch["workflow_git_blob"] == "6c673628eac4693abe0d74b04fc31578a39b3971"
    assert dispatch["target_ref"] == "main"
    assert dispatch["source_sha_policy"] == "RESOLVE_EXACT_MAIN_SHA_AT_DISPATCH"
    assert dispatch["source_sha_at_user_approval"] == "8263fbc1801f213b98183ba4876299041cd01dac"
    assert dispatch["required_event"] == "workflow_dispatch"
    assert dispatch["required_inputs"] == {
        "p3_approval": "ISSUE541_S6_400W_100US_BOTH_CASES_APPROVED",
        "source_sha": "EXACT_SELECTED_REF_HEAD_SHA",
    }
    assert dispatch["cases"] == ["417", "941"]
    assert dispatch["power_W"] == 400 and dispatch["duration_us"] == 100
    assert dispatch["max_parallel_jobs"] == 2 and dispatch["per_job_timeout_minutes"] == 360
    assert dispatch["status"] == "DISPATCHED_RUNNING_AT_RECEIPT"
    assert dispatch["run_id"] == 44050874900 and dispatch["run_attempt"] == 1
    assert dispatch["request_timestamp"] == "2026-11-17T08:55:23Z"
    assert dispatch["observation"] == "MATCHED_ACTIVE_TWO_SOURCE_BOUND_JOBS"
    assert dispatch["target_run_source_sha"] == "8263fbc1801f213b98183ba4876299041cd01dac"
    assert dispatch["target_run_event"] == "workflow_dispatch"
    assert dispatch["target_run_head_branch"] == "main"
    assert dispatch["target_case_job_ids"] == {"417": 133928069072, "941": 133928068701}
    assert dispatch["target_both_case_approval_steps_success"] is True
    assert dispatch["issue535_dispatch_receipt_id"] == 6943420997
    assert dispatch["transport_success_run_id"] == 44050852088
    assert dispatch["transport_skipped_preflight_run_id"] == 44050703765
    assert dispatch["temporary_workflow_cleanup_commit"] == "a39ee535c3dafba90a6f6107020ad04a61a16ca8"
    assert dispatch["temporary_workflow_removed"] is True
    assert dispatch["P3_full_scope_executed"] is False
    assert dispatch["P4"] == "DIAGNOSTIC_ONLY"
    assert dispatch["science"] == "SCIENCE_HOLD"
    assert dispatch["no_coverage_waiver"] is True
    assert dispatch["ref_event_guard_preserved"] is True
    assert data["arch_retirement_outcome"] == {
        "date_utc": "2026-11-17",
        "receipt_id": ARCH_RECEIPT,
        "current_proposed_wave1_retired": 9,
        "current_proposed_wave1_formal_holds": 1,
        "old_approved_eight_verified": True,
        "DD_formal_retired_after_CI_manual_review": True,
        "S6_formal_hold_due_full_replay": True,
        "science_hold": True,
    }

    assert data["global_holds"] == {
        "external_caller_risk": "OPERATOR_SCOPED_RISK_ACCEPTED_CORE_FLOW_ARCH_NOT_GLOBAL_CALLER_ZERO",
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


def test_negative_premature_retirement_ARCH_S6_only():
    for ident in FORMAL_HOLD:
        data = copy.deepcopy(_load())
        row = next(x for x in data["cases"] if x["id"] == ident)
        row["formal_disposition"] = "RETIRED_VERIFIED"
        with pytest.raises(AssertionError):
            _check(data)


def test_negative_forged_ARCH_caller_and_science_claims():
    for ident in ("DD", "S6"):
        for violation in ("missing", "wrong_receipt", "fake_caller_zero"):
            data = copy.deepcopy(_load())
            row = next(x for x in data["cases"] if x["id"] == ident)
            if violation == "missing":
                row["owner_caller_risk_attestation"] = None
            elif violation == "wrong_receipt":
                row["owner_caller_risk_attestation"]["receipt_id"] = OWNER_RECEIPT
            else:
                row["external_dynamic_caller"] = "CALLER_ZERO_PROVEN"
            with pytest.raises(AssertionError):
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
                 "immutable_object_lock_proven", "operator_approved_waiver"):
        data = copy.deepcopy(_load())
        data["arch_custody"][flag] = True
        with pytest.raises(AssertionError, match="ARCH_UNAUTHORIZED_GATE_PROMOTION"):
            _check(data)
    for flag in ("ARCH_external_caller_risk_accepted",
                 "owner_approved_retention_alternative"):
        data = copy.deepcopy(_load())
        data["arch_custody"][flag] = False
        with pytest.raises(AssertionError):
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


def test_negative_S6_dispatch_running_is_not_p3_success_or_science_acceptance():
    for field, corrupted in (
        ("status", "COMPLETED_SUCCESS"),
        ("run_id", 12345),
        ("request_timestamp", "2026-11-17T10:00:00Z"),
        ("observation", "P3_PASS"),
        ("P3_full_scope_executed", True),
        ("science", "SCIENCE_ACCEPTED"),
        ("no_coverage_waiver", False),
        ("source_sha_policy", "USE_OLD_SHA_WITHOUT_CHECK"),
    ):
        data = copy.deepcopy(_load())
        data["arch_p3_dispatch_approval"][field] = corrupted
        with pytest.raises(AssertionError):
            _check(data)


def test_negative_ARCH_user_managed_drive_approval_tampering():
    for field, corrupted in (
        ("comment_id", OWNER_RECEIPT),
        ("scope", ["DD"]),
        ("independent_caller_zero_proven", True),
        ("retention_owner_mutable", False),
        ("object_lock_or_worm_proven", True),
        ("full_s6_execution_is_science_acceptance", True),
    ):
        data = copy.deepcopy(_load())
        data["arch_owner_approval"][field] = corrupted
        with pytest.raises(AssertionError):
            _check(data)


def test_negative_S6_source_run_provenance_or_cleanup_tamper():
    for field, corrupted in (
        ("run_id", 1),
        ("run_attempt", 2),
        ("request_timestamp", "2026-11-17T08:00:00Z"),
        ("target_run_source_sha", "0" * 40),
        ("target_run_event", "push"),
        ("target_run_head_branch", "temporary-branch"),
        ("target_case_job_ids", {"417": 133928069072}),
        ("target_both_case_approval_steps_success", False),
        ("transport_success_run_id", 0),
        ("temporary_workflow_removed", False),
    ):
        data = copy.deepcopy(_load())
        data["arch_p3_dispatch_approval"][field] = corrupted
        with pytest.raises(AssertionError):
            _check(data)
