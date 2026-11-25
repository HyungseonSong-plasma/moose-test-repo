"""Controller-local INIT composition; no execution or mutation authority.

The trusted runtime supplies actual evidence verifiers. This adapter only
sequences their observations and binds them to the current cycle and revisions.
It does not implement Samuel's checkpoint, capability or lifecycle evaluators.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import partial
from types import MappingProxyType

from libs.command_execution.preflight import PreflightCheck, PreflightObservation, run_preflight
from .controller_preflight import verify_start


INIT_CHECKS = (
    "central_authority",
    "work_enrollment",
    "checkpoint_history",
    "blocker_history",
    "execution_routes",
)


@dataclass(frozen=True, slots=True)
class CycleInitObservation:
    request: Mapping[str, str]
    identity_evidence: tuple[tuple[str, str], ...]
    observations: PreflightObservation
    status: str = "INIT_EVIDENCE_COLLECTED"

    @property
    def phase(self) -> str:
        return "INIT"

    @property
    def controller_execution_approved(self) -> bool:
        return False

    @property
    def write_authorized(self) -> bool:
        return False


def collect_cycle_init(*, raw: bytes, digest: str, repository: str,
                       trusted_sha: str, read_head: Callable[[str], str],
                       verifiers: Mapping[str, Callable[[Mapping[str, str]], str]],
                       ) -> CycleInitObservation:
    """Collect one cycle's INIT evidence using explicitly supplied trusted ports.

    Each verifier receives the immutable, parsed current request. It must raise
    on failed or unresolved evidence, including an unverified checkpoint or an
    active blocker. A returned reference is not an independent attestation.
    Nothing in this adapter authorizes a next phase or external side effect.
    """
    if (not isinstance(verifiers, Mapping) or set(verifiers) != set(INIT_CHECKS)
            or any(not callable(verifiers[name]) for name in INIT_CHECKS)):
        raise ValueError("INIT_VERIFIER_SET_MISMATCH")
    identity = verify_start(raw=raw, digest=digest, repository=repository,
                            trusted_sha=trusted_sha, read_head=read_head)
    request = MappingProxyType(dict(identity["request"]))
    checks = tuple(PreflightCheck(name, partial(verifiers[name], request))
                   for name in INIT_CHECKS)

    def read_controller_head():
        if read_head(request["target_branch"]) != request["target_sha"]:
            raise ValueError("TARGET_HEAD_CHANGED")
        return read_head("main")

    observations = run_preflight(
        request_bytes=raw, expected_request_sha256=digest,
        expected_revision=trusted_sha, read_revision=read_controller_head,
        required_checks=INIT_CHECKS, checks=checks,
    )
    return CycleInitObservation(request, identity["check_evidence"], observations)
