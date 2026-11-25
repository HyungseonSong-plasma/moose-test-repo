"""Independent preflight sequencing and request/revision binding.

Only the trusted caller selects the required checks and supplies authenticated
readers and validation functions. This is neither a policy engine nor a write
authorization mechanism. It does not perform mutations, credential discovery,
network access, fallback, retry or deployment enrollment.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re
from typing import Callable


class PreflightError(RuntimeError):
    """Missing, stale or unsuccessful preflight evidence."""


@dataclass(frozen=True, slots=True)
class PreflightCheck:
    name: str
    verify: Callable[[], str]


@dataclass(frozen=True, slots=True)
class PreflightObservation:
    request_sha256: str
    revision: str
    check_evidence: tuple[tuple[str, str], ...]

    @property
    def write_authorized(self) -> bool:
        return False


def run_preflight(*, request_bytes: bytes, expected_request_sha256: str,
                  expected_revision: str, read_revision: Callable[[], str],
                  required_checks: tuple[str, ...],
                  checks: tuple[PreflightCheck, ...]) -> PreflightObservation:
    """Run the trusted caller's exact ordered checks, bound to request and HEAD.

    A callback must raise on any failed or unknown check; a returned reference
    is only caller-supplied evidence, not an independently verified attestation.
    The caller must ensure the check set is complete for the operation and
    recheck live identity before any separately authorized provider action.
    """
    if (not isinstance(request_bytes, bytes) or not request_bytes
            or not isinstance(expected_request_sha256, str)
            or sha256(request_bytes).hexdigest() != expected_request_sha256):
        raise PreflightError("REQUEST_DIGEST_MISMATCH")
    if (not isinstance(expected_revision, str)
            or not re.fullmatch(r"[0-9a-f]{40}", expected_revision)
            or not callable(read_revision)):
        raise PreflightError("EXACT_REVISION_READER_REQUIRED")
    if (not isinstance(required_checks, tuple) or not required_checks
            or any(not isinstance(name, str) or not name.strip() for name in required_checks)
            or len(set(required_checks)) != len(required_checks)
            or not isinstance(checks, tuple)
            or any(not isinstance(check, PreflightCheck) or not callable(check.verify)
                   for check in checks)
            or tuple(check.name for check in checks) != required_checks):
        raise PreflightError("REQUIRED_CHECK_SET_MISMATCH")
    if read_revision() != expected_revision:
        raise PreflightError("STALE_REVISION_BEFORE_CHECKS")
    observations = []
    for check in checks:
        evidence = check.verify()
        if not isinstance(evidence, str) or not evidence.strip():
            raise PreflightError("CHECK_EVIDENCE_MISSING:" + check.name)
        if read_revision() != expected_revision:
            raise PreflightError("STALE_REVISION_AFTER_CHECK:" + check.name)
        observations.append((check.name, evidence))
    return PreflightObservation(expected_request_sha256, expected_revision,
                                tuple(observations))


__all__ = ["PreflightError", "PreflightCheck", "PreflightObservation", "run_preflight"]
