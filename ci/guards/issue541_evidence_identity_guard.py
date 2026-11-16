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
        with urllib.request.urlopen(req, timeout=45) as response:
            return json.loads(response.read().decode("utf-8"))

    def download(self, artifact_id):
        path = "/actions/artifacts/" + str(artifact_id) + "/zip"
        req = urllib.request.Request(
            self.base + path,
            headers={"Accept": "application/vnd.github+json",
                     "User-Agent": "issue541-evidence-identity-v1",
                     **({"Authorization": "Bearer " + self.token} if self.token else {})})
        with urllib.request.urlopen(req, timeout=75) as response:
            return response.read()


def sha(value, n=40):
    return isinstance(value, str) and bool((SHA40 if n == 40 else SHA64).fullmatch(value))


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
    require(run.get("head_sha") == source, "N11_RUN_SOURCE_SHA_MISMATCH")
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
    require(job.get("head_sha") in (None, source), "JOB_HEAD_SHA_MISMATCH")
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
        require(pr.get("head", {}).get("sha") == record["pr_head_sha"],
                "N11_STALE_PR_HEAD")
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
            artifact.get("workflow_run", {}).get("head_sha") == source,
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
    require(identity.get("checkout_sha", identity.get("source_sha")) ==
            record["checkout_sha"], "N1_INNER_CHECKOUT_SHA_MISMATCH")
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


class MockGitHub:
    """Synthetic only: exercised by --self-test, not exposed to production CLI."""
    def __init__(self, data, blob):
        self.data, self.blob = data, blob
    def get(self, path):
        return self.data[path]
    def download(self, artifact_id):
        return self.blob


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
                       "head": {"sha": source}, "base": {"ref": "main"}},
        "/actions/runs/101": {"id": 101, "run_attempt": 1, "event": "pull_request",
                              "head_sha": source, "status": "completed",
                              "conclusion": "failure", "name": "Repository CI",
                              "repository": {"full_name": REPOSITORY},
                              "pull_requests": [{"number": 578}]},
        "/actions/runs/101/jobs?per_page=100&filter=latest":
            {"jobs": [{"id": 201, "run_id": 101, "name": "CORE Native",
                       "status": "completed", "conclusion": "success"}]},
        "/actions/artifacts/301": {"id": 301, "name": "core-native", "expired": False,
                                    "workflow_run": {"id": 101, "head_sha": source}},
        "/branches/main": {"commit": {"sha": "f" * 40}},
        "/compare/" + source + "..." + "f" * 40:
            {"status": "ahead", "behind_by": 0}}
    return record, data, blob


def self_test():
    r, d, blob = sample()
    require(verify(r, MockGitHub(d, blob))["status"] == "PASS", "SELFTEST_POSITIVE")
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
        ("N11", lambda a, b: b["/pulls/578"]["head"].update(sha="e" * 40)),
        ("N12", lambda a, b: a.update(validation_scope="ALL_NATIVE")),
        ("N13", lambda a, b: a.update(science="SCIENCE_PASS")),
        ("N14", lambda a, b: a.update(binary_sha256="f" * 64)),
        ("N15", lambda a, b: b["/actions/artifacts/301"].update(expired=True)),
        ("N19", lambda a, b: b["/actions/artifacts/301"]["workflow_run"].update(id=505)),
        ("N16", lambda a, b: a.update(workflow_result="success")),
        ("N17", lambda a, b: b["/actions/runs/101"].update(head_sha="e" * 40)),
        ("N18", lambda a, b: a.update(oci_digest="other@sha256:" + "b" * 64)),
    ]
    for name, mutate in cases:
        rr, dd = copy.deepcopy(r), copy.deepcopy(d)
        mutate(rr, dd)
        try:
            verify(rr, MockGitHub(dd, blob))
        except (EvidenceRejected, KeyError):
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
    print("ISSUE541_EVIDENCE_IDENTITY_MUTATION_SELF_TEST=PASS; NEGATIVES=21; SCIENCE_HOLD")


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
        "checkout_sha": identity.get("checkout_sha", identity.get("source_sha")),
        "pr_head_sha": pr["head"]["sha"], "pr_merge_ref_sha": None,
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
