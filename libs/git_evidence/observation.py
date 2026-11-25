"""Pure dispatch receipt correlation; no execution or acceptance authority.

Consumes independently retrieved GitHub run metadata. Enumeration completeness
is a caller obligation, not a conclusion inferred from an empty page.
"""
from __future__ import annotations

from datetime import datetime
import re


def _time(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timezone required")
    return result


def observe_dispatch(receipt: dict, runs: list[dict], *, repository: str,
                     enumeration_complete: bool, observed_at: str,
                     visibility_grace_seconds: int = 60,
                     run_attempt: int = 1) -> dict:
    """Match direct run identity or explicit run-name correlation on exact SHA."""
    incomplete = {"status": "OBSERVATION_INCOMPLETE", "matched_run_ids": []}
    if (enumeration_complete is not True or not isinstance(receipt, dict)
            or not isinstance(runs, list) or receipt.get("repository") != repository
            or type(visibility_grace_seconds) is not int
            or not 0 <= visibility_grace_seconds <= 3600
            or type(run_attempt) is not int or run_attempt < 1):
        return incomplete
    try:
        requested = _time(receipt["requested_at"])
        observed = _time(observed_at)
        workflow_id = receipt["workflow_id"]
        branch = receipt["ref"]
        sha = receipt["expected_head_sha"]
        correlation = receipt["correlation_id"]
    except (TypeError, ValueError, KeyError, AttributeError):
        return incomplete
    if (type(workflow_id) is not int or workflow_id <= 0
            or not isinstance(branch, str) or not branch
            or not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha)
            or not isinstance(correlation, str) or not correlation
            or observed < requested):
        return incomplete
    direct_id = receipt.get("workflow_run_id")
    prefix = receipt.get("correlation_run_name_prefix")
    if direct_id is not None and (type(direct_id) is not int or direct_id < 1):
        return incomplete
    if direct_id is None and (not isinstance(prefix, str) or not prefix):
        # SHA/ref alone cannot distinguish repeated dispatches.
        return incomplete
    eligible, stale, seen = [], [], set()
    for run in runs:
        if not isinstance(run, dict) or type(run.get("id")) is not int or run["id"] <= 0:
            return incomplete
        rid = run["id"]
        if rid in seen:
            return incomplete
        seen.add(rid)
        if direct_id is not None and rid != direct_id:
            continue
        required = {"workflow_id": workflow_id, "event": "workflow_dispatch",
                    "head_branch": branch, "head_sha": sha, "run_attempt": run_attempt}
        if direct_id is not None:
            mismatches = {k: {"expected": v, "observed": run.get(k)}
                          for k, v in required.items() if run.get(k) != v}
            if mismatches:
                return {"status": "BOUND_RUN_IDENTITY_MISMATCH", "matched_run_ids": [rid],
                        "identity_mismatches": mismatches}
        else:
            # Exclude unrelated runs only on observed contradictory evidence.
            if any(run.get(k) is not None and run[k] != v for k, v in required.items()):
                continue
            title = run.get("display_title")
            if not isinstance(title, str):
                return incomplete
            if title != prefix + correlation:
                continue
            if any(run.get(k) is None for k in required):
                return incomplete
        if (not isinstance(run.get("repository"), dict)
                or run["repository"].get("full_name") != repository
                or not isinstance(run.get("status"), str) or not run["status"]):
            return incomplete
        try:
            created = _time(run["created_at"])
        except (KeyError, TypeError, ValueError, AttributeError):
            return incomplete
        if created > observed:
            return incomplete
        # GitHub timestamps may have only second precision.
        if created < requested.replace(microsecond=0):
            stale.append(rid)
        else:
            eligible.append(run)
    ids = [r["id"] for r in eligible]
    if len(ids) > 1:
        return {"status": "AMBIGUOUS_MATCH", "matched_run_ids": ids}
    if len(ids) == 1:
        run = eligible[0]
        if run["status"] == "completed":
            if not isinstance(run.get("conclusion"), str) or not run["conclusion"]:
                return incomplete
            return {"status": "MATCHED_TERMINAL", "matched_run_ids": ids,
                    "conclusion": run["conclusion"]}
        return {"status": "MATCHED_ACTIVE", "matched_run_ids": ids}
    if stale:
        return {"status": "STALE_ONLY", "matched_run_ids": stale}
    status = ("PENDING_VISIBILITY" if (observed - requested).total_seconds()
              <= visibility_grace_seconds else "NO_MATCH")
    return {"status": status, "matched_run_ids": []}
