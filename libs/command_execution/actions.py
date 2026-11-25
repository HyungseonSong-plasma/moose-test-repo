"""Workflow dispatch primitives for an authorized CI caller.

No credential discovery, provider fallback, or implicit retry. The injected
transport is supplied by the trusted execution environment. A dispatch receipt
is not proof that the requested revision actually ran. The workflow itself
must also validate its expected revision before executing side effects.
"""
from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any, Protocol
from urllib.parse import quote


class ActionsDispatchError(RuntimeError):
    """A dispatch prerequisite or response is invalid."""


class ActionsDispatchTransport(Protocol):
    repository: str

    def get(self, path: str, *, query: dict[str, str] | None = None) -> Any: ...

    def request(self, method: str, path: str, *,
                payload: dict[str, Any]) -> tuple[int, Any]: ...


def dispatch_workflow(transport: ActionsDispatchTransport, *, repository: str,
                      workflow: str | int, branch: str, expected_head_sha: str,
                      correlation_id: str, inputs: dict[str, str] | None = None,
                      correlation_input: str | None = "correlation_id",
                      correlation_run_name_prefix: str | None = None) -> dict:
    """Send one dispatch after checking the registered workflow and branch.

    Branch-only in this first stage; tag support is deliberately deferred.
    An uncertain POST result must be reconciled by the caller, never retried
    blindly. There is no atomic compare-and-dispatch operation in this API.
    """
    if (not isinstance(repository, str)
            or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository)
            or getattr(transport, "repository", None) != repository):
        raise ActionsDispatchError("DISPATCH_REPOSITORY_MISMATCH")
    if (not isinstance(expected_head_sha, str)
            or not re.fullmatch(r"[0-9a-f]{40}", expected_head_sha)):
        raise ActionsDispatchError("DISPATCH_EXACT_SHA_REQUIRED")
    if (not isinstance(branch, str) or not branch or branch.startswith(("/", "-"))
            or branch.endswith(("/", ".")) or ".." in branch or "@{" in branch
            or any(not part or part.startswith(".") or part.endswith(".lock")
                   for part in branch.split("/"))
            or not re.fullmatch(r"[A-Za-z0-9_./-]+", branch)):
        raise ActionsDispatchError("DISPATCH_INVALID_BRANCH")
    if not ((type(workflow) is int and workflow > 0) or
            (isinstance(workflow, str) and
             re.fullmatch(r"[A-Za-z0-9_.-]+\.ya?ml", workflow))):
        raise ActionsDispatchError("DISPATCH_INVALID_WORKFLOW")
    if not isinstance(correlation_id, str) or not correlation_id.strip():
        raise ActionsDispatchError("DISPATCH_CORRELATION_REQUIRED")
    if (correlation_run_name_prefix is not None and
            (not isinstance(correlation_run_name_prefix, str)
             or not correlation_run_name_prefix)):
        raise ActionsDispatchError("DISPATCH_INVALID_CORRELATION_PREFIX")
    if inputs is not None and (not isinstance(inputs, dict) or any(
            not isinstance(k, str) or not k or not isinstance(v, str)
            for k, v in inputs.items())):
        raise ActionsDispatchError("DISPATCH_INVALID_INPUTS")
    payload_inputs = dict(inputs or {})
    if correlation_input is not None:
        if not isinstance(correlation_input, str) or not correlation_input:
            raise ActionsDispatchError("DISPATCH_INVALID_CORRELATION_INPUT")
        if (correlation_input in payload_inputs
                and payload_inputs[correlation_input] != correlation_id):
            raise ActionsDispatchError("DISPATCH_CORRELATION_CONFLICT")
        payload_inputs[correlation_input] = correlation_id
    metadata = transport.get("/actions/workflows/" + quote(str(workflow), safe=""))
    if (not isinstance(metadata, dict) or type(metadata.get("id")) is not int
            or metadata["id"] <= 0 or metadata.get("state") != "active"
            or not isinstance(metadata.get("path"), str)
            or not metadata["path"].startswith(".github/workflows/")):
        raise ActionsDispatchError("DISPATCH_WORKFLOW_NOT_ACTIVE")
    if ((type(workflow) is int and metadata["id"] != workflow)
            or (isinstance(workflow, str) and metadata["path"] != ".github/workflows/" + workflow)):
        raise ActionsDispatchError("DISPATCH_WORKFLOW_IDENTITY_MISMATCH")
    ref = transport.get("/git/ref/heads/" + quote(branch, safe="/"))
    if (not isinstance(ref, dict) or ref.get("ref") != "refs/heads/" + branch
            or not isinstance(ref.get("object"), dict)
            or ref["object"].get("type") != "commit"
            or ref["object"].get("sha") != expected_head_sha):
        raise ActionsDispatchError("DISPATCH_HEAD_MISMATCH")
    requested_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    status, response = transport.request(
        "POST", f"/actions/workflows/{metadata['id']}/dispatches",
        payload={"ref": branch, "inputs": payload_inputs, "return_run_details": True},
    )
    if status not in {200, 204}:
        raise ActionsDispatchError("DISPATCH_UNEXPECTED_STATUS")
    if response is not None and not isinstance(response, dict):
        raise ActionsDispatchError("DISPATCH_RESPONSE_UNCERTAIN_RECONCILE")
    run_id = (response or {}).get("workflow_run_id")
    if run_id is not None and (type(run_id) is not int or run_id <= 0):
        raise ActionsDispatchError("DISPATCH_RESPONSE_UNCERTAIN_RECONCILE")
    return {
        "repository": repository, "workflow_id": metadata["id"],
        "workflow_path": metadata["path"], "ref": branch,
        "expected_head_sha": expected_head_sha, "correlation_id": correlation_id,
        "correlation_input": correlation_input,
        "correlation_run_name_prefix": correlation_run_name_prefix,
        "requested_at": requested_at, "workflow_run_id": run_id,
        "dispatch_status": status,
    }
