"""Controller INIT observations, not per-operation mutation approval.

Run once per controller cycle before INIT advances. This adapter checks local
repository and target identities; it never fetches Samuel contracts. The owner must still authenticate work/checkpoint
history and resolve actual execution routes; each write retains its existing
operation-specific policy, blocker and fresh target checks.
"""
from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from urllib.parse import quote

from libs.command_execution.preflight import PreflightCheck, run_preflight
from .connector_policy_probe import _api, _run, _strict_json

_SHA = re.compile(r"[0-9a-f]{40}\Z")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_FIELDS = {"repository", "work_id", "cycle_id", "controller_sha", "target_branch", "target_sha"}


def parse_start_request(raw: bytes, digest: str, repository: str, trusted_sha: str) -> dict:
    if len(raw) > 16384 or sha256(raw).hexdigest() != digest:
        raise ValueError("REQUEST_DIGEST_MISMATCH")
    request = _strict_json(raw)
    if not isinstance(request, dict) or set(request) != _FIELDS:
        raise ValueError("START_REQUEST_FIELDS_MISMATCH")
    if request["repository"] != repository or request["controller_sha"] != trusted_sha:
        raise ValueError("CONTROLLER_SOURCE_MISMATCH")
    for key in ("controller_sha", "target_sha"):
        if not isinstance(request[key], str) or not _SHA.fullmatch(request[key]):
            raise ValueError("INVALID_REVISION:" + key)
    for key in ("work_id", "cycle_id"):
        if not isinstance(request[key], str) or not _ID.fullmatch(request[key]):
            raise ValueError("INVALID_IDENTITY:" + key)
    branch = request["target_branch"]
    if not isinstance(branch, str) or not branch or branch.startswith("-"):
        raise ValueError("INVALID_TARGET_BRANCH")
    return request


def verify_start(*, raw, digest, repository, trusted_sha, read_head):
    """Read exact main and target before/after the existing generic checks."""
    request = parse_start_request(raw, digest, repository, trusted_sha)
    branch = request["target_branch"]
    target = request["target_sha"]

    def controller_head():
        if read_head(branch) != target:
            raise ValueError("TARGET_HEAD_CHANGED")
        return read_head("main")

    def main_identity():
        return "refs/heads/main@" + trusted_sha

    def target_identity():
        return "refs/heads/" + branch + "@" + target

    observation = run_preflight(
        request_bytes=raw, expected_request_sha256=digest,
        expected_revision=trusted_sha, read_revision=controller_head,
        required_checks=("controller_identity", "target_identity"),
        checks=(PreflightCheck("controller_identity", main_identity),
                PreflightCheck("target_identity", target_identity)),
    )
    return dict(asdict(observation), request=request,
                status="INIT_IDENTITIES_CHECKED", write_authorized=False,
                central_contracts_checked=False,
                work_identity_authenticated=False, checkpoint_checked=False,
                blocker_history_checked=False, execution_routes_verified=False,
                controller_execution_approved=False)



def main():
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("GITHUB_REF") != "refs/heads/main":
        raise ValueError("TRUSTED_MAIN_WORKFLOW_REQUIRED")
    repo = os.environ["GITHUB_REPOSITORY"]
    trusted_sha = os.environ["GITHUB_SHA"]
    raw = os.environ["PREFLIGHT_REQUEST"].encode("utf-8")
    digest = os.environ["PREFLIGHT_REQUEST_SHA256"]
    request = parse_start_request(raw, digest, repo, trusted_sha)
    _run("git", "check-ref-format", "refs/heads/" + request["target_branch"])
    receipt = verify_start(
        raw=raw, digest=digest, repository=repo, trusted_sha=trusted_sha,
        read_head=lambda branch: _api("repos/" + repo + "/git/ref/heads/" + quote(branch, safe="/"))["object"]["sha"],
    )
    receipt.update(run_id=os.environ["GITHUB_RUN_ID"], run_attempt=os.environ["GITHUB_RUN_ATTEMPT"])
    output = Path(os.environ["RUNNER_TEMP"]) / "controller-preflight-receipt.json"
    with output.open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, sort_keys=True, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()
