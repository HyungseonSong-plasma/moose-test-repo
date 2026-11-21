#!/usr/bin/env python3
"""Verify GitHub Actions v4 Artifact creation via the independent REST read API.

Does not upload data, start Native computation, or mutate repository state.
Never log the GH_TOKEN, headers, or entire REST response.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def has_receipt(document: dict, artifact_id: int, artifact_name: str) -> bool:
    return any(
        isinstance(item, dict)
        and item.get("id") == artifact_id
        and item.get("name") == artifact_name
        and item.get("expired") is False
        for item in document.get("artifacts", [])
    )


def verify(artifact_id: str, name: str, *, attempts: int = 12,
           delay_seconds: int = 5) -> bool:
    if not re.fullmatch(r"[0-9]{1,20}", artifact_id):
        raise ValueError("ARTIFACT_ID_MISSING_OR_INVALID")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,220}", name):
        raise ValueError("ARTIFACT_NAME_INVALID")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    token = os.environ.get("GH_TOKEN", "")
    if (not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo)
            or not re.fullmatch(r"[0-9]+", run_id) or not token):
        raise ValueError("ARTIFACT_RECEIPT_CONTEXT_MISSING")
    url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/artifacts?per_page=100"
    req = Request(url, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    for index in range(attempts):
        try:
            with urlopen(req, timeout=20) as response:
                document = json.load(response)
            if has_receipt(document, int(artifact_id), name):
                print(f"ISSUE518_ARTIFACT_REST_RECEIPT_PASS id={artifact_id}")
                return True
        except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
            # Transient listing issues are independently retried; no auth details logged.
            pass
        if index + 1 < attempts:
            time.sleep(delay_seconds)
    print("ISSUE518_ARTIFACT_REST_RECEIPT_MISSING", file=sys.stderr)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-id", required=True)
    parser.add_argument("--name", required=True)
    args = parser.parse_args()
    return 0 if verify(args.artifact_id, args.name) else 2


if __name__ == "__main__":
    raise SystemExit(main())
