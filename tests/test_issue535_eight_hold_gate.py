"""Fail-closed P0 contract for the eight *formal* Issue #535 retirement HOLDs.

This does NOT attest private/off-platform callers, prove immutable storage,
dispatch native P3, or promote numerical scientific acceptance.  The purpose is
to prevent silent reactivation or unsupported formal status upgrades while
the existing manual verification and owner/archival gates are resolved.
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
    "D2": {"EXTERNAL_CALLER_ATTESTATION"},
    "D3": {"EXTERNAL_CALLER_ATTESTATION"},
    "D4": {"EXTERNAL_CALLER_ATTESTATION"},
    "A3": {"EXTERNAL_CALLER_ATTESTATION"},
    "A4": {"EXTERNAL_CALLER_ATTESTATION"},
    "B": {"EXTERNAL_CALLER_ATTESTATION", "RENEW_PRIVATE_B_ARTIFACT_READBACK_BEFORE_2026_11_27"},
    "DD": {"EXTERNAL_CALLER_ATTESTATION", "IMMUTABLE_CUSTODY_OR_EXPLICIT_APPROVED_RETENTION_ALTERNATIVE"},
    "S6": {"EXTERNAL_CALLER_ATTESTATION", "IMMUTABLE_CUSTODY_OR_EXPLICIT_APPROVED_RETENTION_ALTERNATIVE",
           "FULL_400W_100US_REPLAY_EQUIVALENCE_OR_SEPARATE_APPROVED_WAIVER"},
}


def _load() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _git_blob(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


def _check(data: dict, *, reintroduced: frozenset[str] = frozenset()) -> None:
    assert data["schema"] == "issue535.postrelease_eight_hold_gate.v1"
    assert data["repository"] == "HyungseonSong-plasma/moose-test-repo"
    assert re.fullmatch(r"[0-9a-f]{40}", data["source_main"])
    assert data["source_main"] == "bde6931a0030eb8bd4dfc532a6f9209e639ef275"
    assert data["checks"]["main_ci_conclusion"] == "success"
    assert data["checks"]["exact_pr_head_repo_ci_conclusion"] == "success"
    assert data["checks"]["full_p3_dispatched_this_audit"] is False
    assert data["authority"]["no_automatic_formal_promotion"] is True
    assert [x["cases"] for x in data["cycles"]] == [
        ["D2", "D3"], ["D4", "A3"], ["A4", "B"], ["DD", "S6"]
    ]
    cases = data["cases"]
    assert len(cases) == len(ORIGINALS) == 8
    assert {x["id"] for x in cases} == set(ORIGINALS)

    for x in cases:
        ident = x["id"]
        original = x["original"]
        path = original["path"]
        assert path.startswith(".github/workflows/issue402-")
        assert path.endswith("-once.yml")
        assert original["git_blob"] == ORIGINALS[ident]
        assert original["declared_trigger"] == "OLD_BRANCH_PUSH_ONLY"
        assert original["original_executable_absent_main"] is True
        assert not any(original[k] for k in ("declared_dispatch", "declared_workflow_call",
                                              "declared_workflow_run", "declared_schedule"))
        assert path not in reintroduced and not (ROOT / path).exists(), (
            "RETIRED_ORIGINAL_REINTRODUCED: " + ident
        )
        assert original["old_branch_state"] == (
            "BRANCH_PRESENT_ORIGINAL_REMOVED" if ident in ARCHIVE else "BRANCH_ABSENT_404"
        )
        hist = x["historic"]
        assert hist["run_id"] > 0 and re.fullmatch(r"[0-9a-f]{40}", hist["source_sha"])
        assert hist["event"] == "push"
        assert hist["run_conclusion"] == ("failure" if ident in ARCHIVE else "success")
        assert len(hist["artifacts"]) == (0 if ident == "A4" else 2 if ident == "S6" else 1)
        for a in hist["artifacts"]:
            assert a["id"] > 0 and a["bytes"] > 0
            assert re.fullmatch(r"sha256:[0-9a-f]{64}", a["sha256_digest"])
            assert re.fullmatch(r"\d{4}-\d\d-\d\dT.+Z", a["expires_at"])
            assert a["expired"] is False  # Snapshot on 2026-11-16, not future availability.
        assert x["external_dynamic_caller"] == "UNVERIFIED_ALL_BRANCHES_OFF_PLATFORM"
        assert x["worm_object_lock"] == "NOT_PROVEN"
        assert x["science"] == "SCIENCE_HOLD" and x["p4"] == "NOT_ACCEPTED"
        assert x["red_gates"] and set(x["red_gates"]) == REQUIRED_GATES[ident]
        assert x["issue535_receipt"] > 0
        assert x["owner_caller_risk_attestation"] is None
        # A future RETIRED_VERIFIED must be implemented by a separately reviewed
        # exact-SHA owner/retention evidence change, not a one-word manifest edit.
        assert x["formal_disposition"] == "KEEP_HOLD", "UNAUTHORIZED_RETIREMENT:" + ident

        assert x["replacement"]["routes"]
        for ref in x["replacement"]["routes"]:
            file_name, sep, job = ref.partition("#")
            assert sep and job and file_name.startswith(".github/workflows/")
            text = (ROOT / file_name).read_text(encoding="utf-8")
            assert re.search(r"(?m)^  " + re.escape(job) + r":\s*$", text), (
                "REPLACEMENT_JOB_LOST:" + ident + ":" + job
            )

    assert data["global_holds"] == {
        "external_caller_risk": "NO_NEW_OPERATOR_SIGNOFF_RECEIVED",
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


def test_eight_originals_removed_and_all_formal_holds_fail_closed():
    _check(_load())


def test_ARCH_originals_are_identical_nonexecutable_git_blobs():
    for ident, path in ARCHIVE.items():
        raw = (ROOT / path).read_bytes()
        assert _git_blob(raw) == ORIGINALS[ident]


def test_maintained_ARCH_replay_is_approval_and_source_sha_gated():
    for path, approval in REPLAY.values():
        _verify_manual_only((ROOT / path).read_text(encoding="utf-8"), approval)


def test_negative_reintroducing_each_of_eight_old_workflows_is_detected():
    data = _load()
    for x in data["cases"]:
        with pytest.raises(AssertionError, match="RETIRED_ORIGINAL_REINTRODUCED"):
            _check(data, reintroduced=frozenset({x["original"]["path"]}))


def test_negative_premature_retired_verified_never_passes_by_manifest_edit():
    for ident in ORIGINALS:
        data = copy.deepcopy(_load())
        row = next(x for x in data["cases"] if x["id"] == ident)
        row["formal_disposition"] = "RETIRED_VERIFIED"
        with pytest.raises(AssertionError, match="UNAUTHORIZED_RETIREMENT"):
            _check(data)


def test_negative_approval_and_exact_source_sha_gates():
    for path, approval in REPLAY.values():
        text = (ROOT / path).read_text(encoding="utf-8")
        with pytest.raises(AssertionError, match="NO_EXPLICIT_APPROVAL"):
            _verify_manual_only(text.replace(approval, "REMOVED_APPROVAL"), approval)
        with pytest.raises(AssertionError, match="MISSING_EXACT_SHA_GATE"):
            _verify_manual_only(text.replace('test "$REQUESTED_SHA" = "$GITHUB_SHA"',
                                             'test "1" = "1"'), approval)


def test_negative_falsified_artifact_custody_or_science_promotion():
    for case in ("B", "DD", "S6"):
        data = copy.deepcopy(_load())
        row = next(x for x in data["cases"] if x["id"] == case)
        row["red_gates"] = []
        row["worm_object_lock"] = "PROVEN"
        row["science"] = "SCIENCE_ACCEPTED"
        with pytest.raises(AssertionError):
            _check(data)
