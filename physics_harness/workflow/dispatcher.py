"""Explicitly authorized workflow_dispatch on an already registered workflow."""
from __future__ import annotations

from physics_harness.workflow.validator import WorkflowValidationError


def dispatch(provider, *, workflow_file: str, ref: str,
             authorize: bool) -> dict:
    if not authorize:
        raise WorkflowValidationError("EXPLICIT_DISPATCH_AUTHORIZATION_REQUIRED")
    info = provider.workflow(workflow_file)
    if not isinstance(info, dict) or info.get("state") != "active":
        raise WorkflowValidationError("WORKFLOW_NOT_REGISTERED_AND_ACTIVE")
    expected = ".github/workflows/" + workflow_file
    if info.get("path") != expected:
        raise WorkflowValidationError("WORKFLOW_PATH_MISMATCH")
    provider.dispatch(workflow_file, ref)
    # REST workflow_dispatch returns 204, without a run ID. Never invent one.
    return {"status": "DISPATCH_ACCEPTED", "run_id": None,
            "workflow_file": workflow_file, "ref": ref}
