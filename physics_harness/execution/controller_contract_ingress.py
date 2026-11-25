"""Narrow request-file ingress for one qualification-only PR.

Only trusted main code executes with Actions write permission. PR contents are
read as data; this is not a general-purpose dispatch, writer, or admission gate.
"""
from __future__ import annotations
import base64
from hashlib import sha1, sha256
import json
from pathlib import Path
import re
from urllib.parse import quote

from .controller_contract_receipt import (
    REPO, WORKFLOW, CONTRACT, SOURCE_PATHS, ContractRequest, dispatch_contract,
)

REPO_ID = 1346502851
OWNER_ID = 189476866
REQUEST_PATH = "automation/controller-requests/checkpoint-contract.json"
BRANCH = re.compile(r"issue-888-checkpoint-qualification-[a-f0-9]{12}\Z")
SHA = re.compile(r"[a-f0-9]{40}\Z")
HASH = re.compile(r"[a-f0-9]{64}\Z")
CI_PATH = ".github/workflows/ci.yml"


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def positive(v):
    return type(v) is int and v > 0


def valid(pattern, value):
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def unique(items):
    result = {}
    for k, v in items:
        require(k not in result, "DUPLICATE_REQUEST_FIELD")
        result[k] = v
    return result


def request_body(raw):
    require(type(raw) is bytes and 0 < len(raw) <= 4096, "REQUEST_SIZE")
    obj = json.loads(raw, object_pairs_hook=unique)
    require(type(obj) is dict and set(obj) == {"schema_version", "expected_main_sha", "expected_contract_sha256", "expected_samuel_pin"}
            and type(obj["schema_version"]) is int and obj["schema_version"] == 1
            and valid(SHA, obj["expected_main_sha"]) and valid(HASH, obj["expected_contract_sha256"])
            and valid(SHA, obj["expected_samuel_pin"]), "REQUEST_SCHEMA")
    return obj


def complete_runs(transport, workflow_id, **filters):
    # GitHub's filtered workflow-run listing can cap results at 1000. Rather
    # than infer absence from a truncated list, refuse oversized inventories.
    require(positive(workflow_id), "WORKFLOW_ID")
    first = transport.get(f"/actions/workflows/{workflow_id}/runs", query={**filters, "per_page": "100", "page": "1"})
    n = first.get("total_count")
    require(type(n) is int and 0 <= n <= 100 and isinstance(first.get("workflow_runs"), list)
            and len(first["workflow_runs"]) == n, "INCOMPLETE_RUN_ENUMERATION")
    runs = first["workflow_runs"]
    require(all(isinstance(x, dict) and positive(x.get("id")) for x in runs)
            and len({x["id"] for x in runs}) == n, "INVALID_RUN_ENUMERATION")
    return runs


def same_repo(obj):
    return isinstance(obj, dict) and obj.get("id") == REPO_ID and obj.get("full_name") == REPO


def owned(obj):
    return isinstance(obj, dict) and obj.get("id") == OWNER_ID


def bind_request(transport, *, root: Path, main_sha: str, upstream_id: int, ingress_id: int, ingress_attempt: int):
    require(valid(SHA, main_sha) and positive(upstream_id) and positive(ingress_id)
            and type(ingress_attempt) is int and ingress_attempt == 1, "INGRESS_IDENTITY_OR_REPLAY")
    upstream = transport.get(f"/actions/runs/{upstream_id}")
    branch, head = upstream.get("head_branch"), upstream.get("head_sha")
    require(upstream.get("id") == upstream_id and upstream.get("path") == CI_PATH
            and upstream.get("event") == "pull_request" and upstream.get("status") == "completed"
            and upstream.get("conclusion") == "success" and upstream.get("run_attempt") == 1
            and same_repo(upstream.get("repository")) and same_repo(upstream.get("head_repository"))
            and owned(upstream.get("actor")) and owned(upstream.get("triggering_actor"))
            and valid(BRANCH, branch) and valid(SHA, head), "UPSTREAM_NOT_AUTHORIZED")
    ingress = transport.get(f"/actions/runs/{ingress_id}")
    require(ingress.get("id") == ingress_id and ingress.get("path") == WORKFLOW
            and ingress.get("event") == "workflow_run" and ingress.get("head_sha") == main_sha
            and ingress.get("head_branch") == "main" and ingress.get("run_attempt") == 1
            and ingress.get("display_title") == "checkpoint-ingress:" + head
            and same_repo(ingress.get("repository")) and same_repo(ingress.get("head_repository")), "INGRESS_RUN_MISMATCH")
    workflow_id = ingress.get("workflow_id")
    pr_list = transport.get("/pulls", query={"state": "open", "head": "HyungseonSong-plasma:" + branch,
                                            "base": "main", "per_page": "100", "page": "1"})
    require(type(pr_list) is list and len(pr_list) == 1, "INDEPENDENT_PR_REQUIRED")
    pr = pr_list[0]
    require(positive(pr.get("number")) and pr.get("state") == "open" and pr.get("draft") is True
            and owned(pr.get("user")) and pr.get("changed_files") in (None, 1)
            and same_repo(pr.get("head", {}).get("repo")) and same_repo(pr.get("base", {}).get("repo"))
            and pr["head"].get("ref") == branch and pr["head"].get("sha") == head
            and pr["base"].get("ref") == "main" and pr["base"].get("sha") == main_sha, "PR_IDENTITY_MISMATCH")
    # A qualification request is one immutable commit containing ONLY the new
    # request file, on current trusted main. Never execute its source code.
    commit = transport.get(f"/commits/{head}")
    files = commit.get("files")
    require(commit.get("sha") == head and [x.get("sha") for x in commit.get("parents", [])] == [main_sha]
            and type(files) is list and len(files) == 1 and files[0].get("filename") == REQUEST_PATH
            and files[0].get("status") == "added", "REQUEST_ONLY_COMMIT_REQUIRED")
    obj = transport.get("/contents/" + quote(REQUEST_PATH, safe="/"), query={"ref": head})
    require(obj.get("type") == "file" and obj.get("path") == REQUEST_PATH and obj.get("encoding") == "base64"
            and obj.get("sha") == files[0].get("sha") and type(obj.get("size")) is int
            and 0 < obj["size"] <= 4096 and isinstance(obj.get("content"), str), "REQUEST_BLOB_MISMATCH")
    raw = base64.b64decode("".join(obj["content"].splitlines()), validate=True)
    require(len(raw) == obj["size"] and sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest() == obj["sha"], "REQUEST_BLOB_SIZE_OR_HASH")
    req = request_body(raw)
    source_hashes = {p: sha256((root / p).read_bytes()).hexdigest() for p in SOURCE_PATHS}
    pin = json.loads((root / "docs/operating_system/central_skills.json").read_bytes())["operating_system"]["revision"]
    require(req["expected_main_sha"] == main_sha and req["expected_contract_sha256"] == source_hashes[CONTRACT]
            and req["expected_samuel_pin"] == pin, "REQUEST_STALE_CONTRACT")
    # Reject reruns, duplicate source CI runs, duplicate ingress invocations,
    # and already visible child dispatches. No automatic retry after ambiguity.
    upstream_runs = complete_runs(transport, upstream.get("workflow_id"), event="pull_request", head_sha=head, branch=branch)
    require([x["id"] for x in upstream_runs] == [upstream_id], "UPSTREAM_AMBIGUOUS")
    ingresses = complete_runs(transport, workflow_id, event="workflow_run", head_sha=main_sha, branch="main")
    require(all(isinstance(x.get("display_title"), str) and x["display_title"] for x in ingresses), "INGRESS_TITLE_MISSING")
    require([x["id"] for x in ingresses if x.get("display_title") == "checkpoint-ingress:" + head] == [ingress_id], "INGRESS_AMBIGUOUS")
    correlation = "checkpoint-request-" + head
    children = complete_runs(transport, workflow_id, event="workflow_dispatch", head_sha=main_sha, branch="main")
    require(all(isinstance(x.get("display_title"), str) and x["display_title"] for x in children), "CHILD_TITLE_MISSING")
    require(not any(x.get("display_title") == "checkpoint-contract:" + correlation for x in children), "CHILD_ALREADY_EXISTS")
    require(transport.get("/git/ref/heads/main").get("object", {}).get("sha") == main_sha
            and transport.get("/git/ref/heads/" + branch).get("object", {}).get("sha") == head, "LIVE_HEAD_CHANGED")
    # PR is re-read independently after the inventory queries.
    live = transport.get(f"/pulls/{pr['number']}")
    require(live.get("state") == "open" and live.get("draft") is True and live.get("merged") is False
            and live.get("head", {}).get("sha") == head and live.get("base", {}).get("sha") == main_sha,
            "LIVE_PR_CHANGED")
    return ContractRequest(main_sha, pin, source_hashes, correlation), {
        "pr_number": pr["number"], "request_head": head, "request_blob": obj["sha"],
        "upstream_run_id": upstream_id, "ingress_run_id": ingress_id,
    }


def execute(transport, *, root, main_sha, upstream_id, ingress_id, ingress_attempt, output, samuel_runtime=None):
    request, binding = bind_request(transport, root=root, main_sha=main_sha, upstream_id=upstream_id,
                                    ingress_id=ingress_id, ingress_attempt=ingress_attempt)
    # Exclusive create before dispatch: no local retry after a response loss.
    # A separate run cannot use this local file as a global durable lock.
    with output.open("x", encoding="utf-8") as f:
        json.dump({**binding, "status": "DISPATCH_OUTCOME_UNKNOWN", "correlation_id": request.correlation_id}, f)
    result = dispatch_contract(request, transport, samuel_runtime=samuel_runtime)
    output.write_text(json.dumps({**binding, "status": "DISPATCH_RETURNED", "dispatch": result}, sort_keys=True, indent=2) + "\n")
    return result
