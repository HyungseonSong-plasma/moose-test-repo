#!/usr/bin/env python3
"""Fail-closed, read-only Group A retirement inventory.

This is an evidence gate, NOT a workflow retirement or global guard waiver.
No dynamic/external caller absence is inferred from a code-search miss.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEDGER = Path("ci/baselines/issue541_group_a_retirement.json")
CASES = {
    "A1": ("CORE", "issue402-dd-json-boundary-p0-p2-once.yml",
           "bbebff910db3e5659014368043a50b99273d2cdc",
           "issue-402-dd-plasma-boundary-action", "PRESENT", 43533803916),
    "A2": ("FLOW", "issue402-legacy-symbol-audit-once.yml",
           "1931f0b9909507979826812f346d3353f12e333b",
           "issue-402-dd-plasma-boundary-action", "NOT_FOUND", 43522731185),
    "A3": ("FLOW", "issue402-rate-coef-ideal-gas-native-once.yml",
           "64164c097ec8f7831e67b80b317144cd97ba9ee8",
           "issue-402-rate-coef-ideal-gas", "NOT_FOUND", 43464123958),
    "A4": ("FLOW", "issue402-reaction-material-reduction-p0-once.yml",
           "5e433b5c56f335808e6a5cbaa771b808eef1ad45",
           "issue-402-species-functor-naming", "NOT_FOUND", 43428302896),
}
KNOWN_ARTIFACTS = {"A1": 14088768015, "A2": None,
                   "A3": 14058320821, "A4": None}


# Immutable 2026-11-16 readback receipts. These are historical observations,
# not live branch lookups and not permission to retire either workflow.
A1_A2_LIVE_HEAD = "af4a9e896328386723e8bbb957f334e1d83fe75e"
A1_A2_SAME_HEAD_PROOFS = {
  "A1": {
    "candidate_pr": 553,
    "head": "34a3539477071d56027c60b1f19d0b502b2e9733",
    "run_id": 43839529668,
    "run_conclusion": "failure",
    "job_id": 133204451509,
    "job_name": "Issue541 CORE four native source-bound P1 P2 (no P3)",
    "job_conclusion": "success",
    "scope": "P0/P1/P2",
    "p3": "NOT_RUN"
  },
  "A2": {
    "candidate_pr": 553,
    "head": "34a3539477071d56027c60b1f19d0b502b2e9733",
    "run_id": 43839529668,
    "run_conclusion": "failure",
    "job_id": 133204451103,
    "job_name": "issue402_legacy_p0_inventory",
    "job_conclusion": "success",
    "scope": "P0",
    "p3": "NOT_RUN"
  }
}

# Wave1-C 2026-11-16 immutable GitHub snapshot. Caller-zero is explicitly
# Previous snapshot records unverified A1/A2 BEFORE the owner-attested A2-only
# historic cutover. A1 and P3 remain KEEP_HOLD; this is not a live API read.
WAVE1_C_FIXED = json.loads(r'''{"audit_id":"wave1-c-20261116-live-github-readback","historical_branch_head":"af4a9e896328386723e8bbb957f334e1d83fe75e","historical_branch_comparison":"BEHIND_MAIN_13_AHEAD_0","branch_pr_531":"CLOSED_MERGED_EXACT_HEAD","branch_protected_metadata":false,"detailed_branch_protection":"UNVERIFIED_403_INTEGRATION_FORBIDDEN","other_same_branch_p3_workflows":[".github/workflows/issue402-dd-json-p3-smoke-once.yml",".github/workflows/issue402-hybrid-json-s6-p3-p4-once.yml"],"default_branch_static_caller_search":"SELF_YAML_ONLY_NOT_CALLER_ZERO","original_trigger":"PUSH_EXACT_BRANCH_AND_SELF_PATH_ONLY","workflow_call":"NOT_DECLARED_IN_ORIGINAL","workflow_dispatch":"NOT_DECLARED_IN_ORIGINAL","repository_dispatch":"NOT_DECLARED_IN_ORIGINAL","workflow_run":"NOT_DECLARED_IN_ORIGINAL","cross_branch_dynamic_callers":"UNVERIFIED","external_api_gh_controller_callers":"UNVERIFIED","integration_pr":578,"integration_head":"9e71762a5f45ab755481720e8beba314f59cd021","integration_ci_run":43853584740,"integration_ci_conclusion":"FAILURE","group_a_p0_job":133252079431,"group_a_p0_conclusion":"SUCCESS_27_NEGATIVE_MUTATIONS","global_surface_guard":"FAIL_SIX_OTHER_AND_A1_A2_ORIGINAL_BRANCH_VIOLATIONS","disposition":"KEEP_HOLD_NO_ORIGINAL_REMOVAL_NO_BRANCH_DELETE","science":"SCIENCE_HOLD_P3_NOT_RUN"}''')
WAVE1_C_PER_CASE = json.loads(r'''{"A1":{"historical_run_id":43533803916,"historical_run_conclusion":"SUCCESS","artifact_custody":"ARTIFACT_14088768015_UNEXPIRED_EXPIRES_2026-12-14_BACKUP_NOT_REHASHED","replacement_p0_job":133252079406,"replacement_native_p1_p2_job":133252079180,"replacement_job_conclusion":"SUCCESS","distinct_red_gate":"EXTERNAL_DYNAMIC_CALLER_ZERO_NOT_PROVEN; LEGACY_PUSH_BRANCH_PRESENT; SOURCE_CI_RED; P3_BRANCH_SHARED; FULL_PRESERVATION_UNPROVEN"},"A2":{"historical_run_id":43522731185,"historical_run_conclusion":"SUCCESS","artifact_custody":"NO_ARTIFACT_PUBLISHED_IN_ORIGINAL_RUN","replacement_p0_job":133252079239,"replacement_native_p1_p2_job":null,"replacement_job_conclusion":"SUCCESS","distinct_red_gate":"EXTERNAL_DYNAMIC_CALLER_ZERO_NOT_PROVEN; LEGACY_PUSH_BRANCH_PRESENT; SOURCE_CI_RED; P3_BRANCH_SHARED; FULL_PRESERVATION_UNPROVEN"}}''')


# Independent Drive source bytes and isolated branch sunset prerequisite.
# This is a recorded, fail-closed staging receipt, not CALLER_ZERO_PROVEN.
WAVE1_C_CLOSURE = json.loads(r'''{"A1":{"mode":"STAGED_LEGACY_BRANCH_SHUTDOWN_REVIEW_ONLY","retention":"PRIVATE_INDEPENDENT_COPY_READBACK","proof_date":"2026-11-16","historical_branch":"issue-402-dd-plasma-boundary-action","historical_branch_head":"af4a9e896328386723e8bbb957f334e1d83fe75e","branch_shared_with_p3":true,"branch_must_not_be_deleted":true,"original_workflows_reviewed":45,"branch_write_route":"PUSH_EXACT_SELF_PATH_ONLY","declared_dispatch_or_call_route":false,"cross_branch_external_or_dynamic_callers":"UNVERIFIED","caller_zero_proven":false,"prereq_draft_pr":588,"prereq_draft_head":"85d6968f5155e25eabfca8b503828979d9509506","prereq_base":"issue-402-dd-plasma-boundary-action","prereq_state":"OPEN_DRAFT_NOT_MERGED","prereq_scope":"EXACTLY_TWO_A1_A2_FILES_REMOVED_FROM_CANDIDATE_BRANCH_ONLY","untouched_p3_dd_blob":"068ef7f78b84b45dbf8c678522ada049d4a42b7a","untouched_p3_s6_blob":"485439a723584ca5bbc8632a86c53574b0b1eb9a","original_sha":"bbebff910db3e5659014368043a50b99273d2cdc","artifact_backup":{"drive_file_id":"1OsADIq21_JU4Z4O65t_Hl-_AwjM6Nxf0","github_artifact_id":14088768015,"bytes":2072,"sha256":"de931c0c1dcb95308759a0c67eba42b9fbcd97fcb961b88a92d0b179ca9a8d27","independent_zip_readback":"EXACT_BINARY_AND_HASH_PASS","worm":"NOT_PROVEN"},"final_deletion_authorized":false,"decision":"KEEP_HOLD","science":"SCIENCE_HOLD","p3":"NOT_RUN"},"A2":{"mode":"STAGED_LEGACY_BRANCH_SHUTDOWN_REVIEW_ONLY","retention":"PRIVATE_INDEPENDENT_COPY_READBACK","proof_date":"2026-11-16","historical_branch":"issue-402-dd-plasma-boundary-action","historical_branch_head":"af4a9e896328386723e8bbb957f334e1d83fe75e","branch_shared_with_p3":true,"branch_must_not_be_deleted":true,"original_workflows_reviewed":45,"branch_write_route":"PUSH_EXACT_SELF_PATH_ONLY","declared_dispatch_or_call_route":false,"cross_branch_external_or_dynamic_callers":"UNVERIFIED","caller_zero_proven":false,"prereq_draft_pr":588,"prereq_draft_head":"85d6968f5155e25eabfca8b503828979d9509506","prereq_base":"issue-402-dd-plasma-boundary-action","prereq_state":"OPEN_DRAFT_NOT_MERGED","prereq_scope":"EXACTLY_TWO_A1_A2_FILES_REMOVED_FROM_CANDIDATE_BRANCH_ONLY","untouched_p3_dd_blob":"068ef7f78b84b45dbf8c678522ada049d4a42b7a","untouched_p3_s6_blob":"485439a723584ca5bbc8632a86c53574b0b1eb9a","original_sha":"1931f0b9909507979826812f346d3353f12e333b","artifact_backup":null,"final_deletion_authorized":false,"decision":"KEEP_HOLD","science":"SCIENCE_HOLD","p3":"NOT_RUN"}}''')

# A1 user-declared off-platform caller absence: STAGED ONLY; old ref not yet cut over.
A1_OWNER_RETIREMENT = json.loads(r'''{"mode":"OPERATOR_DECLARED_A1_NO_EXTERNAL_CALLERS__STAGED_ONLY","operator_statement":"외부 호출자는 존재하지 않으니까, 그걸로 처리를 하자.","statement_source":"CURRENT_USER_CONVERSATION_2026-11-16","attestation_type":"USER_DECLARATION_NOT_INDEPENDENT_GITHUB_AUDIT","static_census":"FIVE_CONNECTED_REPOS_DEFAULT_BRANCH_A1_SELF_PATH_ONLY","historic_actions_runs":19,"historic_events":"ALL_PUSH_REPO_OWNER","historical_branch":"issue-402-dd-plasma-boundary-action","historical_head_before":"b3f3b6e09b83828343fc0bc097f5a4edce9207e7","original_blob":"bbebff910db3e5659014368043a50b99273d2cdc","historic_a1_file":"ABSENT_ON_LIVE_HISTORICAL_REF","old_ref_cutover_pr":606,"old_ref_cutover_head":"08086bd563f76d1b6bd86d4274679791f801136d","old_ref_cutover_state":"MERGED_READBACK_VERIFIED","old_ref_cutover_scope":"EXACTLY_ONE_A1_YAML_DELETION","original_artifact_id":14088768015,"historical_zip_sha256":"de931c0c1dcb95308759a0c67eba42b9fbcd97fcb961b88a92d0b179ca9a8d27","independent_drive_backup":"1OsADIq21_JU4Z4O65t_Hl-_AwjM6Nxf0","original_zip_bytes":2072,"backup_readback":"MATCHED_BYTES_SHA256_VALID_ZIP","archive_worm":"NOT_PROVEN","a2_unchanged":"RETIRED_VERIFIED_AND_ABSENT_ON_LIVE_BRANCH","p3_dd_blob":"068ef7f78b84b45dbf8c678522ada049d4a42b7a","p3_s6_blob":"485439a723584ca5bbc8632a86c53574b0b1eb9a","shared_branch_deletion":"NOT_AUTHORIZED","replacement_job":"issue402_core_four_native_p2","replacement_p0_job":"issue402_core_four_p0","replacement_oci_sha256":"2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008","last_verified_run":43872131969,"last_verified_sha":"8dcec2c195b683d795d162ab6825da1366c932d2","last_verified_native_job":133315748335,"last_verified_native_artifact_id":14227174075,"last_verified_group_a_mutations":59,"final_candidate_exact_head_ci":"DEFERRED_BY_USER_AFTER_SOURCE_CHANGE","proposed_retirement":"STAGED_DELETE_KEEP_HOLD_INTEGRATION","accepted_retirement":false,"p3":"NOT_RUN","science":"SCIENCE_HOLD","old_ref_merge_commit":"632aa2376cad03faa271bad2986c664086842225","historical_head_after":"632aa2376cad03faa271bad2986c664086842225"}''')

# A2-only owner attestation and independently read-back historical cutover.
# This is a pinned release receipt; the exact source HEAD is rechecked by CI.
A2_OWNER_RETIREMENT = json.loads(r'''{"mode":"OWNER_ATTESTED_A2_SELF_PATH_RETIREMENT","attestation":"REPOSITORY_OWNER_CONFIRMS_NO_EXTERNAL_PAT_OR_PRIVATE_CONTROLLER","attestation_basis":"OPERATOR_DECLARATION_AND_REVIEWED_GITHUB_CODE_AND_RUN_HISTORY","attestation_comment_id":6917594646,"original_blob":"1931f0b9909507979826812f346d3353f12e333b","historical_branch":"issue-402-dd-plasma-boundary-action","historical_head_before":"af4a9e896328386723e8bbb957f334e1d83fe75e","historical_head_after":"b3f3b6e09b83828343fc0bc097f5a4edce9207e7","historical_a2_file":"ABSENT","historical_pr":602,"original_workflow_id":417813582,"original_success_run":43522731185,"original_artifact":"NONE_PUBLISHED","observed_a2_push_runs":5,"observed_a2_actors":"HyungseonSong-plasma","same_branch_a1_blob":"bbebff910db3e5659014368043a50b99273d2cdc","same_branch_p3_dd_blob":"068ef7f78b84b45dbf8c678522ada049d4a42b7a","same_branch_p3_s6_blob":"485439a723584ca5bbc8632a86c53574b0b1eb9a","legacy_branch_retained":true,"integration_pr":578,"integration_review_pr":605,"integration_base_before_delete":"860dd366e191a20124b0eae85d369498738233d6","maintained_job":"issue402_legacy_p0_inventory","maintained_run_id":43870291280,"maintained_job_id":133309345787,"maintained_p0":"PASS_81_PASSED_13_SKIPPED","maintained_inventory":"SELF_TEST_AND_CHECK_PASS","group_a_job_id":133309345622,"group_a_negative_mutations_before":49,"global_surface_guard":"STILL_FAILS_A1_AND_TWO_ARCH_P3_UNWAIVED","p3":"NOT_RUN","science":"SCIENCE_HOLD"}''')


def git_blob_sha(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def check_trigger(source: str, path: str, branch: str) -> list[str]:
    errors = []
    prologue = source.split("permissions:", 1)[0]
    if not re.search(r"(?m)^on:\s*$", prologue):
        errors.append("missing on: trigger")
    if not re.search(r"(?m)^  push:\s*$", prologue):
        errors.append("missing push trigger")
    if "    branches: [" + branch + "]" not in prologue:
        errors.append("historical branch differs")
    if "    paths: [" + path + "]" not in prologue:
        errors.append("exact self-file trigger differs")
    if re.search(r"(?m)^  (workflow_dispatch|workflow_call|workflow_run|repository_dispatch|schedule|pull_request):", prologue):
        errors.append("unexpected additional trigger")
    return errors


S6_STAGED_REPLAY = ".github/workflows/issue541-arch-s6-p3-p4-replay.yml"
S6_STAGED_README = "experiments/Issue402_plasma_dsl_g1/chemistry/README.md"
S6_STAGED_MARKERS = (
    "issue541-arch-s6-p3-p4-replay.yml",
    "485439a723584ca5bbc8632a86c53574b0b1eb9a",
    "manual-only", "retirement proposal", "current default branch",
)


def s6_staged_absence_evidence(readme: str, replay: str) -> bool:
    """S6-only staged-removal proof; never promote DD or A1 retirement."""
    if not all(marker in readme for marker in S6_STAGED_MARKERS):
        return False
    if "\non:\n" not in replay:
        return False
    trigger = replay.split("\non:\n", 1)[1].split("\npermissions:", 1)[0]
    return (trigger.startswith("  workflow_dispatch:\n") and
            all(event not in trigger for event in
                ("  push:", "  pull_request:", "  schedule:")) and
            "ISSUE541_S6_400W_100US_BOTH_CASES_APPROVED" in replay and
            'test "$REQUESTED_SHA" = "$GITHUB_SHA"' in replay)


DD_STAGE_MANIFEST = Path("ci/baselines/issue541_dd_p3_retirement_20261116.json")
DD_STAGE_ARCHIVE = Path("docs/development/archive/issue402-dd-json-p3-smoke-once.yml.txt")
DD_STAGE_DOC = Path("docs/development/2026-11-16_issue541_dd_p3_original_retirement_custody.md")
DD_STAGE_REPLAY = Path(".github/workflows/issue541-arch-dd-p3-replay.yml")

def dd_staged_absence_evidence(root: Path) -> bool:
    try:
        m=json.loads((root/DD_STAGE_MANIFEST).read_text(encoding="utf-8"))
        archive=(root/DD_STAGE_ARCHIVE).read_bytes()
        doc=(root/DD_STAGE_DOC).read_text(encoding="utf-8")
        replay=(root/DD_STAGE_REPLAY).read_text(encoding="utf-8")
        trigger=replay.split("\non:\n",1)[1].split("\npermissions:",1)[0]
        return (m["schema"] == "issue541.dd_p3.original_staged_retirement.v1"
                and m["state"] == "STAGED_DELETE_KEEP_HOLD_INTEGRATION"
                and m["science"] == "SCIENCE_HOLD"
                and m["final_retired_verified"] is False
                and m["original"]["git_blob"] == A1_OWNER_RETIREMENT["p3_dd_blob"]
                and m["original"]["source_copy_path"] == str(DD_STAGE_ARCHIVE)
                and git_blob_sha(archive) == A1_OWNER_RETIREMENT["p3_dd_blob"]
                and m["custody"]["readback"] == "REMOTE_DOWNLOAD_SHA256_AND_ZIP_CRC_MATCH_ALL_THREE"
                and m["custody"]["worm_lock"] == "NOT_PROVEN"
                and m["dd_native_p3"]["run_id"] == 43911477519
                and m["dd_native_p3"]["two_timesteps_completed"] is True
                and A1_OWNER_RETIREMENT["p3_dd_blob"] in doc
                and "manual-only" in doc
                and trigger.startswith("  workflow_dispatch:\n")
                and all(x not in trigger for x in ("  push:", "  pull_request:", "  schedule:"))
                and "ISSUE541_DD_TWO_STEP_P3_APPROVED" in replay
                and 'test "$REQUESTED_SHA" = "$GITHUB_SHA"' in replay)
    except (OSError,ValueError,KeyError,TypeError,IndexError):
        return False


def inspect(root: Path, doc: dict) -> list[str]:
    errors = []
    if doc.get("schema") != "issue541.workflow_surface.group_a_evidence.v1":
        errors.append("schema")
    if doc.get("repository") != "HyungseonSong-plasma/moose-test-repo":
        errors.append("repository")
    if doc.get("baseline_main_sha") != "71e112eb05d4645c82aab8861b99d6952ac4ac3e":
        errors.append("baseline source")
    if doc.get("science") != "SCIENCE_HOLD" or doc.get("p3") != "NOT_RUN":
        errors.append("science/P3 promotion")
    records = doc.get("workflows")
    if not isinstance(records, list):
        return errors + ["missing workflow records"]
    ids = [x.get("id") for x in records if isinstance(x, dict)]
    if len(records) != 4 or set(ids) != set(CASES) or len(ids) != len(set(ids)):
        errors.append("must inventory exactly four unique Group A owners")
    for record in records:
        if not isinstance(record, dict) or record.get("id") not in CASES:
            errors.append("unknown or malformed Group A record")
            continue
        id_ = record["id"]
        package, name, sha, branch, observed, run = CASES[id_]
        path = ".github/workflows/" + name
        for key, value in (("package", package), ("path", path),
                           ("original_blob", sha), ("historical_branch", branch),
                           ("branch_observed", observed), ("original_run_id", run),
                           ("original_conclusion", "success")):
            if record.get(key) != value:
                errors.append(id_ + " mismatched " + key)
        if not re.fullmatch(r"[0-9a-f]{40}", str(record.get("original_source_sha", ""))):
            errors.append(id_ + " missing historical source identity")
        source_path = root / path
        if id_ in {"A3", "A4"}:
            # Integration is staged deletion, NOT accepted retirement. A3/A4
            # are independently owned by the FLOW A-2 archival/negative gate.
            staged = record.get("staged_candidate")
            expected_staged = {
                "source_pr": 568,
                "source_integration_pr": 574,
                "status": "STAGED_DELETE_KEEP_HOLD_INTEGRATION",
                "flow_manifest": "ci/baselines/issue541_group_a2_flow_retirement.json",
                "flow_guard": "ci/guards/issue541_group_a2_flow_retirement_p0.py",
            }
            if staged != expected_staged:
                errors.append(id_ + " staged owner evidence missing/falsified")
            if source_path.exists():
                errors.append(id_ + " staged retired workflow was reintroduced")
            for needed in (expected_staged["flow_manifest"], expected_staged["flow_guard"],
                           ".github/workflows/issue402-flow-native-p2-regression.yml"):
                if not (root / needed).is_file():
                    errors.append(id_ + " FLOW replacement/archival dependency absent: " + needed)
            native_path = root / ".github/workflows/issue402-flow-native-p2-regression.yml"
            if native_path.is_file() and (
                "issue541_group_a2_flow_retirement_p0.py --self-test --check"
                not in native_path.read_text(encoding="utf-8")
            ):
                errors.append(id_ + " mandatory FLOW A-2 mutation contract disconnected")
            ci_file = root / ".github/workflows/physics-legacy-audit.yml"
            expected_job = ("issue402_ideal_gas_p0" if id_ == "A3"
                            else "issue402_reaction_material_p0")
            if ci_file.is_file() and "  " + expected_job + ":" not in ci_file.read_text(encoding="utf-8"):
                errors.append(id_ + " maintained P0 owner not in canonical CI")
        elif id_ == "A1":
            # This is an isolated staged deletion, not a global or old-ref retirement.
            if source_path.exists():
                errors.append("A1 staged original was reintroduced")
            if record.get("a1_owner_retirement") != A1_OWNER_RETIREMENT:
                errors.append("A1 owner source/caller/provenance stage receipt falsified")
            for p3name, blob in (
                ("issue402-dd-json-p3-smoke-once.yml", A1_OWNER_RETIREMENT["p3_dd_blob"]),
                ("issue402-hybrid-json-s6-p3-p4-once.yml", A1_OWNER_RETIREMENT["p3_s6_blob"]),
            ):
                p3source = root / ".github/workflows" / p3name
                if p3source.is_file():
                    if git_blob_sha(p3source.read_bytes()) != blob:
                        errors.append("A1 associated ARCH P3 original changed: " + p3name)
                elif p3name == "issue402-dd-json-p3-smoke-once.yml":
                    if not dd_staged_absence_evidence(root):
                        errors.append("DD staged original absent without pinned archival/manual proof")
                elif p3name == "issue402-hybrid-json-s6-p3-p4-once.yml":
                    # S6's isolated retirement candidate may delete this
                    # original from the integration tree, but only with a
                    # manifest-pinned rollback blob and manual-only replay.
                    readme_path = root / S6_STAGED_README
                    replay_path = root / S6_STAGED_REPLAY
                    if (not readme_path.is_file() or not replay_path.is_file()
                            or not s6_staged_absence_evidence(
                                readme_path.read_text(encoding="utf-8"),
                                replay_path.read_text(encoding="utf-8"))):
                        errors.append("S6 staged absent without approved source/replay receipt")
                else:
                    errors.append("A1 associated ARCH DD P3 original changed/missing: " + p3name)
            ci_file = root / ".github/workflows/physics-legacy-audit.yml"
            native_file = root / ".github/workflows/physics-native-ci.yml"
            ci_text = ci_file.read_text(encoding="utf-8") if ci_file.is_file() else ""
            native_text = native_file.read_text(encoding="utf-8") if native_file.is_file() else ""
            if "  issue402_core_four_p0:" not in ci_text:
                errors.append("A1 maintained P0 replacement route disconnected")
            for needed in ("  issue402_core_four_native_p2:",
                           "run_issue541_core_four_native_p2.py", "make -C physics_app -j2"):
                if needed not in native_text:
                    errors.append("A1 maintained Native P1/P2 replacement route disconnected: " + needed)
        elif id_ == "A2":
            # The approved absent P0-only A2; do not change its ownership.
            # Do not generalize this exception to A1 or the ARCH P3 originals.
            if source_path.exists():
                errors.append("A2 legacy workflow reintroduced after verified shutdown")
            if record.get("a2_owner_retirement") != A2_OWNER_RETIREMENT:
                errors.append("A2 source/owner/caller/P0/P3 release receipt missing or falsified")
            # A2's original one-shot workflow was independently accepted as
            # RETIRED_VERIFIED. Its historic P0 run and owner attestation are
            # immutable ledger facts, not a mandate to keep recreating an
            # Issue402-specific job or a symbol-reporting tool.
            # Current Physics test protection is owned by the ordinary
            # physics_code_validate pytest suite; no A2 dynamic gate remains.
        elif not source_path.is_file():
            errors.append(id_ + " active-branch original workflow missing without accepted caller-zero")
        else:
            raw = source_path.read_bytes()
            if git_blob_sha(raw) != sha:
                errors.append(id_ + " original Git blob changed")
            errors += [id_ + " " + error for error in
                       check_trigger(raw.decode("utf-8"), path, branch)]
        artifact = record.get("artifact")
        expected_id = KNOWN_ARTIFACTS[id_]
        if expected_id is None:
            if artifact is not None:
                errors.append(id_ + " invented original artifact")
        elif not isinstance(artifact, dict) or artifact.get("id") != expected_id or (
            not isinstance(artifact.get("bytes"), int) or artifact["bytes"] <= 0
        ) or artifact.get("expired") is not False:
            errors.append(id_ + " missing original artifact receipt")
        replacement = record.get("replacement")
        if not isinstance(replacement, dict) or replacement.get("conclusion") != "success" or (
            not isinstance(replacement.get("run_id"), int) or replacement["run_id"] <= 0
        ) or not re.fullmatch(r"[0-9a-f]{40}", str(replacement.get("head", ""))):
            errors.append(id_ + " missing source-bound replacement receipt")
        if id_ in A1_A2_SAME_HEAD_PROOFS:
            # A historical success job does not override red global CI or
            # independently verified historical A1 self-path removal; the shared
            # branch remains because two independent P3 workflows still own it.
            observed = ({
                "head": A2_OWNER_RETIREMENT["historical_head_after"],
                "workflow_blob": None,
                "entrypoint": "A2_SELF_PATH_REMOVED",
                "observed_on": "2026-11-16",
            } if id_ == "A2" else {
                "head": A1_OWNER_RETIREMENT["historical_head_after"],
                "workflow_blob": None,
                "entrypoint": "A1_SELF_PATH_REMOVED",
                "observed_on": "2026-11-16",
            })
            if record.get("live_branch_readback") != observed:
                errors.append(id_ + " active legacy branch receipt missing or falsified")
            if record.get("same_head_revalidation") != A1_A2_SAME_HEAD_PROOFS[id_]:
                errors.append(id_ + " same-head CI/job provenance missing or falsified")
        if id_ in WAVE1_C_PER_CASE:
            expected_wave1 = dict(WAVE1_C_FIXED)
            expected_wave1.update(WAVE1_C_PER_CASE[id_])
            if record.get("wave1_c_followup") != expected_wave1:
                errors.append(id_ + " Wave1-C branch/caller/CI/retention audit missing or falsified")
            if record.get("wave1_c_closure") != WAVE1_C_CLOSURE[id_]:
                errors.append(id_ + " Wave1-C independent backup or source-branch cutover evidence falsified")
        if id_ == "A1":
            if record.get("decision") != "STAGED_DELETE_KEEP_HOLD_INTEGRATION":
                errors.append("A1 premature final retirement/rollback of staged status")
            if record.get("caller_state") != "OWNER_DECLARED_NO_EXTERNAL_CALLERS__A1_OLD_REF_CUTOVER_MERGED":
                errors.append("A1 owner attestation scope/state falsified")
            if record.get("blockers") != [
                "Final integrated #578 exact-source CI/Native and retirement acceptance deferred by operator; A1 remains staged HOLD",
                "Independent ARCH DD P3 and hybrid S6 P3/P4 workflow surface policies remain unresolved and unwaived",
            ]:
                errors.append("A1 incomplete integration/old-ref HOLD not disclosed")
            if record.get("remaining_non_a1_gates") != [
                "ARCH DD P3 original not retired",
                "ARCH hybrid S6 P3/P4 original not retired",
                "Global Workflow Surface Guard still FAIL while ARCH originals remain",
            ]:
                errors.append("A1 remaining ARCH P3 global holds hidden")
        elif id_ == "A2":
            if record.get("decision") != "RETIRED_VERIFIED":
                errors.append("A2 expected owner-attested retirement disposition missing")
            if record.get("caller_state") != "OWNER_ATTESTED_NO_EXTERNAL_PAT_PRIVATE_CONTROLLER__SELF_PATH_DISABLED":
                errors.append("A2 owner-attested caller status missing or forged")
            if record.get("blockers") != []:
                errors.append("A2 old HOLD blockers reused or new unresolved blocker injected")
            if record.get("remaining_non_a2_gates") != [
                "A1 DD JSON Boundary one-shot KEEP_HOLD",
                "ARCH DD P3 one-shot KEEP_HOLD",
                "ARCH Hybrid S6 P3/P4 one-shot KEEP_HOLD",
                "Global validate remains red until separate authorized closures",
            ]:
                errors.append("A2 global A1/P3 remaining gates suppressed")
        else:
            if record.get("decision") != "KEEP_HOLD":
                errors.append(id_ + " retirement promoted without accepted caller-zero/integrated proof")
            if not isinstance(record.get("blockers"), list) or not record["blockers"]:
                errors.append(id_ + " missing explicit HOLD blockers")
            if "UNPROVEN" not in str(record.get("caller_state", "")):
                errors.append(id_ + " external/dynamic caller uncertainty omitted")
        if not isinstance(record.get("required"), list) or not record["required"]:
            errors.append(id_ + " missing P0/P1/P2 obligations")
    return errors


def self_test(root: Path, original: dict) -> None:
    assert not inspect(root, original), inspect(root, original)
    probes = []
    for id_ in CASES:
        mutated = copy.deepcopy(original)
        record = next(x for x in mutated["workflows"] if x["id"] == id_)
        record["decision"] = ("KEEP_HOLD" if id_ == "A2" else "RETIRED_VERIFIED")
        probes.append(("false retirement " + id_, mutated))
        mutated = copy.deepcopy(original)
        record = next(x for x in mutated["workflows"] if x["id"] == id_)
        record["original_blob"] = "0" * 40
        probes.append(("forged source hash " + id_, mutated))
        mutated = copy.deepcopy(original)
        record = next(x for x in mutated["workflows"] if x["id"] == id_)
        record["blockers"] = (["fabricated unresolved A2 blocker"] if id_ == "A2" else [])
        probes.append(("lost blockers " + id_, mutated))
    mutated = copy.deepcopy(original)
    mutated["workflows"].pop()
    probes.append(("omitted owner", mutated))
    mutated = copy.deepcopy(original)
    mutated["science"] = "SCIENCE_PASS"
    probes.append(("unapproved science", mutated))
    mutated = copy.deepcopy(original)
    mutated["workflows"][0]["caller_state"] = "ZERO_PROVEN"
    probes.append(("fabricated caller zero", mutated))
    for id_ in A1_A2_SAME_HEAD_PROOFS:
        mutated = copy.deepcopy(original)
        record = next(x for x in mutated["workflows"] if x["id"] == id_)
        record["live_branch_readback"]["head"] = "0" * 40
        probes.append(("falsified active branch " + id_, mutated))
        mutated = copy.deepcopy(original)
        record = next(x for x in mutated["workflows"] if x["id"] == id_)
        record["same_head_revalidation"]["run_conclusion"] = "success"
        probes.append(("falsified global CI pass " + id_, mutated))
        mutated = copy.deepcopy(original)
        record = next(x for x in mutated["workflows"] if x["id"] == id_)
        record["same_head_revalidation"]["job_id"] = 0
        probes.append(("missing exact job provenance " + id_, mutated))
    # New Wave1-C fail-closed controls: changing any unproved caller status,
    # branch/P3 ownership, original artifact custody, or red CI must reject.
    for id_ in ("A1", "A2"):
        for key, tampered in (
            ("historical_branch_head", "0" * 40),
            ("external_api_gh_controller_callers", "ZERO_PROVEN"),
            ("global_surface_guard", "PASS"),
            ("artifact_custody", "VERIFIED_IMMUTABLE"),
            ("other_same_branch_p3_workflows", []),
            ("integration_head", "0" * 40),
        ):
            mutated = copy.deepcopy(original)
            record = next(x for x in mutated["workflows"] if x["id"] == id_)
            record["wave1_c_followup"][key] = tampered
            probes.append(("Wave1-C falsified " + id_ + " " + key, mutated))
    # Mutation checks for independent original ZIP backup and branch-specific
    # staged cutover. They deliberately reject fake retirement eligibility.
    for id_ in ("A1", "A2"):
        for key, tampered in (
            ("prereq_draft_head", "0" * 40),
            ("prereq_state", "MERGED_VERIFIED"),
            ("caller_zero_proven", True),
            ("final_deletion_authorized", True),
        ):
            mutated = copy.deepcopy(original)
            record = next(x for x in mutated["workflows"] if x["id"] == id_)
            record["wave1_c_closure"][key] = tampered
            probes.append(("Wave1-C closure falsified " + id_ + " " + key, mutated))
    mutated = copy.deepcopy(original)
    record = next(x for x in mutated["workflows"] if x["id"] == "A1")
    record["wave1_c_closure"]["artifact_backup"]["sha256"] = "0" * 64
    probes.append(("Wave1-C original Drive hash falsified", mutated))
    mutated = copy.deepcopy(original)
    record = next(x for x in mutated["workflows"] if x["id"] == "A1")
    record["wave1_c_closure"]["untouched_p3_dd_blob"] = "0" * 40
    probes.append(("Wave1-C P3 source identity falsified", mutated))
    for id_ in ("A3", "A4"):
        mutated = copy.deepcopy(original)
        record = next(x for x in mutated["workflows"] if x["id"] == id_)
        record["staged_candidate"]["status"] = "RETIRED_VERIFIED"
        probes.append(("premature staged acceptance " + id_, mutated))
        mutated = copy.deepcopy(original)
        record = next(x for x in mutated["workflows"] if x["id"] == id_)
        del record["staged_candidate"]
        probes.append(("missing FLOW replacement custody " + id_, mutated))
    for key, fake_value in (
        ("attestation_type", "GITHUB_INDEPENDENTLY_VERIFIED"),
        ("original_blob", "0" * 40),
        ("old_ref_cutover_head", "0" * 40),
        ("old_ref_cutover_state", "MERGED_AND_ACCEPTED"),
        ("backup_readback", "UNVERIFIED"),
        ("p3_dd_blob", "0" * 40),
        ("p3_s6_blob", "0" * 40),
        ("accepted_retirement", True),
    ):
        mutated = copy.deepcopy(original)
        record = next(x for x in mutated["workflows"] if x["id"] == "A1")
        record["a1_owner_retirement"][key] = fake_value
        probes.append(("A1 owner/stage receipt falsified " + key, mutated))
    for key, fake_value in (
        ("attestation", "NOT_ATTESTED"),
        ("attestation_comment_id", 0),
        ("historical_head_after", "0" * 40),
        ("original_blob", "0" * 40),
        ("same_branch_a1_blob", "0" * 40),
        ("same_branch_p3_dd_blob", "0" * 40),
        ("maintained_job_id", 0),
        ("group_a_job_id", 0),
        ("p3", "PASS"),
        ("science", "SCIENCE_PASS"),
    ):
        mutated = copy.deepcopy(original)
        record = next(x for x in mutated["workflows"] if x["id"] == "A2")
        record["a2_owner_retirement"][key] = fake_value
        probes.append(("A2 owner-retirement receipt falsified " + key, mutated))
    mutated = copy.deepcopy(original)
    record = next(x for x in mutated["workflows"] if x["id"] == "A2")
    record["remaining_non_a2_gates"] = []
    probes.append(("A2 falsely declares global clearance", mutated))
    for label, fake in probes:
        assert inspect(root, fake), "negative mutation not rejected: " + label
    # Archived original A1 Git blob is retained in git/independent ZIP provenance,
    # but must no longer be a file on this integration candidate.
    first = original["workflows"][0]
    assert not (root / first["path"]).exists(), "A1_PREMATURE_REINTRODUCTION"
    raw = ("name: A1 Original Trigger\non:\n  push:\n"
           "    branches: [" + first["historical_branch"] + "]\n"
           "    paths: [" + first["path"] + "]\n"
           "permissions:\n  contents: read\n")
    assert not check_trigger(raw, first["path"], first["historical_branch"])
    assert check_trigger(raw.replace(first["historical_branch"], "main", 1),
                         first["path"], first["historical_branch"])
    assert check_trigger(raw.replace("    paths:", "    paths_disabled:", 1),
                         first["path"], first["historical_branch"])
    if not (root / ".github/workflows/issue402-dd-json-p3-smoke-once.yml").is_file():
        assert dd_staged_absence_evidence(root), "DD_SOURCE_ARCHIVE_NOT_VERIFIED"
        print("ISSUE541_GROUP_A_DD_STAGED_ABSENCE_P0_PASS")
    if not (root / ".github/workflows/issue402-hybrid-json-s6-p3-p4-once.yml").is_file():
        # Negative proof: corrupting any of the five staged-retirement
        # requirements or auto-enabling the replacement must be rejected.
        doc_bytes = (root / S6_STAGED_README).read_text(encoding="utf-8")
        replay_bytes = (root / S6_STAGED_REPLAY).read_text(encoding="utf-8")
        assert s6_staged_absence_evidence(doc_bytes, replay_bytes)
        for marker in S6_STAGED_MARKERS:
            assert not s6_staged_absence_evidence(
                doc_bytes.replace(marker, "forged", 1), replay_bytes)
        assert not s6_staged_absence_evidence(
            doc_bytes,
            replay_bytes.replace("  workflow_dispatch:", "  push:", 1))
        print("ISSUE541_GROUP_A_S6_STAGED_ABSENCE_MUTATIONS_6_REJECTED")
    print("ISSUE541_GROUP_A_MUTATION_SELF_TEST=PASS count=" + str(len(probes) + 2))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    root = args.root.resolve()
    doc = json.loads((root / LEDGER).read_text(encoding="utf-8"))
    errors = inspect(root, doc)
    if errors:
        for item in errors:
            print("::error::GROUP_A_CONTRACT: " + item)
        return 1
    if args.self_test:
        self_test(root, doc)
    if args.check:
        for record in doc["workflows"]:
            print(record["id"] + " " + record["decision"] + " | " +
                  record["caller_state"] + " | original=" + record["original_blob"])
        print("ISSUE541_GROUP_A_LEDGER=PASS RETIREMENTS=1_A2_ONLY; A1=STAGED_DELETE_HOLD; GLOBAL_SURFACE_GUARD_NOT_WAIVED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
