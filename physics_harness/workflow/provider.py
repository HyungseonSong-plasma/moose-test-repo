"""Small GitHub Actions REST adapter. No token or secrets in evidence."""
from __future__ import annotations

import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from physics_harness.workflow.validator import WorkflowValidationError


REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
WORKFLOW_FILE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]+\.ya?ml\Z")
REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9_./-]{0,220}\Z")


class GitHubActionsProvider:
    def __init__(self, repository: str, token: str | None = None):
        if not isinstance(repository, str) or not REPOSITORY.fullmatch(repository):
            raise WorkflowValidationError("INVALID_GITHUB_REPOSITORY")
        self.repository = repository
        self.token = token if token is not None else os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if not self.token:
            raise WorkflowValidationError("GITHUB_TOKEN_REQUIRED")

    def request(self, method: str, path: str, payload: dict | None = None) -> dict | None:
        url = "https://api.github.com/repos/" + self.repository + "/" + path
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = Request(url, data=body, method=method, headers={
            "Authorization": "Bearer " + self.token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            **({"Content-Type": "application/json"} if body is not None else {}),
        })
        try:
            with urlopen(req, timeout=30) as response:
                data = response.read()
                return json.loads(data) if data else None
        except (HTTPError, URLError, ValueError) as exc:
            # Never leak the authorization header or response body.
            code = getattr(exc, "code", "TRANSPORT")
            raise WorkflowValidationError("GITHUB_ACTIONS_API_ERROR:" + str(code)) from None

    def workflow(self, filename: str) -> dict:
        if not WORKFLOW_FILE.fullmatch(filename):
            raise WorkflowValidationError("INVALID_WORKFLOW_FILENAME")
        return self.request("GET", "actions/workflows/" + quote(filename, safe=""))

    def dispatch(self, filename: str, ref: str) -> None:
        if not WORKFLOW_FILE.fullmatch(filename) or not isinstance(ref, str) or not REF.fullmatch(ref) or ".." in ref:
            raise WorkflowValidationError("INVALID_DISPATCH_SELECTOR")
        self.request("POST", "actions/workflows/" + quote(filename, safe="") +
                     "/dispatches", {"ref": ref})

    def run(self, run_id: int) -> dict:
        if type(run_id) is not int or run_id <= 0:
            raise WorkflowValidationError("INVALID_RUN_ID")
        return self.request("GET", "actions/runs/" + str(run_id))

    def jobs(self, run_id: int) -> list[dict]:
        if type(run_id) is not int or run_id <= 0:
            raise WorkflowValidationError("INVALID_RUN_ID")
        result = []
        for page in range(1, 21):
            payload = self.request("GET", f"actions/runs/{run_id}/jobs?per_page=100&page={page}")
            batch = payload.get("jobs", [])
            if not isinstance(batch, list):
                raise WorkflowValidationError("INVALID_JOBS_RESPONSE")
            result.extend(batch)
            if len(batch) < 100:
                return result
        raise WorkflowValidationError("JOBS_PAGINATION_LIMIT")
