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
           "issue-402-dd-plasma-boundary-action", "PRESENT", 43522731185),
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
# UNVERIFIED; A1/A2 originals must remain while the old push branch and
# independent P3 consumers remain. This gate is not a live API read.
WAVE1_C_FIXED = json.loads(r'''{"audit_id":"wave1-c-20261116-live-github-readback","historical_branch_head":"af4a9e896328386723e8bbb957f334e1d83fe75e","historical_branch_comparison":"BEHIND_MAIN_13_AHEAD_0","branch_pr_531":"CLOSED_MERGED_EXACT_HEAD","branch_protected_metadata":false,"detailed_branch_protection":"UNVERIFIED_403_INTEGRATION_FORBIDDEN","other_same_branch_p3_workflows":[".github/workflows/issue402-dd-json-p3-smoke-once.yml",".github/workflows/issue402-hybrid-json-s6-p3-p4-once.yml"],"default_branch_static_caller_search":"SELF_YAML_ONLY_NOT_CALLER_ZERO","original_trigger":"PUSH_EXACT_BRANCH_AND_SELF_PATH_ONLY","workflow_call":"NOT_DECLARED_IN_ORIGINAL","workflow_dispatch":"NOT_DECLARED_IN_ORIGINAL","repository_dispatch":"NOT_DECLARED_IN_ORIGINAL","workflow_run":"NOT_DECLARED_IN_ORIGINAL","cross_branch_dynamic_callers":"UNVERIFIED","external_api_gh_controller_callers":"UNVERIFIED","integration_pr":578,"integration_head":"9e71762a5f45ab755481720e8beba314f59cd021","integration_ci_run":43853584740,"integration_ci_conclusion":"FAILURE","group_a_p0_job":133252079431,"group_a_p0_conclusion":"SUCCESS_27_NEGATIVE_MUTATIONS","global_surface_guard":"FAIL_SIX_OTHER_AND_A1_A2_ORIGINAL_BRANCH_VIOLATIONS","disposition":"KEEP_HOLD_NO_ORIGINAL_REMOVAL_NO_BRANCH_DELETE","science":"SCIENCE_HOLD_P3_NOT_RUN"}''')
WAVE1_C_PER_CASE = json.loads(r'''{"A1":{"historical_run_id":43533803916,"historical_run_conclusion":"SUCCESS","artifact_custody":"ARTIFACT_14088768015_UNEXPIRED_EXPIRES_2026-12-14_BACKUP_NOT_REHASHED","replacement_p0_job":133252079406,"replacement_native_p1_p2_job":133252079180,"replacement_job_conclusion":"SUCCESS","distinct_red_gate":"EXTERNAL_DYNAMIC_CALLER_ZERO_NOT_PROVEN; LEGACY_PUSH_BRANCH_PRESENT; SOURCE_CI_RED; P3_BRANCH_SHARED; FULL_PRESERVATION_UNPROVEN"},"A2":{"historical_run_id":43522731185,"historical_run_conclusion":"SUCCESS","artifact_custody":"NO_ARTIFACT_PUBLISHED_IN_ORIGINAL_RUN","replacement_p0_job":133252079239,"replacement_native_p1_p2_job":null,"replacement_job_conclusion":"SUCCESS","distinct_red_gate":"EXTERNAL_DYNAMIC_CALLER_ZERO_NOT_PROVEN; LEGACY_PUSH_BRANCH_PRESENT; SOURCE_CI_RED; P3_BRANCH_SHARED; FULL_PRESERVATION_UNPROVEN"}}''')


# Independent Drive source bytes and isolated branch sunset prerequisite.
# This is a recorded, fail-closed staging receipt, not CALLER_ZERO_PROVEN.
WAVE1_C_CLOSURE = json.loads(r'''{"A1":{"mode":"STAGED_LEGACY_BRANCH_SHUTDOWN_REVIEW_ONLY","retention":"PRIVATE_INDEPENDENT_COPY_READBACK","proof_date":"2026-11-16","historical_branch":"issue-402-dd-plasma-boundary-action","historical_branch_head":"af4a9e896328386723e8bbb957f334e1d83fe75e","branch_shared_with_p3":true,"branch_must_not_be_deleted":true,"original_workflows_reviewed":45,"branch_write_route":"PUSH_EXACT_SELF_PATH_ONLY","declared_dispatch_or_call_route":false,"cross_branch_external_or_dynamic_callers":"UNVERIFIED","caller_zero_proven":false,"prereq_draft_pr":588,"prereq_draft_head":"85d6968f5155e25eabfca8b503828979d9509506","prereq_base":"issue-402-dd-plasma-boundary-action","prereq_state":"OPEN_DRAFT_NOT_MERGED","prereq_scope":"EXACTLY_TWO_A1_A2_FILES_REMOVED_FROM_CANDIDATE_BRANCH_ONLY","untouched_p3_dd_blob":"068ef7f78b84b45dbf8c678522ada049d4a42b7a","untouched_p3_s6_blob":"485439a723584ca5bbc8632a86c53574b0b1eb9a","original_sha":"bbebff910db3e5659014368043a50b99273d2cdc","artifact_backup":{"drive_file_id":"1OsADIq21_JU4Z4O65t_Hl-_AwjM6Nxf0","github_artifact_id":14088768015,"bytes":2072,"sha256":"de931c0c1dcb95308759a0c67eba42b9fbcd97fcb961b88a92d0b179ca9a8d27","independent_zip_readback":"EXACT_BINARY_AND_HASH_PASS","worm":"NOT_PROVEN"},"final_deletion_authorized":false,"decision":"KEEP_HOLD","science":"SCIENCE_HOLD","p3":"NOT_RUN"},"A2":{"mode":"STAGED_LEGACY_BRANCH_SHUTDOWN_REVIEW_ONLY","retention":"PRIVATE_INDEPENDENT_COPY_READBACK","proof_date":"2026-11-16","historical_branch":"issue-402-dd-plasma-boundary-action","historical_branch_head":"af4a9e896328386723e8bbb957f334e1d83fe75e","branch_shared_with_p3":true,"branch_must_not_be_deleted":true,"original_workflows_reviewed":45,"branch_write_route":"PUSH_EXACT_SELF_PATH_ONLY","declared_dispatch_or_call_route":false,"cross_branch_external_or_dynamic_callers":"UNVERIFIED","caller_zero_proven":false,"prereq_draft_pr":588,"prereq_draft_head":"85d6968f5155e25eabfca8b503828979d9509506","prereq_base":"issue-402-dd-plasma-boundary-action","prereq_state":"OPEN_DRAFT_NOT_MERGED","prereq_scope":"EXACTLY_TWO_A1_A2_FILES_REMOVED_FROM_CANDIDATE_BRANCH_ONLY","untouched_p3_dd_blob":"068ef7f78b84b45dbf8c678522ada049d4a42b7a","untouched_p3_s6_blob":"485439a723584ca5bbc8632a86c53574b0b1eb9a","original_sha":"1931f0b9909507979826812f346d3353f12e333b","artifact_backup":null,"final_deletion_authorized":false,"decision":"KEEP_HOLD","science":"SCIENCE_HOLD","p3":"NOT_RUN"}}''')


# A1-only: this is an immutable account-visible GitHub audit snapshot, not
# positive evidence of *off-platform* controller/scheduler absence.
A1_CALLER_AUDIT = json.loads(r'''{"snapshot_date":"2026-11-16","target":"A1_DD_BOUNDARY_ONLY","original_blob":"bbebff910db3e5659014368043a50b99273d2cdc","workflow_id":417754909,"historical_branch":"issue-402-dd-plasma-boundary-action","historical_head":"af4a9e896328386723e8bbb957f334e1d83fe75e","original_self_path_push_only":true,"api_dispatch_and_workflow_call_not_declared":true,"historical_actions_branch_runs_total":36,"historical_a1_runs":19,"historical_a1_events":["push"],"historical_a1_actors":["HyungseonSong-plasma"],"latest_a1_run_utc":"2026-11-14T00:22:57Z","github_installation_id":155128539,"github_accessible_repos":["HyungseonSong-plasma/chatgpt-operation","HyungseonSong-plasma/codeQA","HyungseonSong-plasma/moose-test-repo","HyungseonSong-plasma/simulation-ontology","HyungseonSong-plasma/sol-adapter-moose"],"accessible_repo_default_branch_exact_literal_a1_reference":"SELF_YAML_ONLY","other_repo_default_branch_exact_literal_a1_reference_count":0,"all_branches_scanned":false,"off_platform_controller_schedules_scanned":false,"owner_external_caller_disposition":"UNVERIFIED","dynamic_gh_api_and_git_push_consumers":"UNVERIFIED","caller_zero_proven":false,"original_a1_preserved":true,"old_ref_cutover_pr_588":"OPEN_DRAFT_A1_A2_SHARED_NOT_EXECUTED","shared_dd_p3_original_blob":"068ef7f78b84b45dbf8c678522ada049d4a42b7a","shared_s6_p3_original_blob":"485439a723584ca5bbc8632a86c53574b0b1eb9a","independently_byte_rehashed_original_zip_sha256":"de931c0c1dcb95308759a0c67eba42b9fbcd97fcb961b88a92d0b179ca9a8d27","artifact_id":14088768015,"artifact_external_worm":"NOT_PROVEN","retirement_authorized":false,"state":"KEEP_HOLD_UNVERIFIED_EXTERNAL_CALLERS","science":"SCIENCE_HOLD","p3":"NOT_RUN"}''')

def a1_static_workflow_callers(workflows: dict[str, str]) -> list[str]:
    """Detect explicit same-repository dispatch/reuse/run callers of the A1 one-shot.

    Dynamic GitHub API or automated git push consumers outside this static
    source set remain explicitly UNVERIFIED. Negative scan != caller-zero.
    """
    target = "issue402-dd-json-boundary-p0-p2-once.yml"
    workflow_id = "417754909"
    workflow_name = "Issue402 DD JSON plasma boundary exact"
    matches = []
    for path, source in workflows.items():
        if path.endswith("/" + target):
            continue
        lines = [line.strip() for line in source.splitlines()
                 if line.strip() and not line.lstrip().startswith("#")]
        for i, line in enumerate(lines):
            window = " ".join(lines[i:i + 4])
            marker = (target in window or workflow_id in window)
            if marker and (
                re.search(r"\bgh\s+workflow\s+run\b", line)
                or re.search(r"\buses:\s*[^ ]*", line) and target in line
                or re.search(r"actions/workflows/", line) and marker
                or re.search(r"\bworkflow_id\s*:", line) and marker
            ):
                matches.append(path + ":" + str(i + 1) + ":direct-caller")
            elif "workflow_run" in line and workflow_name in window:
                matches.append(path + ":" + str(i + 1) + ":workflow-run")
    return sorted(set(matches))


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
    workflow_dir = root / ".github/workflows"
    if workflow_dir.is_dir():
        observed_callers = a1_static_workflow_callers({
            str(path.relative_to(root)): path.read_text(encoding="utf-8")
            for path in sorted(workflow_dir.glob("*.yml"))
        })
        for caller in observed_callers:
            errors.append("A1 newly introduced static workflow caller " + caller)
    else:
        errors.append("A1 canonical workflow inventory directory missing")
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
            ci_file = root / ".github/workflows/ci.yml"
            expected_job = ("issue402_ideal_gas_p0" if id_ == "A3"
                            else "issue402_reaction_material_p0")
            if ci_file.is_file() and "  " + expected_job + ":" not in ci_file.read_text(encoding="utf-8"):
                errors.append(id_ + " maintained P0 owner not in canonical CI")
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
            # the verified still-present live legacy-branch entrypoint.
            observed = {
                "head": A1_A2_LIVE_HEAD,
                "workflow_blob": sha,
                "entrypoint": "PUSH_SELF_PATH_STILL_PRESENT",
                "observed_on": "2026-11-16",
            }
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
            if record.get("wave1_c_a1_caller_audit") != A1_CALLER_AUDIT:
                errors.append("A1 caller audit snapshot missing or fabricated")
            if record.get("decision") != "KEEP_HOLD":
                errors.append("A1 retirement without off-platform caller-zero authorization")
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
        record["decision"] = "RETIRED_VERIFIED"
        probes.append(("false retirement " + id_, mutated))
        mutated = copy.deepcopy(original)
        record = next(x for x in mutated["workflows"] if x["id"] == id_)
        record["original_blob"] = "0" * 40
        probes.append(("forged source hash " + id_, mutated))
        mutated = copy.deepcopy(original)
        record = next(x for x in mutated["workflows"] if x["id"] == id_)
        record["blockers"] = []
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
    # A1-only receipt must reject silent upgrades of unscanned services,
    # owner attestation, historical branch state or the actual disposition.
    for field, forged in (
        ("owner_external_caller_disposition", "ZERO_PROVEN"),
        ("dynamic_gh_api_and_git_push_consumers", "NONE"),
        ("caller_zero_proven", True),
        ("retirement_authorized", True),
        ("historical_head", "0" * 40),
        ("all_branches_scanned", True),
    ):
        bad = copy.deepcopy(original)
        a1 = next(x for x in bad["workflows"] if x["id"] == "A1")
        a1["wave1_c_a1_caller_audit"][field] = forged
        probes.append(("A1 forged caller audit " + field, bad))
    synthetic_callers = (
        ("GH_CLI", "run: gh workflow run issue402-dd-json-boundary-p0-p2-once.yml"),
        ("WORKFLOW_REUSE", "steps:\n  - uses: ./.github/workflows/issue402-dd-json-boundary-p0-p2-once.yml"),
        ("EXPLICIT_API", "run: gh api repos/o/r/actions/workflows/417754909/dispatches"),
        ("WORKFLOW_RUN", "on:\n  workflow_run:\n    workflows: [Issue402 DD JSON plasma boundary exact]"),
    )
    for label, synthetic in synthetic_callers:
        assert a1_static_workflow_callers({
            ".github/workflows/a1-consumer.yml": synthetic
        }), "A1_STATIC_CALLER_FALSE_NEGATIVE:" + label
    for id_ in ("A3", "A4"):
        mutated = copy.deepcopy(original)
        record = next(x for x in mutated["workflows"] if x["id"] == id_)
        record["staged_candidate"]["status"] = "RETIRED_VERIFIED"
        probes.append(("premature staged acceptance " + id_, mutated))
        mutated = copy.deepcopy(original)
        record = next(x for x in mutated["workflows"] if x["id"] == id_)
        del record["staged_candidate"]
        probes.append(("missing FLOW replacement custody " + id_, mutated))
    for label, fake in probes:
        assert inspect(root, fake), "negative mutation not rejected: " + label
    first = original["workflows"][0]
    raw = (root / first["path"]).read_text(encoding="utf-8")
    assert check_trigger(raw.replace(first["historical_branch"], "main", 1),
                         first["path"], first["historical_branch"])
    assert check_trigger(raw.replace("    paths:", "    paths_disabled:", 1),
                         first["path"], first["historical_branch"])
    print("ISSUE541_A1_CALLER_STATIC_MUTATIONS=PASS count=4")
    print("ISSUE541_GROUP_A_MUTATION_SELF_TEST=PASS count=" + str(len(probes) + 2 + 4))


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
        print("ISSUE541_GROUP_A_LEDGER=PASS RETIREMENTS=0 GLOBAL_SURFACE_GUARD_NOT_WAIVED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
