"""Read-only CI bootstrap for connector file-create/update policy checks.

This is not a journal deployment, permissions check, or authorization. The
controller must verify prior same-work blocker history separately (and use
its configured gate when present), then recheck the exact request and HEAD
before the connector operation. No candidate code is checked out or run.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
from urllib.parse import quote

from libs.command_execution.preflight import PreflightCheck, run_preflight

_SHA = re.compile(r"[0-9a-f]{40}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_FIELDS = {"repository", "work_id", "capability", "branch", "head_sha", "path",
           "expected_blob_sha", "desired_content_sha256"}
_SOURCE_REPO = "HyungseonSong-plasma/chatgpt-operation"


def _strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("DUPLICATE_JSON_KEY")
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs)


def _run(*args, cwd=None):
    return subprocess.check_output(args, cwd=cwd, timeout=45)


def _api(path):
    return _strict_json(_run("gh", "api", "--method", "GET", path))


def _blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("GITHUB_REF") != "refs/heads/main":
        raise ValueError("TRUSTED_MAIN_WORKFLOW_REQUIRED")
    repository = os.environ["GITHUB_REPOSITORY"]
    trusted_sha = os.environ["GITHUB_SHA"]
    raw = os.environ["PREFLIGHT_REQUEST"].encode("utf-8")
    digest = os.environ["PREFLIGHT_REQUEST_SHA256"]
    if len(raw) > 16_384 or hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("REQUEST_DIGEST_MISMATCH")
    request = _strict_json(raw)
    if not isinstance(request, dict) or set(request) != _FIELDS:
        raise ValueError("REQUEST_FIELDS_MISMATCH")
    if (request["repository"] != repository or not isinstance(request["work_id"], str)
            or not request["work_id"].strip() or request["capability"] not in
            ("GITHUB_FILE_CREATE", "GITHUB_FILE_UPDATE")
            or not isinstance(request["head_sha"], str) or not _SHA.fullmatch(request["head_sha"])
            or not isinstance(request["desired_content_sha256"], str)
            or not _DIGEST.fullmatch(request["desired_content_sha256"])):
        raise ValueError("INVALID_REQUEST_IDENTITY")
    expected = request["expected_blob_sha"]
    create = request["capability"] == "GITHUB_FILE_CREATE"
    if (create and expected is not None) or (not create and
            (not isinstance(expected, str) or not _SHA.fullmatch(expected))):
        raise ValueError("INVALID_EXPECTED_BLOB")

    def head(branch):
        return _api("repos/" + repository + "/git/ref/heads/" + quote(branch, safe="/"))["object"]["sha"]

    if head("main") != trusted_sha:
        raise ValueError("TRUSTED_MAIN_CHANGED")
    manifest = _strict_json(Path("docs/operating_system/central_skills.json").read_bytes())
    pin = manifest["operating_system"]["revision"]
    registry_spec = manifest["capability_registry"]
    if (manifest["source_repository"] != _SOURCE_REPO or not _SHA.fullmatch(pin)
            or registry_spec["path"] != "skills/capability-registry.json"):
        raise ValueError("INVALID_CENTRAL_PIN")
    policy_path = Path("automation/samuel/repository-mutation-policy.json")
    policy_bytes = policy_path.read_bytes()

    with TemporaryDirectory(prefix="connector-preflight-") as central:
        _run("git", "init", "-q", cwd=central)
        _run("git", "fetch", "--quiet", "--depth=1",
             "https://github.com/" + _SOURCE_REPO + ".git", pin, cwd=central)
        _run("git", "checkout", "--quiet", "--detach", "FETCH_HEAD", cwd=central)
        if _run("git", "rev-parse", "HEAD", cwd=central).decode().strip() != pin:
            raise ValueError("CENTRAL_PIN_MISMATCH")
        registry_path = Path(central) / registry_spec["path"]
        registry_bytes = registry_path.read_bytes()
        if _blob(registry_bytes) != registry_spec["expected_blob_sha"]:
            raise ValueError("REGISTRY_BLOB_MISMATCH")
        sys.path.insert(0, str(Path(central) / "src"))
        from chatgpt_operation.repository.branch_preflight import require_allowed_branch
        from chatgpt_operation.repository.mutation import _allowed, normalize_path, parse_policy
        from chatgpt_operation.skills.capability_registry import resolve_providers

        branch = require_allowed_branch(repository=repository, branch=request["branch"],
                                        policy_path=policy_path)
        path = normalize_path(request["path"])
        if path != request["path"]:
            raise ValueError("PATH_NOT_CANONICAL")

        def policy_check():
            policy = parse_policy(_strict_json(policy_bytes))
            if (("create" if create else "update") not in policy.allow_file_actions
                    or not _allowed(path, policy.file_allow, policy.file_deny)):
                raise ValueError("FILE_POLICY_DENIED")
            providers = resolve_providers(request["capability"], registry_path)
            if not providers or (providers[0].name, providers[0].kind, providers[0].priority) != (
                    "github-connector", "external", 10) or (create and len(providers) != 1):
                raise ValueError("CONNECTOR_ROUTE_MISMATCH")
            return _blob(registry_bytes) + ":" + _blob(policy_bytes)

        def target_check():
            # Walk exact commit trees, rather than treating ambiguous HTTP 404
            # or a truncated recursive inventory as proof of file absence.
            commit = _api("repos/" + repository + "/git/commits/" + request["head_sha"])
            tree_sha = commit["tree"]["sha"]
            parts = path.split("/")
            for i, part in enumerate(parts):
                tree = _api("repos/" + repository + "/git/trees/" + tree_sha)
                if tree.get("truncated") is not False:
                    raise ValueError("TREE_INVENTORY_INCOMPLETE")
                hits = [item for item in tree["tree"] if item["path"] == part]
                if not hits and create:
                    return "ABSENT_AT_HEAD:" + request["head_sha"]
                if len(hits) != 1:
                    raise ValueError("FILE_IDENTITY_UNRESOLVED")
                item = hits[0]
                if i < len(parts) - 1:
                    if item["type"] != "tree" or item["mode"] != "040000":
                        raise ValueError("NON_DIRECTORY_PARENT")
                    tree_sha = item["sha"]
                elif (create or item["type"] != "blob" or item["mode"] not in
                      ("100644", "100755") or item["sha"] != expected):
                    raise ValueError("FILE_PRECONDITION_MISMATCH")
                else:
                    return item["sha"]
            raise ValueError("FILE_IDENTITY_UNRESOLVED")

        observation = run_preflight(
            request_bytes=raw, expected_request_sha256=digest,
            expected_revision=request["head_sha"], read_revision=lambda: head(branch),
            required_checks=("pinned_policy", "target_file"),
            checks=(PreflightCheck("pinned_policy", policy_check),
                    PreflightCheck("target_file", target_check)),
        )
    if head("main") != trusted_sha:
        raise ValueError("TRUSTED_MAIN_CHANGED")
    receipt = dict(asdict(observation), status="POLICY_AND_IDENTITY_CHECKED",
                   repository=repository, request=request, central_revision=pin,
                   trusted_main_sha=trusted_sha, run_id=os.environ["GITHUB_RUN_ID"],
                   run_attempt=os.environ["GITHUB_RUN_ATTEMPT"],
                   blocker_history_checked=False, journal_anchor_checked=False,
                   write_authorized=False, desired_content_verified=False)
    output = Path(os.environ["RUNNER_TEMP"]) / "connector-policy-receipt.json"
    with output.open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, sort_keys=True, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()
