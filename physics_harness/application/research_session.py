"""Research Mode v0.1: persisted human goal clarification before analysis.

Opt-in, solver independent and fail-closed. No model invocation, automatic
objective inference, physics mutation, simulation, or scientific acceptance.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4
from typing import Any

from physics_harness.specification.research_objective import (
    EVALUATION_SCOPES, ResearchObjective, scope_choices,
)

SCHEMA_VERSION = 1
AWAITING_GOAL = "AWAITING_GOAL"
AWAITING_SCOPE = "AWAITING_SCOPE"
AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
GOAL_CONFIRMED = "GOAL_CONFIRMED"
STATUSES = frozenset({AWAITING_GOAL, AWAITING_SCOPE, AWAITING_CONFIRMATION, GOAL_CONFIRMED})


class ResearchModeError(ValueError):
    """Invalid research-session request, state transition or provenance."""


class ResearchNotReady(ResearchModeError):
    """A research analysis was requested before explicit goal confirmation."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _file_digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _dataset(path: str | Path) -> dict[str, Any]:
    file = Path(path).expanduser().resolve(strict=True)
    if not file.is_file():
        raise ResearchModeError("dataset must be a readable regular file")
    return {"path": str(file), "bytes": file.stat().st_size, "sha256": _file_digest(file)}


def _session_path(path: str | Path) -> Path:
    file = Path(path).expanduser().resolve()
    if file.suffix.lower() != ".json":
        raise ResearchModeError("research session must use a .json path")
    return file


def _validate(record: dict[str, Any]) -> None:
    if not isinstance(record, dict) or record.get("schema_version") != SCHEMA_VERSION:
        raise ResearchModeError("unsupported research session schema")
    if record.get("status") not in STATUSES:
        raise ResearchModeError("invalid research status")
    if not isinstance(record.get("session_id"), str) or not record["session_id"].strip():
        raise ResearchModeError("research session identity missing")
    source = record.get("dataset")
    if not isinstance(source, dict) or set(source) != {"path", "bytes", "sha256"}:
        raise ResearchModeError("dataset provenance incomplete")
    if not isinstance(source["path"], str) or not source["path"]:
        raise ResearchModeError("dataset path invalid")
    if type(source["bytes"]) is not int or source["bytes"] < 0:
        raise ResearchModeError("dataset size invalid")
    if not isinstance(source["sha256"], str) or len(source["sha256"]) != 64:
        raise ResearchModeError("dataset hash invalid")
    if type(record.get("revision")) is not int or record["revision"] < 0:
        raise ResearchModeError("session revision invalid")
    if not isinstance(record.get("events"), list):
        raise ResearchModeError("missing session transition history")
    objective, scope, detail = (
        record.get("objective"), record.get("evaluation_scope"), record.get("scope_detail")
    )
    status = record["status"]
    if status == AWAITING_GOAL:
        if objective is not None or scope is not None or record.get("confirmation") is not None:
            raise ResearchModeError("initial session must not carry an unconfirmed objective")
    else:
        if not isinstance(objective, str) or not objective.strip():
            raise ResearchModeError("goal statement missing")
        if scope is not None:
            ResearchObjective(objective, scope, detail)
        if status == AWAITING_SCOPE and scope is not None:
            raise ResearchModeError("scope clarification state cannot have a scope")
        if status in {AWAITING_CONFIRMATION, GOAL_CONFIRMED} and scope is None:
            raise ResearchModeError("evaluation scope not supplied")
    confirm = record.get("confirmation")
    if status != GOAL_CONFIRMED and confirm is not None:
        raise ResearchModeError("unconfirmed goal carries a confirmation")
    if status == GOAL_CONFIRMED:
        if not isinstance(confirm, dict) or confirm.get("accepted") is not True:
            raise ResearchModeError("human confirmation evidence missing")
        if confirm.get("source") != "explicit_operator_confirmation":
            raise ResearchModeError("goal confirmation provenance missing")
        if confirm.get("revision") != record["revision"] or not confirm.get("at_utc"):
            raise ResearchModeError("goal confirmation revision mismatch")
        if not any(
            isinstance(event, dict) and event.get("type") == "GOAL_CONFIRMED"
            and event.get("revision") == record["revision"]
            for event in record["events"]
        ):
            raise ResearchModeError("goal confirmation transition missing from event ledger")


def _load(path: str | Path) -> dict[str, Any]:
    file = _session_path(path)
    obj = json.loads(file.read_text(encoding="utf-8"))
    _validate(obj)
    return obj


def _save(path: str | Path, record: dict[str, Any], *, create: bool = False) -> dict[str, Any]:
    _validate(record)
    file = _session_path(path)
    file.parent.mkdir(parents=True, exist_ok=True)
    if create and file.exists():
        raise ResearchModeError("research session already exists; refuse overwrite")
    tmp = file.with_name(f".{file.name}.{uuid4().hex}.tmp")
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(record, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        if create and file.exists():
            raise ResearchModeError("research session appeared during initial write")
        os.replace(tmp, file)
    finally:
        tmp.unlink(missing_ok=True)
    return status(path)


def _transition(record: dict[str, Any], event: str) -> None:
    record["revision"] += 1
    record["events"].append(
        {"type": event, "at_utc": _now(), "revision": record["revision"]}
    )


def _verify_data(record: dict[str, Any]) -> None:
    original = record["dataset"]
    try:
        current = _dataset(original["path"])
    except (OSError, ResearchModeError) as exc:
        raise ResearchNotReady("original dataset is no longer available") from exc
    if current != original:
        raise ResearchNotReady("dataset changed since research goal was recorded")


def _question(record: dict[str, Any]) -> dict[str, Any] | None:
    state = record["status"]
    if state == AWAITING_GOAL:
        return {
            "code": "ASK_RESEARCH_GOAL",
            "text": "이 데이터로 무엇을 확인하거나 재현하려고 하시나요?",
        }
    if state == AWAITING_SCOPE:
        return {
            "code": "ASK_EVALUATION_SCOPE",
            "text": (
                "연구 목표를 어떻게 평가하면 좋을까요? 예: 전체 영역 오차를 작게 할까요, "
                "물리적으로 대표적인 프로파일을 일치시킬까요, 주요 특징을 맞출까요?"
            ),
            "options": scope_choices(),
        }
    if state == AWAITING_CONFIRMATION:
        return {
            "code": "CONFIRM_RESEARCH_GOAL",
            "text": (
                f"목표: {record['objective']}; 평가 범위: "
                f"{record['evaluation_scope']}"
                + (f" ({record['scope_detail']})" if record.get("scope_detail") else "")
                + ". 이 기준으로 분석을 진행해도 될까요?"
            ),
        }
    return None


def status(path: str | Path) -> dict[str, Any]:
    record = _load(path)
    try:
        _verify_data(record)
        data_integrity = "MATCH"
    except ResearchNotReady:
        data_integrity = "MISSING_OR_CHANGED"
    return {
        "session_id": record["session_id"],
        "status": record["status"],
        "revision": record["revision"],
        "data_identity": record["dataset"],
        "data_integrity": data_integrity,
        "objective": record["objective"],
        "evaluation_scope": record["evaluation_scope"],
        "scope_detail": record.get("scope_detail"),
        "reused_from": record.get("reused_from"),
        "ready_for_analysis": record["status"] == GOAL_CONFIRMED and data_integrity == "MATCH",
        "next_question": _question(record),
        "confirmation": record.get("confirmation"),
    }


def start(
    data: str | Path, session: str | Path, *, reuse_from: str | Path | None = None,
) -> dict[str, Any]:
    file = _session_path(session)
    if file.exists():
        raise ResearchModeError("research session already exists")
    source = _dataset(data)
    record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "session_id": uuid4().hex,
        "dataset": source,
        "objective": None,
        "evaluation_scope": None,
        "scope_detail": None,
        "status": AWAITING_GOAL,
        "revision": 0,
        "confirmation": None,
        "reused_from": None,
        "events": [{"type": "DATA_RECEIVED", "at_utc": _now(), "revision": 0}],
    }
    if reuse_from is not None:
        earlier = _load(reuse_from)
        if earlier["status"] != GOAL_CONFIRMED:
            raise ResearchModeError("only a previously confirmed goal may be proposed for reuse")
        _verify_data(earlier)
        record["objective"] = earlier["objective"]
        record["evaluation_scope"] = earlier["evaluation_scope"]
        record["scope_detail"] = earlier.get("scope_detail")
        record["reused_from"] = earlier["session_id"]
        record["status"] = AWAITING_CONFIRMATION
        _transition(record, "GOAL_REUSE_PROPOSED")
    return _save(file, record, create=True)


def submit_goal(
    session: str | Path, objective: str, *,
    scope: str | None = None, scope_detail: str | None = None,
) -> dict[str, Any]:
    record = _load(session)
    if record["status"] == GOAL_CONFIRMED:
        raise ResearchModeError("confirmed goal is immutable; start a new research session")
    if not isinstance(objective, str) or not objective.strip():
        raise ResearchModeError("objective must be a non-empty statement")
    if scope is None and scope_detail is not None:
        raise ResearchModeError("scope detail requires a scope")
    if scope is not None:
        ResearchObjective(objective, scope, scope_detail)
    record.update(
        objective=objective.strip(),
        evaluation_scope=scope,
        scope_detail=scope_detail.strip() if scope_detail else None,
        status=AWAITING_SCOPE if scope is None else AWAITING_CONFIRMATION,
        confirmation=None,
    )
    _transition(record, "GOAL_PROPOSED")
    return _save(session, record)


def clarify_scope(
    session: str | Path, scope: str, *, scope_detail: str | None = None,
) -> dict[str, Any]:
    record = _load(session)
    if record["status"] not in {AWAITING_SCOPE, AWAITING_CONFIRMATION}:
        raise ResearchModeError("scope can only be clarified on an unconfirmed goal")
    ResearchObjective(record["objective"], scope, scope_detail)
    record.update(
        evaluation_scope=scope, scope_detail=scope_detail.strip() if scope_detail else None,
        status=AWAITING_CONFIRMATION, confirmation=None,
    )
    _transition(record, "SCOPE_CLARIFIED")
    return _save(session, record)


def confirm(session: str | Path, *, approve: bool) -> dict[str, Any]:
    record = _load(session)
    if record["status"] != AWAITING_CONFIRMATION:
        raise ResearchModeError("explicit approval requires a fully specified, unconfirmed goal")
    if type(approve) is not bool:
        raise ResearchModeError("approval decision must be explicit boolean")
    if not approve:
        record.update(
            status=AWAITING_GOAL, objective=None, evaluation_scope=None,
            scope_detail=None, confirmation=None, reused_from=None,
        )
        _transition(record, "GOAL_REJECTED")
    else:
        ResearchObjective(
            record["objective"], record["evaluation_scope"], record.get("scope_detail")
        )
        _verify_data(record)
        record["status"] = GOAL_CONFIRMED
        _transition(record, "GOAL_CONFIRMED")
        record["confirmation"] = {
            "source": "explicit_operator_confirmation",
            "accepted": True,
            "at_utc": _now(),
            "revision": record["revision"],
        }
    return _save(session, record)


def require_analysis_ready(session: str | Path) -> dict[str, Any]:
    """Application gate for *research-mode* analysis execution entrypoints.

    Existing non-research CLI commands are deliberately not changed by v0.1.
    """
    record = _load(session)
    if record["status"] != GOAL_CONFIRMED:
        raise ResearchNotReady(
            f"RESEARCH_GOAL_UNCONFIRMED:{record['status']}; do not run research analysis"
        )
    _verify_data(record)
    return status(session)


__all__ = [
    "ResearchModeError", "ResearchNotReady", "start", "submit_goal",
    "clarify_scope", "confirm", "status", "require_analysis_ready",
]
