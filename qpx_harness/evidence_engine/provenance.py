"""Attempt/build provenance helpers owned by the unified evidence engine."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

_ATTEMPT_RE = re.compile(r"^attempt_(?P<id>.+)$")
_ZERO_SHA = "0" * 40


def artifact_created_utc() -> str:
    """Return an explicit metadata timestamp for artifact creation."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def infer_attempt_id(attempt_dir: Path) -> str:
    """Infer the attempt identifier from ``attempt_<id>`` directory naming."""
    match = _ATTEMPT_RE.match(attempt_dir.name)
    if match is None:
        raise ValueError(
            f"attempt directory must match 'attempt_<id>': {attempt_dir.as_posix()}"
        )
    return match.group("id")


def write_attempt_identity(
    attempt_dir: Path,
    *,
    attempt_id: str,
    qpx_build_identity: Mapping[str, Any],
    probe_plan_contract_digest: str | None = None,
) -> Path:
    """Write a deterministic attempt-level identity manifest."""
    payload: dict[str, Any] = {
        "schema_version": 1,
        "attempt_id": str(attempt_id),
        "attempt_dir": attempt_dir.as_posix(),
        "qpx_build_identity": dict(qpx_build_identity),
    }
    if probe_plan_contract_digest is not None:
        payload["probe_plan_contract_digest"] = str(probe_plan_contract_digest)
    path = attempt_dir / "attempt_identity.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return path


def load_attempt_identity(attempt_dir: Path) -> dict[str, Any]:
    """Load the attempt-level identity manifest."""
    path = attempt_dir / "attempt_identity.json"
    if not path.is_file():
        raise FileNotFoundError(f"missing attempt identity manifest: {path}")
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError(f"attempt identity manifest is not an object: {path}")
    return payload


def normalize_git_commit(value: Any) -> str | None:
    """Normalize a git commit identifier without manufacturing identity."""
    if value is None:
        return None
    text = str(value).strip()
    if not text or text == _ZERO_SHA:
        return None
    return text


def normalize_image_reference(value: Any) -> str | None:
    """Normalize an image digest/reference while preserving provenance."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.startswith("sha256:"):
        digest = text[len("sha256:") :].lower()
        if len(digest) == 64 and all(ch in "0123456789abcdef" for ch in digest):
            return f"sha256:{digest}"
        return None
    return text


def canonical_identity_fields(identity: Mapping[str, Any] | None) -> dict[str, str | None]:
    """Return canonical build-identity fields used across evidence summaries."""
    source = dict(identity or {})
    git_commit = normalize_git_commit(
        source.get("git_commit") or source.get("identity_commit")
    )
    image_reference = normalize_image_reference(
        source.get("image_reference")
        or source.get("image_digest")
        or source.get("image_reference_raw")
        or source.get("identity_image_reference")
    )
    return {
        "git_commit": git_commit,
        "image_reference": image_reference,
    }


def canonical_identity_annotations(
    identity: Mapping[str, Any] | None,
) -> dict[str, str]:
    """Return explicit quality annotations for canonical identity fields."""
    fields = canonical_identity_fields(identity)
    return {
        "git_commit_status": "verified" if fields["git_commit"] else "unproven",
        "image_reference_status": (
            "verified" if fields["image_reference"] else "unproven"
        ),
    }


__all__ = [
    "artifact_created_utc",
    "canonical_identity_annotations",
    "canonical_identity_fields",
    "infer_attempt_id",
    "load_attempt_identity",
    "normalize_git_commit",
    "normalize_image_reference",
    "write_attempt_identity",
]
