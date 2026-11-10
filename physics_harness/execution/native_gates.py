"""Backend-neutral P1 build identity gate before any native P2 input check.

P1 evidence is a same-runner build record, not a cryptographic signature or
scientific acceptance. Consumers MUST supply the independent expected source
SHA and pinned OCI image, never trust those expectations from the record.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

from physics_harness.evidence.identity import sha256_file
from physics_harness.execution.runtime import run_command, validate_executable

SCHEMA = "physics-native-p1-evidence-v1"
_PINNED_IMAGE = re.compile(r"^[^\s@]+@sha256:[a-f0-9]{64}$")
_SHA = re.compile(r"^[a-f0-9]{40}$")


class P1GateError(RuntimeError):
    """P2 may not proceed because the P1 build identity is unproven."""


def _source_head(source_root: Path) -> str:
    if not source_root.is_dir():
        raise P1GateError("P1_SOURCE_MISSING")
    try:
        rev = subprocess.run(
            ["git", "-C", str(source_root), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True, timeout=15,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise P1GateError("P1_SOURCE_UNVERIFIED") from exc
    return rev


def _require_identity(
    source_root: Path, binary: Path, *, source_sha: str, image_ref: str,
) -> tuple[Path, Path]:
    root, exe = source_root.resolve(), binary.resolve()
    if not _SHA.fullmatch(source_sha):
        raise P1GateError("P1_SOURCE_SHA_INVALID")
    if not _PINNED_IMAGE.fullmatch(image_ref):
        raise P1GateError("P1_OCI_NOT_DIGEST_PINNED")
    if _source_head(root) != source_sha:
        raise P1GateError("P1_SOURCE_HEAD_MISMATCH")
    if not exe.is_file() or not os.access(exe, os.X_OK):
        raise P1GateError("P1_BINARY_MISSING_OR_NOT_EXECUTABLE")
    try:
        exe.relative_to(root)
    except ValueError as exc:
        raise P1GateError("P1_BINARY_OUTSIDE_SOURCE") from exc
    try:
        validate_executable(exe)
    except (SystemExit, OSError, ValueError) as exc:
        raise P1GateError("P1_BINARY_INVALID") from exc
    return root, exe


def record_p1_success(
    output: Path, *, source_root: Path, binary: Path,
    source_sha: str, image_ref: str,
) -> dict[str, str | int]:
    """Record verified binary identity only AFTER the build step succeeds.

    Exclusive creation prevents a stale status from being silently replaced.
    The CI caller must ensure no binary existed before its build step.
    """
    root, exe = _require_identity(source_root, binary, source_sha=source_sha, image_ref=image_ref)
    status: dict[str, str | int] = {
        "schema": SCHEMA,
        "phase": "P1",
        "status": "PASS",
        "source_sha": source_sha,
        "source_root": str(root),
        "oci_image": image_ref,
        "binary_path": str(exe),
        "binary_sha256": sha256_file(exe),
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("x", encoding="utf-8") as stream:
            json.dump(status, stream, sort_keys=True, indent=2)
            stream.write("\n")
    except FileExistsError as exc:
        raise P1GateError("P1_EVIDENCE_ALREADY_EXISTS") from exc
    return status


def require_p1_success(
    evidence: Path, *, source_root: Path, binary: Path,
    source_sha: str, image_ref: str,
) -> dict[str, str | int]:
    """Fail closed on missing, forged/stale, or mismatched P1 evidence."""
    path = Path(evidence)
    if not path.is_file():
        raise P1GateError("P1_EVIDENCE_MISSING")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise P1GateError("P1_EVIDENCE_INVALID_JSON") from exc
    if not isinstance(data, dict) or data.get("schema") != SCHEMA or data.get("phase") != "P1" or data.get("status") != "PASS":
        raise P1GateError("P1_EVIDENCE_NOT_PASS")
    root, exe = _require_identity(source_root, binary, source_sha=source_sha, image_ref=image_ref)
    expected = {
        "source_sha": source_sha,
        "source_root": str(root),
        "oci_image": image_ref,
        "binary_path": str(exe),
    }
    for field, value in expected.items():
        if data.get(field) != value:
            raise P1GateError(f"P1_EVIDENCE_{field.upper()}_MISMATCH")
    digest = data.get("binary_sha256")
    if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise P1GateError("P1_BINARY_SHA_INVALID")
    if sha256_file(exe) != digest:
        raise P1GateError("P1_BINARY_SHA_MISMATCH")
    return data


def run_p2_checked(
    command: Sequence[str], *, evidence: Path, source_root: Path,
    binary: Path, source_sha: str, image_ref: str,
    cwd: Path, log_path: Path, timeout_seconds: float = 1200,
    success_marker: str | None = None,
    failure_classifier: Callable[[Path, int], dict[str, object]] | None = None,
) -> dict[str, object]:
    """Run P2 only after checking that the *same* P1 binary still exists.

    Caller supplies the platform invocation (local or OCI). Never invokes P3.
    """
    verified = require_p1_success(
        evidence, source_root=source_root, binary=binary,
        source_sha=source_sha, image_ref=image_ref,
    )
    if not command or not any("--check-input" in str(arg) for arg in command):
        raise P1GateError("P2_CHECK_INPUT_COMMAND_REQUIRED")
    if timeout_seconds <= 0:
        raise ValueError("P2 timeout must be positive")
    log_path = Path(log_path)
    if log_path.exists():
        raise P1GateError("P2_LOG_ALREADY_EXISTS")
    try:
        result = run_command(command, cwd=Path(cwd), log_path=log_path, timeout_seconds=timeout_seconds)
        rc, timed_out, elapsed = result.returncode, result.timed_out, result.wall_seconds
    except OSError as exc:
        # Record the infrastructure failure rather than misclassify it as physics.
        log_path.write_text(f"P2 launcher error: {type(exc).__name__}: {exc}\n")
        rc, timed_out, elapsed = 127, False, 0.0
    if timed_out:
        reason = {"status": "HOLD", "class": "ENVIRONMENT_OR_BUILD_FAIL", "reason": "P2_TIMEOUT", "detail": None}
    elif rc in (125, 126, 127):
        reason = {"status": "HOLD", "class": "ENVIRONMENT_OR_BUILD_FAIL", "reason": "P2_LAUNCHER_FAIL", "detail": None}
    elif rc == 0 and success_marker and (not log_path.is_file() or success_marker not in log_path.read_text(errors="replace")):
        reason = {"status": "HOLD", "class": "HARNESS_OR_CONSTRUCTION_FAIL", "reason": "P2_SUCCESS_MARKER_MISSING", "detail": None}
    elif rc == 0:
        reason = {"status": "PASS", "class": None, "reason": None, "detail": None}
    elif failure_classifier is not None:
        reason = failure_classifier(log_path, rc)
    else:
        reason = {"status": "HOLD", "class": "HARNESS_OR_CONSTRUCTION_FAIL", "reason": "NATIVE_CHECK_INPUT_FAIL", "detail": None}
    return {
        "P2": "PASS" if reason["status"] == "PASS" else "HOLD",
        "returncode": rc,
        "timed_out": timed_out,
        "wall_seconds": elapsed,
        "classification": reason,
        "p1_binary_sha256": verified["binary_sha256"],
        "log_sha256": sha256_file(log_path) if log_path.is_file() else None,
    }
