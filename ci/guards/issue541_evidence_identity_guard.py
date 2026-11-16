#!/usr/bin/env python3
"""Wave1-E (#541/#16): verify SHA-scoped GitHub evidence against LIVE provenance.

No merge, P3, or science promotion is performed. Local mock metadata is accepted
ONLY by --self-test, never by the production --audit-live command.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import PurePosixPath, Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile

REPOSITORY = "HyungseonSong-plasma/moose-test-repo"
SCHEMA = "issue541.evidence_identity.v1"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
KINDS = {"PR_HEAD", "PR_MERGE_REF", "MERGED_COMMIT", "POST_MERGE_NATIVE"}
NATIVE_SCOPES = {"CORE_NATIVE_P1_P2", "FLOW_NATIVE_P1_P2",
                 "ARCH_NATIVE_P1_P2", "NATIVE_REGRESSION", "POST_MERGE_NATIVE"}
CORE_MARKERS = (
    "ISSUE541_CORE_FOUR_P1_SOURCE_BINARY_OCI_VERIFIED",
    "ISSUE541_CORE_FOUR_NATIVE_P2_PASS; P3=NOT_RUN; SCIENCE_HOLD",
)
FILES = ("p1_identity.json", "p1.log", "p2.log")


class EvidenceRejected(ValueError):
    pass


def require(ok, reason):
    if not ok:
        raise EvidenceRejected(reason)


class ArtifactRedirect(urllib.request.HTTPRedirectHandler):
    """Allow HTTPS signed-URL redirects but never forward API credentials."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old = urllib.parse.urlsplit(req.full_url)
        new = urllib.parse.urlsplit(newurl)
        require(new.scheme == "https" and bool(new.hostname) and
                new.username is None and new.password is None,
                "ARTIFACT_REDIRECT_NOT_HTTPS")
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is not None and old.netloc != new.netloc:
            # urllib normally copies regular request headers on redirects;
            # signed blob-storage URLs MUST NOT receive the GitHub token.
            redirected.remove_header("Authorization")
        return redirected


class GitHub:
    """Read-only GitHub API: metadata and artifact ZIP from the same repository."""
    def __init__(self, repo=REPOSITORY):
        require(repo == REPOSITORY, "REPOSITORY_NOT_AUTHORIZED")
        self.repo = repo
        self.base = "https://api.github.com/repos/" + repo
        self.token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")

    def get(self, path):
        require(path.startswith("/") and ".." not in path, "API_PATH_INVALID")
        req = urllib.request.Request(
            self.base + path,
            headers={"Accept": "application/vnd.github+json",
                     "User-Agent": "issue541-evidence-identity-v1",
                     **({"Authorization": "Bearer " + self.token} if self.token else {})})
        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise EvidenceRejected(
                "GITHUB_METADATA_HTTP_" + str(exc.code) + ":" + path) from exc

    def job_log(self, job_id):
        path = "/actions/jobs/" + str(job_id) + "/logs"
        req = urllib.request.Request(
            self.base + path,
            headers={"Accept": "application/vnd.github+json",
                     "User-Agent": "issue541-evidence-identity-v1",
                     **({"Authorization": "Bearer " + self.token} if self.token else {})})
        try:
            opener = urllib.request.build_opener(ArtifactRedirect())
            with opener.open(req, timeout=75) as response:
                return response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            raise EvidenceRejected(
                "GITHUB_JOB_LOG_HTTP_" + str(exc.code) + ":" + str(job_id)) from exc

    def download(self, artifact_id):
        path = "/actions/artifacts/" + str(artifact_id) + "/zip"
        req = urllib.request.Request(
            self.base + path,
            headers={"Accept": "application/vnd.github+json",
                     "User-Agent": "issue541-evidence-identity-v1",
                     **({"Authorization": "Bearer " + self.token} if self.token else {})})
        try:
            opener = urllib.request.build_opener(ArtifactRedirect())
            with opener.open(req, timeout=75) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            raise EvidenceRejected(
                "GITHUB_ARTIFACT_ZIP_HTTP_" + str(exc.code) + ":" + str(artifact_id)) from exc


def sha(value, n=40):
    return isinstance(value, str) and bool((SHA40 if n == 40 else SHA64).fullmatch(value))


def checkout_from_job_log(log):
    """Runner-observed git checkout SHA, read independently from GitHub log."""
    require(isinstance(log, str), "CHECKOUT_LOG_UNAVAILABLE")
    hits = re.findall(
        r"\[command\]/usr/bin/git checkout --progress --force ([0-9a-f]{40})\b",
        log)
    require(len(hits) == 1, "INDEPENDENT_CHECKOUT_LOG_MISSING_OR_AMBIGUOUS")
    return hits[0]


def zip_files(blob):
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            result = {}
            for info in archive.infolist():
                p = PurePosixPath(info.filename)
                require(not p.is_absolute() and ".." not in p.parts, "ZIP_PATH_TRAVERSAL")
                require(not info.is_dir() or info.file_size == 0, "ZIP_DIRECTORY_INVALID")
                if not info.is_dir():
                    require(info.filename not in result, "ZIP_DUPLICATE_MEMBER")
                    result[info.filename] = archive.read(info)
            return result
    except (zipfile.BadZipFile, RuntimeError) as exc:
        raise EvidenceRejected("ARTIFACT_ZIP_INVALID") from exc


def pick_member(members, name):
    require(isinstance(name, str) and name and
            not name.startswith("/") and ".." not in PurePosixPath(name).parts,
            "REQUIRED_FILE_PATH_INVALID")
    matching = [path for path in members
                if path == name or path.endswith("/" + name)]
    require(len(matching) == 1, "REQUIRED_ARTIFACT_FILE_MISSING_OR_AMBIGUOUS:" + name)
    require(bool(members[matching[0]]), "REQUIRED_ARTIFACT_FILE_EMPTY:" + name)
    return members[matching[0]]


def verify(record, api):
    """All GitHub and ZIP evidence must be fetched independently from api.

    api is never read from a receipt; only --self-test substitutes a fake API.
    An individual successful job proves just the named scope, not whole CI.
    """
    require(isinstance(record, dict) and record.get("schema") == SCHEMA, "SCHEMA_INVALID")
    require(record.get("repository") == REPOSITORY, "REPOSITORY_MISMATCH")
    kind = record.get("evidence_kind")
    require(kind in KINDS, "EVIDENCE_KIND_INVALID")
    source = record.get("source_sha")
    require(sha(source), "SOURCE_SHA_INVALID")
    require(sha(record.get("checkout_sha")), "CHECKOUT_SHA_INVALID")
    require(source == record["checkout_sha"], "N1_CHECKOUT_SOURCE_MISMATCH")
    require(record.get("target_branch") == "main", "TARGET_BRANCH_NOT_MAIN")
    require(record.get("science") == "SCIENCE_HOLD", "N13_SCIENCE_PROMOTION")
    require(record.get("p3_result") == "NOT_RUN", "N13_P3_PROMOTION")
    require(record.get("result") in {"PASS", "FAIL", "HOLD"}, "RESULT_INVALID")
    scope = record.get("validation_scope")
    require(scope in NATIVE_SCOPES, "SCOPE_UNSUPPORTED_FAIL_CLOSED")
    require(scope != "ALL_NATIVE", "N12_ALL_NATIVE_SCOPE_NOT_PROVEN")
    for key in ("workflow_run_id", "job_id", "pr_number", "run_attempt"):
        require(type(record.get(key)) is int and record[key] > 0, "IDENTITY_NUMBER_INVALID:" + key)
    art_record = record.get("artifact")
    require(isinstance(art_record, dict) and
            type(art_record.get("id")) is int and art_record["id"] > 0 and
            sha(art_record.get("sha256"), 64), "N7_N8_ARTIFACT_ID_HASH_REQUIRED")
    require(isinstance(art_record.get("name"), str) and art_record["name"],
            "ARTIFACT_NAME_REQUIRED")
    require(record.get("event_name") in {"pull_request", "push", "workflow_dispatch"},
            "EVENT_INVALID")
    require(record.get("p0_result") in {"PASS", "FAIL", "UNKNOWN", "NOT_RUN"},
            "P0_STATUS_INVALID")
    for name in ("p1_result", "p2_result"):
        require(record.get(name) in {"PASS", "FAIL", "UNKNOWN", "NOT_RUN"},
                "N6_NATIVE_STATUS_INVALID:" + name)
    require(record["p1_result"] == "PASS" and record["p2_result"] == "PASS",
            "N6_P1_P2_NOT_BOTH_PROVEN")
    require(record.get("result") == "PASS", "EVIDENCE_NOT_A_PASS")
    require(isinstance(record.get("required_files"), list) and
            all(x in record["required_files"] for x in FILES),
            "N7_REQUIRED_ARTIFACT_FILES_NOT_DECLARED")
    require(sha(record.get("binary_sha256"), 64) and
            isinstance(record.get("oci_digest"), str) and
            re.fullmatch(r".+@sha256:[0-9a-f]{64}", record["oci_digest"]),
            "N14_RUNTIME_IDENTITY_MISSING")

    pr = api.get("/pulls/" + str(record["pr_number"]))
    run = api.get("/actions/runs/" + str(record["workflow_run_id"]))
    jobs_page = api.get("/actions/runs/" + str(record["workflow_run_id"]) +
                        "/jobs?per_page=100&filter=latest")
    artifact = api.get("/actions/artifacts/" + str(art_record["id"]))
    require(run.get("id") == record["workflow_run_id"], "N4_RUN_ID_INVALID")
    require(run.get("run_attempt") == record["run_attempt"], "RUN_ATTEMPT_MISMATCH")
    require(run.get("event") == record["event_name"], "RUN_EVENT_MISMATCH")
    # pull_request run.head_sha identifies PR source even when checkout uses
    # the temporary refs/pull/N/merge commit. Keep these distinct.
    expected_run_head = (record.get("pr_head_sha")
                         if kind == "PR_MERGE_REF" else source)
    require(run.get("head_sha") == expected_run_head,
            "N11_RUN_SOURCE_SHA_MISMATCH")
    require(run.get("head_commit", {}).get("id") == expected_run_head,
            "N11_RUN_HEAD_COMMIT_MISMATCH")
    require(run.get("status") == "completed", "RUN_NOT_COMPLETE")
    require(pr.get("number") == record["pr_number"], "N3_PR_NUMBER_MISMATCH")
    require(pr.get("base", {}).get("ref") == "main", "PR_TARGET_MISMATCH")
    require(run.get("repository", {}).get("full_name") == REPOSITORY,
            "RUN_REPOSITORY_MISMATCH")
    run_prs = [x.get("number") for x in run.get("pull_requests") or []]
    # GitHub push runs often omit pull_requests; post-merge ownership is
    # proved by merged PR SHA + main ancestry instead.
    if kind in {"PR_HEAD", "PR_MERGE_REF"}:
        require(record["pr_number"] in run_prs, "N3_RUN_NOT_OWNED_BY_PR")
    require(isinstance(jobs_page.get("jobs"), list), "JOBS_UNAVAILABLE")
    job = next((x for x in jobs_page["jobs"]
                if x.get("id") == record["job_id"]), None)
    require(job is not None and job.get("run_id") == run["id"], "N4_JOB_RUN_MISMATCH")
    require(job.get("status") == "completed" and job.get("conclusion") == "success",
            "N5_JOB_FAILED_OR_INCOMPLETE")
    require(job.get("name") == record.get("job_name"), "JOB_NAME_MISMATCH")
    require(job.get("head_sha") in (None, expected_run_head),
            "JOB_HEAD_SHA_MISMATCH")
    independent_checkout = checkout_from_job_log(api.job_log(job["id"]))
    require(independent_checkout == record["checkout_sha"],
            "N1_GITHUB_JOB_LOG_CHECKOUT_MISMATCH")
    # Checkout alone is not a passing assertion. Read the job step result
    # independently of the artifact's self-reported source_sha.
    assert_step = next(
        (step for step in job.get("steps", [])
         if step.get("name") == "Verify source and exact build image"), None)
    require(assert_step is not None and assert_step.get("conclusion") == "success",
            "N1_CHECKOUT_ASSERTION_STEP_NOT_PROVEN")
    require(record.get("workflow_result") == run.get("conclusion"),
            "WORKFLOW_RESULT_MISMATCH")
    require(record.get("workflow_result") in {"success", "failure", "cancelled",
                                               "timed_out", "skipped", "neutral"},
            "WORKFLOW_STATUS_INVALID")

    if kind in {"PR_HEAD", "PR_MERGE_REF"}:
        require(not pr.get("merged") and pr.get("state") == "open",
                "N9_PREMERGE_PR_NOT_OPEN")
        require(run["event"] == "pull_request", "PR_EVENT_REQUIRED")
        require(sha(record.get("pr_head_sha")), "PR_HEAD_SHA_INVALID")
        # A PR can advance after a successful historical run. The immutable
        # run SHA remains the evidence owner: current PR.head.sha is NOT the
        # source SHA of that old run. Require identical branch and verified
        # non-rewritten ancestry rather than silently rebinding its proof.
        require(run.get("head_branch") == pr.get("head", {}).get("ref"),
                "N11_PR_RUN_BRANCH_MISMATCH")
        current_pr_sha = pr.get("head", {}).get("sha")
        require(sha(current_pr_sha), "N11_CURRENT_PR_HEAD_INVALID")
        historical_pr_sha = record["pr_head_sha"]
        require(historical_pr_sha == run.get("head_sha"),
                "N11_HISTORICAL_PR_HEAD_NOT_RUN_SHA")
        if historical_pr_sha != current_pr_sha:
            ancestry = api.get("/compare/" + historical_pr_sha +
                               "..." + current_pr_sha)
            require(ancestry.get("status") == "ahead" and
                    ancestry.get("behind_by") == 0,
                    "N11_HISTORICAL_PR_HEAD_NOT_ANCESTOR")
        if kind == "PR_HEAD":
            require(source == record["pr_head_sha"], "N2_PR_HEAD_IS_NOT_SOURCE")
            require(record.get("pr_merge_ref_sha") is None and
                    record.get("merged_commit_sha") is None, "N2_MERGE_CLAIM_FOR_HEAD")
        else:
            require(sha(record.get("pr_merge_ref_sha")) and
                    source == record["pr_merge_ref_sha"] and
                    source != record["pr_head_sha"], "N10_MERGE_REF_IDENTITY_INVALID")
            require(record.get("merged_commit_sha") is None,
                    "N10_TEST_MERGE_IS_NOT_ACTUAL_MERGE")
            # Live Git test-merge ref and its parents: no PR API merge_commit_sha
            # presence alone can establish an actual completed merge.
            live_ref = api.get("/git/ref/pull/" + str(record["pr_number"]) + "/merge")
            require(live_ref.get("ref") == "refs/pull/" +
                    str(record["pr_number"]) + "/merge" and
                    live_ref.get("object", {}).get("sha") == source,
                    "N10_MERGE_REF_NOT_VERIFIED")
            merge_commit = api.get("/commits/" + source)
            parents = {x.get("sha") for x in merge_commit.get("parents", [])}
            require(len(parents) >= 2 and record["pr_head_sha"] in parents,
                    "N10_MERGE_REF_NOT_A_TEST_MERGE_OF_PR_HEAD")
            require(pr.get("merge_commit_sha") == source,
                    "N10_PR_TEST_MERGE_SHA_MISMATCH")
    else:
        require(pr.get("merged") is True and pr.get("merged_at"),
                "N9_ACTUAL_MERGE_NOT_CONFIRMED")
        require(run["event"] in {"push", "workflow_dispatch"} and
                run.get("head_branch") == "main",
                "N10_POSTMERGE_EVENT_OR_BRANCH_INVALID")
        require(sha(record.get("merged_commit_sha")) and
                source == record["merged_commit_sha"] and
                source == pr.get("merge_commit_sha"), "N2_MERGE_COMMIT_MISMATCH")
        require(record.get("pr_merge_ref_sha") is None,
                "N10_TEMPORARY_MERGE_REF_REUSED")
        branch = api.get("/branches/main")
        current = branch.get("commit", {}).get("sha")
        require(sha(current), "MAIN_HEAD_NOT_VERIFIED")
        ancestry = api.get("/compare/" + source + "..." + current)
        require(ancestry.get("status") in {"ahead", "identical"} and
                ancestry.get("behind_by") == 0,
                "MERGED_COMMIT_NOT_IN_MAIN_ANCESTRY")

    require(artifact.get("id") == art_record["id"] and
            artifact.get("name") == art_record["name"],
            "ARTIFACT_NAME_OR_ID_MISMATCH")
    require(artifact.get("expired") is False, "N15_ARTIFACT_EXPIRED")
    require(artifact.get("workflow_run", {}).get("id") == run["id"] and
            artifact.get("workflow_run", {}).get("head_sha") == run.get("head_sha"),
            "N3_N15_ARTIFACT_WRONG_RUN_OR_HEAD")
    blob = api.download(art_record["id"])
    digest = hashlib.sha256(blob).hexdigest()
    require(digest == art_record["sha256"], "N8_ARTIFACT_SHA256_MISMATCH")
    published = artifact.get("digest")
    if published is not None:
        require(published == "sha256:" + digest, "ARTIFACT_SERVER_DIGEST_MISMATCH")
    members = zip_files(blob)
    for path in record["required_files"]:
        pick_member(members, path)
    try:
        identity = json.loads(pick_member(members, "p1_identity.json"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise EvidenceRejected("INNER_IDENTITY_INVALID") from exc
    require(identity.get("source_sha") == source, "N1_N11_INNER_SOURCE_SHA_MISMATCH")
    # Legacy artifacts may omit inner checkout_sha. That is NOT used
    # to attest checkout: verified GitHub job logs/steps are mandatory.
    require(identity.get("checkout_sha") in (None, record["checkout_sha"]),
            "N1_INNER_CHECKOUT_SHA_MISMATCH")
    require(identity.get("P1") == "PASS", "N6_P1_IDENTITY_NOT_PASS")
    require(identity.get("oci_image") == record["oci_digest"] and
            identity.get("binary_sha256") == record["binary_sha256"],
            "N14_OCI_OR_BINARY_REBOUND")
    p2_log = pick_member(members, "p2.log").decode("utf-8")
    if scope == "CORE_NATIVE_P1_P2":
        require(all(marker in p2_log for marker in CORE_MARKERS),
                "N6_NATIVE_P2_OWNER_MARKERS_MISSING")
    else:
        # Other waves must supply an owner-specific P2 oracle/marker adapter.
        raise EvidenceRejected("NATIVE_SCOPE_OWNER_ORACLE_NOT_REGISTERED:" + scope)

    return {"schema": SCHEMA, "status": "PASS", "evidence_kind": kind,
            "source_sha": source, "run_id": run["id"], "job_id": job["id"],
            "artifact_id": artifact["id"], "artifact_sha256": digest,
            "validation_scope": scope, "workflow_result": run["conclusion"],
            "repository_ci_result": run["conclusion"] if
            run.get("name") == "Repository CI" else "UNKNOWN",
            "p1_result": "PASS", "p2_result": "PASS", "p3_result": "NOT_RUN",
            "science": "SCIENCE_HOLD",
            "verified_at": datetime.now(timezone.utc).isoformat()}


def verify_historic_merged_ci(api, pr_number, run_id, job_id, artifact_id,
                              expected_sha):
    """Actual merged-main Repository CI, explicitly NOT a Native/P2 receipt.

    Artifacts created before the v1 identity schema may lack internal
    source_sha, so preserve distinct RUN_BOUND_ONLY provenance. Native
    and science remain HOLD / NOT_RUN in this restricted evidence class.
    """
    require(sha(expected_sha), "MERGED_CI_SHA_INVALID")
    pr = api.get("/pulls/" + str(pr_number))
    run = api.get("/actions/runs/" + str(run_id))
    jobs = api.get("/actions/runs/" + str(run_id) +
                   "/jobs?per_page=100&filter=latest")
    artifact = api.get("/actions/artifacts/" + str(artifact_id))
    require(pr.get("number") == pr_number and
            pr.get("merged") is True and pr.get("merged_at") and
            pr.get("base", {}).get("ref") == "main" and
            pr.get("merge_commit_sha") == expected_sha,
            "MERGED_CI_PR_NOT_MERGED_AT_SHA")
    current = api.get("/branches/main").get("commit", {}).get("sha")
    require(sha(current), "MERGED_CI_MAIN_SHA_MISSING")
    ancestry = api.get("/compare/" + expected_sha + "..." + current)
    require(ancestry.get("status") in {"identical", "ahead"} and
            ancestry.get("behind_by") == 0, "MERGED_CI_NOT_MAIN_ANCESTOR")
    require(run.get("id") == run_id and run.get("event") == "push" and
            run.get("head_branch") == "main" and
            run.get("head_sha") == expected_sha and
            run.get("status") == "completed" and
            run.get("conclusion") == "success" and
            run.get("name") == "Repository CI",
            "MERGED_CI_PUSH_RUN_NOT_VERIFIED")
    require(isinstance(jobs.get("jobs"), list), "MERGED_CI_JOB_LIST_INVALID")
    job = next((x for x in jobs["jobs"] if x.get("id") == job_id), None)
    require(job is not None and job.get("run_id") == run_id and
            job.get("name") == "validate" and
            job.get("status") == "completed" and
            job.get("conclusion") == "success", "MERGED_CI_VALIDATE_NOT_PASS")
    require(artifact.get("id") == artifact_id and
            artifact.get("expired") is False and
            artifact.get("workflow_run", {}).get("id") == run_id and
            artifact.get("workflow_run", {}).get("head_sha") == expected_sha,
            "MERGED_CI_ARTIFACT_OWNERSHIP_INVALID")
    blob = api.download(artifact_id)
    digest = hashlib.sha256(blob).hexdigest()
    published = artifact.get("digest")
    if published is not None:
        require(published == "sha256:" + digest, "MERGED_CI_ZIP_DIGEST_INVALID")
    members = zip_files(blob)
    require(bool(members) and all(bool(v) for v in members.values()),
            "MERGED_CI_ZIP_CONTENT_MISSING")
    # Historical archive is from the authoritative GitHub run, but its inner
    # payload has no required v1 source/checkout attestation. Do not reuse
    # this class as POST_MERGE_NATIVE or v1 full-content-identity proof.
    return {
        "schema": SCHEMA, "evidence_kind": "MERGED_COMMIT",
        "validation_scope": "REPOSITORY_CI_ONLY",
        "status": "CI_PROVENANCE_VERIFIED_NATIVE_NOT_PROVEN",
        "source_sha": expected_sha, "checkout_sha": None,
        "merged_commit_sha": expected_sha, "pr_number": pr_number,
        "workflow_run_id": run_id, "job_id": job_id,
        "workflow_result": "success",
        "artifact_id": artifact_id, "artifact_name": artifact.get("name"),
        "artifact_sha256": digest, "artifact_provenance": "GITHUB_RUN_BOUND_ONLY",
        "p1_result": "NOT_RUN", "p2_result": "NOT_RUN",
        "p3_result": "NOT_RUN", "science": "SCIENCE_HOLD",
        "verified_at": datetime.now(timezone.utc).isoformat()
    }


class MockGitHub:
    """Synthetic only: exercised by --self-test, not exposed to production CLI."""
    def __init__(self, data, blob):
        self.data, self.blob = data, blob
    def get(self, path):
        return self.data[path]
    def download(self, artifact_id):
        return self.blob
    def job_log(self, job_id):
        return self.data["/actions/jobs/" + str(job_id) + "/logs"]


def sample():
    source = "a" * 40
    body = {"source_sha": source, "oci_image": "image@sha256:" + "b" * 64,
            "binary_sha256": "c" * 64, "P1": "PASS"}
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("p1_identity.json", json.dumps(body))
        z.writestr("p1.log", "built")
        z.writestr("p2.log", "\n".join(CORE_MARKERS))
    blob = out.getvalue()
    record = {
        "schema": SCHEMA, "repository": REPOSITORY, "evidence_kind": "PR_HEAD",
        "source_sha": source, "checkout_sha": source,
        "pr_head_sha": source, "pr_merge_ref_sha": None, "merged_commit_sha": None,
        "workflow_run_id": 101, "job_id": 201, "run_attempt": 1,
        "event_name": "pull_request", "pr_number": 578, "target_branch": "main",
        "job_name": "CORE Native", "result": "PASS", "validation_scope": "CORE_NATIVE_P1_P2",
        "workflow_result": "failure", "p0_result": "UNKNOWN",
        "p1_result": "PASS", "p2_result": "PASS", "p3_result": "NOT_RUN",
        "science": "SCIENCE_HOLD", "oci_digest": body["oci_image"],
        "binary_sha256": body["binary_sha256"],
        "required_files": list(FILES),
        "artifact": {"id": 301, "name": "core-native", "sha256": hashlib.sha256(blob).hexdigest()}}
    data = {
        "/pulls/578": {"number": 578, "merged": False, "state": "open",
                       "head": {"sha": source, "ref": "integration"},
                       "base": {"ref": "main"}},
        "/actions/runs/101": {"id": 101, "run_attempt": 1, "event": "pull_request",
                              "head_sha": source, "head_branch": "integration",
                              "head_commit": {"id": source},
                              "status": "completed",
                              "conclusion": "failure", "name": "Repository CI",
                              "repository": {"full_name": REPOSITORY},
                              "pull_requests": [{"number": 578}]},
        "/actions/runs/101/jobs?per_page=100&filter=latest":
            {"jobs": [{"id": 201, "run_id": 101, "name": "CORE Native",
                       "status": "completed", "conclusion": "success",
                       "steps": [{"name": "Verify source and exact build image",
                                  "conclusion": "success"}]}]},
        "/actions/jobs/201/logs":
            "[command]/usr/bin/git checkout --progress --force " + source + "\n",
        "/actions/artifacts/301": {"id": 301, "name": "core-native", "expired": False,
                                    "workflow_run": {"id": 101, "head_sha": source}},
        "/git/ref/pull/578/merge":
            {"ref": "refs/pull/578/merge", "object": {"sha": "d" * 40}},
        "/commits/" + "d" * 40:
            {"parents": [{"sha": source}, {"sha": "f" * 40}]},
        "/compare/" + source + "..." + "e" * 40:
            {"status": "ahead", "behind_by": 0},
        "/branches/main": {"commit": {"sha": "f" * 40}},
        "/compare/" + source + "..." + "f" * 40:
            {"status": "ahead", "behind_by": 0}}
    return record, data, blob


def self_test():
    r, d, blob = sample()
    require(verify(r, MockGitHub(d, blob))["status"] == "PASS", "SELFTEST_POSITIVE")
    # A run remains valid after PR head advances, but is NEVER promoted to
    # a new source SHA. A rewritten/diverged PR branch is rejected.
    advanced = copy.deepcopy(d)
    advanced["/pulls/578"]["head"]["sha"] = "e" * 40
    require(verify(r, MockGitHub(advanced, blob))["source_sha"] == r["source_sha"],
            "HISTORICAL_HEAD_POSITIVE_NOT_SOURCE_BOUND")
    broken = copy.deepcopy(advanced)
    broken["/compare/" + r["source_sha"] + "..." + "e" * 40]["status"] = "diverged"
    try:
        verify(r, MockGitHub(broken, blob))
    except EvidenceRejected:
        pass
    else:
        raise AssertionError("N27_REWRITTEN_HEAD_FALSE_PASS")
    cases = [
        ("N1", lambda a, b: a.update(checkout_sha="d" * 40)),
        ("N2", lambda a, b: a.update(evidence_kind="MERGED_COMMIT")),
        ("N3", lambda a, b: b["/actions/artifacts/301"]["workflow_run"].update(id=999)),
        ("N4", lambda a, b: a.update(workflow_run_id=102)),
        ("N5", lambda a, b: b["/actions/runs/101/jobs?per_page=100&filter=latest"]
         ["jobs"][0].update(conclusion="failure")),
        ("N6", lambda a, b: a.update(p2_result="UNKNOWN")),
        ("N7", lambda a, b: a.update(required_files=["p1_identity.json"])),
        ("N8", lambda a, b: a["artifact"].update(sha256="f" * 64)),
        ("N9", lambda a, b: a.update(evidence_kind="MERGED_COMMIT",
                                    merged_commit_sha="a" * 40)),
        ("N10", lambda a, b: a.update(evidence_kind="PR_MERGE_REF",
                                     pr_merge_ref_sha="a" * 40)),
        ("N11", lambda a, b: b["/actions/runs/101"].update(
            head_commit={"id": "e" * 40})),
        ("N28_WRONG_PR_BRANCH", lambda a, b: b["/actions/runs/101"].update(
            head_branch="another-branch")),
        ("N29_UNRELATED_HEAD", lambda a, b: (
            b["/pulls/578"]["head"].update(sha="f" * 40),
            b["/compare/" + "a" * 40 + "..." + "f" * 40].update(
                status="diverged", behind_by=1))),
        ("N12", lambda a, b: a.update(validation_scope="ALL_NATIVE")),
        ("N13", lambda a, b: a.update(science="SCIENCE_PASS")),
        ("N14", lambda a, b: a.update(binary_sha256="f" * 64)),
        ("N15", lambda a, b: b["/actions/artifacts/301"].update(expired=True)),
        ("N19", lambda a, b: b["/actions/artifacts/301"]["workflow_run"].update(id=505)),
        ("N16", lambda a, b: a.update(workflow_result="success")),
        ("N17", lambda a, b: b["/actions/runs/101"].update(head_sha="e" * 40)),
        ("N18", lambda a, b: a.update(oci_digest="other@sha256:" + "b" * 64)),
        ("N25_LOG_WRONG_CHECKOUT", lambda a, b: b.update(
            {"/actions/jobs/201/logs":
             "[command]/usr/bin/git checkout --progress --force " + "e" * 40 + "\n"})),
        ("N26_ASSERTION_STEP_FAILED", lambda a, b:
         b["/actions/runs/101/jobs?per_page=100&filter=latest"]
         ["jobs"][0]["steps"][0].update(conclusion="failure")),
    ]
    for name, mutate in cases:
        rr, dd = copy.deepcopy(r), copy.deepcopy(d)
        mutate(rr, dd)
        try:
            verify(rr, MockGitHub(dd, blob))
        except (EvidenceRejected, KeyError):
            continue
        raise AssertionError("FALSE_PASS_NOT_REJECTED:" + name)
    # Genuine synthetic *temporary* merge-ref fixture. The source run head
    # remains PR_HEAD, while runner checkout and artifact inner source refer
    # to a separate test-merge SHA.
    temp_sha = "d" * 40
    tr, td = copy.deepcopy(r), copy.deepcopy(d)
    tr.update(evidence_kind="PR_MERGE_REF", source_sha=temp_sha,
              checkout_sha=temp_sha, pr_merge_ref_sha=temp_sha)
    td["/pulls/578"]["merge_commit_sha"] = temp_sha
    td["/actions/jobs/201/logs"] = (
        "[command]/usr/bin/git checkout --progress --force " + temp_sha + "\n")
    td["/actions/artifacts/301"]["workflow_run"]["head_sha"] = r["source_sha"]
    inner = json.loads(pick_member(zip_files(blob), "p1_identity.json"))
    inner["source_sha"] = temp_sha
    temp_zip = io.BytesIO()
    with zipfile.ZipFile(temp_zip, "w") as archive:
        archive.writestr("p1_identity.json", json.dumps(inner))
        archive.writestr("p1.log", "built")
        archive.writestr("p2.log", "\n".join(CORE_MARKERS))
    temp_blob = temp_zip.getvalue()
    tr["artifact"]["sha256"] = hashlib.sha256(temp_blob).hexdigest()
    require(verify(tr, MockGitHub(td, temp_blob))["status"] == "PASS",
            "PR_MERGE_REF_POSITIVE_FIXTURE")
    for name, mutate in [
        ("N22_WRONG_REF", lambda a: a["/git/ref/pull/578/merge"]["object"].update(
            sha="e" * 40)),
        ("N23_MISSING_PR_PARENT", lambda a: a["/commits/" + temp_sha].update(
            parents=[{"sha": "f" * 40}, {"sha": "e" * 40}])),
        ("N24_MERGE_CLAIM", lambda a: a["/pulls/578"].update(merged=True)),
    ]:
        trial = copy.deepcopy(td)
        mutate(trial)
        try:
            verify(tr, MockGitHub(trial, temp_blob))
        except EvidenceRejected:
            continue
        raise AssertionError("FALSE_PASS_NOT_REJECTED:" + name)
    # Positive actual-merge fixture must prove ancestry; no fake PR merge acceptance.
    mr, md = copy.deepcopy(r), copy.deepcopy(d)
    mr.update(evidence_kind="MERGED_COMMIT", merged_commit_sha=r["source_sha"],
              pr_merge_ref_sha=None, event_name="push")
    md["/pulls/578"].update(merged=True, merged_at="2026-11-01T00:00:00Z",
                             merge_commit_sha=r["source_sha"], state="closed")
    md["/actions/runs/101"].update(event="push", head_branch="main",
                                    pull_requests=[])
    require(verify(mr, MockGitHub(md, blob))["status"] == "PASS",
            "MERGED_COMMIT_POSITIVE_FIXTURE")
    md["/compare/" + r["source_sha"] + "..." + "f" * 40]["status"] = "diverged"
    try:
        verify(mr, MockGitHub(md, blob))
    except EvidenceRejected:
        pass
    else:
        raise AssertionError("MERGE_ANCESTRY_FALSE_PASS")
    # N7: a declared file is absent from the *actual* ZIP, even when a
    # malicious receipt supplies the correct SHA-256 of that incomplete ZIP.
    incomplete = io.BytesIO()
    with zipfile.ZipFile(incomplete, "w") as archive:
        archive.writestr("p1_identity.json", json.dumps({
            "source_sha": r["source_sha"], "P1": "PASS",
            "oci_image": r["oci_digest"],
            "binary_sha256": r["binary_sha256"]}))
        archive.writestr("p1.log", "built")
    missing_blob = incomplete.getvalue()
    missing_record = copy.deepcopy(r)
    missing_record["artifact"]["sha256"] = hashlib.sha256(missing_blob).hexdigest()
    try:
        verify(missing_record, MockGitHub(d, missing_blob))
    except EvidenceRejected:
        pass
    else:
        raise AssertionError("N7_MISSING_REAL_ZIP_FILE_FALSE_PASS")
    print("ISSUE541_EVIDENCE_IDENTITY_MUTATION_SELF_TEST=PASS; NEGATIVES=29; SCIENCE_HOLD")


def audit_live(args):
    require(args.repo == REPOSITORY, "REPOSITORY_NOT_AUTHORIZED")
    require(sha(args.expected_sha), "EXPECTED_SOURCE_INVALID")
    api = GitHub(args.repo)
    run = api.get("/actions/runs/" + str(args.run_id))
    pr = api.get("/pulls/" + str(args.pr_number))
    job_list = api.get("/actions/runs/" + str(args.run_id) +
                       "/jobs?per_page=100&filter=latest")["jobs"]
    job = next((x for x in job_list if x["id"] == args.job_id), None)
    require(job is not None, "JOB_NOT_FOUND")
    artifact = api.get("/actions/artifacts/" + str(args.artifact_id))
    blob = api.download(args.artifact_id)
    identity = json.loads(pick_member(zip_files(blob), "p1_identity.json"))
    record = {
        "schema": SCHEMA, "repository": args.repo, "evidence_kind": args.kind,
        "source_sha": args.expected_sha,
        "checkout_sha": checkout_from_job_log(api.job_log(args.job_id)),
        "pr_head_sha": run["head_sha"], "pr_merge_ref_sha": None,
        "merged_commit_sha": pr.get("merge_commit_sha") if pr.get("merged") else None,
        "workflow_run_id": args.run_id, "job_id": args.job_id,
        "run_attempt": run["run_attempt"], "event_name": run["event"],
        "pr_number": args.pr_number, "target_branch": "main",
        "job_name": job["name"], "result": "PASS",
        "validation_scope": "CORE_NATIVE_P1_P2",
        "workflow_result": run.get("conclusion"), "p0_result": "UNKNOWN",
        "p1_result": "PASS", "p2_result": "PASS", "p3_result": "NOT_RUN",
        "science": "SCIENCE_HOLD",
        "oci_digest": identity.get("oci_image"),
        "binary_sha256": identity.get("binary_sha256"),
        "required_files": list(FILES),
        "artifact": {"id": args.artifact_id, "name": artifact["name"],
                     "sha256": hashlib.sha256(blob).hexdigest()}}
    result = verify(record, api)
    output = {"claim": "SCOPE_ONLY_NOT_GLOBAL_CI", "identity": record,
              "verification": result}
    if args.output:
        Path(args.output).write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print("ISSUE541_EVIDENCE_IDENTITY_LIVE=" + json.dumps(result, sort_keys=True))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--self-test", action="store_true")
    group.add_argument("--audit-live", action="store_true")
    group.add_argument("--verify-record", metavar="JSON_FILE")
    group.add_argument("--audit-merged-ci", action="store_true")
    ap.add_argument("--repo", default=REPOSITORY)
    ap.add_argument("--run-id", type=int)
    ap.add_argument("--job-id", type=int)
    ap.add_argument("--artifact-id", type=int)
    ap.add_argument("--pr-number", type=int)
    ap.add_argument("--expected-sha")
    ap.add_argument("--kind", choices=sorted(KINDS), default="PR_HEAD")
    ap.add_argument("--output")
    args = ap.parse_args()
    try:
        if args.self_test:
            self_test()
        elif args.audit_merged_ci:
            require(all(type(x) is int and x > 0 for x in
                        (args.run_id, args.job_id, args.artifact_id, args.pr_number)),
                    "MERGED_CI_IDENTIFIERS_REQUIRED")
            result = verify_historic_merged_ci(
                GitHub(args.repo), args.pr_number, args.run_id, args.job_id,
                args.artifact_id, args.expected_sha)
            if args.output:
                Path(args.output).write_text(
                    json.dumps(result, indent=2, sort_keys=True) + "\n")
            print("ISSUE541_HISTORIC_MERGED_CI=" +
                  json.dumps(result, sort_keys=True))
        elif args.verify_record:
            doc = json.loads(Path(args.verify_record).read_text(encoding="utf-8"))
            identity = doc.get("identity", doc)
            result = verify(identity, GitHub(args.repo))
            print("ISSUE541_EVIDENCE_IDENTITY_REPLAY=PASS " +
                  json.dumps(result, sort_keys=True))
        else:
            require(all(type(x) is int and x > 0 for x in
                        (args.run_id, args.job_id, args.artifact_id, args.pr_number)),
                    "LIVE_IDENTIFIERS_REQUIRED")
            audit_live(args)
    except (EvidenceRejected, KeyError, OSError, ValueError) as exc:
        print("ISSUE541_EVIDENCE_IDENTITY=HOLD: " + str(exc), file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
