"""Bounded, read-only GitHub Actions REST access.

Run and jobs methods observe the current attempt, not historical attempt
endpoints. Metadata and archive bytes do not attest execution or semantics.
"""
from __future__ import annotations

import json
from typing import Protocol
from urllib.request import Request, HTTPRedirectHandler, build_opener
from urllib.parse import urlsplit


class ActionsReadSource(Protocol):
    def run(self, repository: str, run_id: int) -> dict: ...
    def jobs(self, repository: str, run_id: int) -> list[dict]: ...
    def artifacts(self, repository: str, run_id: int) -> list[dict]: ...
    def archive(self, repository: str, artifact_id: int) -> bytes: ...


class GitHubActionsRestReader:
    """GitHub REST HTTPS read-only adapter. No workflow dispatch or mutation.

    REST metadata authenticates association with GitHub's database, *not* the
    execution environment or artifact content's scientific/semantic meaning.
    """

    def __init__(self, token: str | None = None, *, timeout: float = 15.0):
        if token is not None and (not isinstance(token, str) or not token.strip()):
            raise ValueError("INVALID_GITHUB_TOKEN")
        if not isinstance(timeout, (float, int)) or not 0 < timeout <= 120:
            raise ValueError("INVALID_GITHUB_TIMEOUT")
        self._token = token
        self._timeout = timeout

    def _read(self, endpoint: str, *, byte_limit: int, archive: bool = False) -> bytes:
        if not endpoint.startswith("/repos/") or ".." in endpoint:
            raise ValueError("INVALID_GITHUB_API_PATH")
        headers = {"Accept": "application/vnd.github+json",
                   "X-GitHub-Api-Version": "2022-11-28",
                   "User-Agent": "Moose-Naming-Actions-Audit-v0.7"}
        if self._token:
            headers["Authorization"] = "Bearer " + self._token
        request = Request("https://api.github.com" + endpoint, headers=headers)

        class ControlledRedirect(HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, hdrs, newurl):
                if not archive or urlsplit(newurl).scheme != "https":
                    raise ValueError("UNEXPECTED_GITHUB_REDIRECT")
                # Artifacts are downloaded through temporary signed redirects;
                # never forward a GitHub API bearer token to that host.
                return Request(newurl, headers={"Accept": "application/zip",
                                                "User-Agent": "Moose-Naming-Actions-Audit-v0.7"},
                               method="GET")

        with build_opener(ControlledRedirect()).open(request, timeout=self._timeout) as response:
            if urlsplit(response.geturl()).scheme != "https":
                raise ValueError("NON_HTTPS_ACTIONS_RESPONSE")
            data = response.read(byte_limit + 1)
        if len(data) > byte_limit:
            raise ValueError("GITHUB_RESPONSE_TOO_LARGE")
        return data

    def _json(self, endpoint: str) -> dict:
        value = json.loads(self._read(endpoint, byte_limit=4_000_000))
        if not isinstance(value, dict):
            raise ValueError("INVALID_GITHUB_JSON_BODY")
        return value

    def run(self, repository: str, run_id: int) -> dict:
        return self._json(f"/repos/{repository}/actions/runs/{run_id}")

    def _paged(self, repository: str, run_id: int, component: str, key: str) -> list[dict]:
        # GitHub paginates both jobs and artifact collections. Never mistake a
        # truncated page for complete evidence of absent consumers/artifacts.
        observed: list[dict] = []
        total = None
        for page in range(1, 6):
            data = self._json(f"/repos/{repository}/actions/runs/{run_id}/{component}?per_page=100&page={page}")
            part = data.get(key)
            count = data.get("total_count")
            if not isinstance(part, list) or type(count) is not int or count < 0:
                raise ValueError("INVALID_GITHUB_PAGINATION")
            if total is None:
                total = count
            elif total != count:
                raise ValueError("GITHUB_PAGINATION_CHANGED_DURING_READ")
            if any(not isinstance(x, dict) for x in part):
                raise ValueError("INVALID_GITHUB_RECORD")
            observed.extend(part)
            if len(observed) >= total:
                if len(observed) != total:
                    raise ValueError("GITHUB_PAGINATION_DUPLICATE_OR_OVERFLOW")
                return observed
            if len(part) != 100:
                raise ValueError("INCOMPLETE_GITHUB_PAGINATION")
        raise ValueError("GITHUB_PAGINATION_BUDGET_EXCEEDED")

    def jobs(self, repository: str, run_id: int) -> list[dict]:
        return self._paged(repository, run_id, "jobs", "jobs")

    def artifacts(self, repository: str, run_id: int) -> list[dict]:
        return self._paged(repository, run_id, "artifacts", "artifacts")

    def archive(self, repository: str, artifact_id: int) -> bytes:
        return self._read(f"/repos/{repository}/actions/artifacts/{artifact_id}/zip", byte_limit=20_000_000, archive=True)


__all__ = ["ActionsReadSource", "GitHubActionsRestReader"]
