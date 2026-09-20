"""Thin Physics boundary to the pinned SOL Adapter Runtime 0.2 consumer.

Physics owns request assembly and interpretation only. Registry, adapter lifecycle,
compatibility discovery, selection, JSON-RPC transport, and replay policy remain
owned by the upstream simulation-ontology consumer.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path
import subprocess
from typing import Any, Mapping, Sequence

from .sol_request import SolRequest

SOL_RUNTIME_REVISION = "020e9a979a0b97f2af3cf54758cedf38fecb187a"
SOL_RUNTIME_PACKAGE = "sol-external-runtime-v02-consumer"
SOL_ADAPTER_MOOSE_REVISION = "f35563f0e63e2739cb94a36c450d5d66024aff2a"
ADAPTER_PROTOCOL_VERSION = "0.2"


class SolRuntimeFailureKind(str, Enum):
    VALIDATION = "validation"
    EXECUTION = "execution"
    PROTOCOL = "protocol"
    RUNTIME = "runtime"
    NO_REPLAY_AMBIGUITY = "no_replay_ambiguity"


@dataclass(frozen=True)
class SolRuntimeOutcome:
    kind: SolRuntimeFailureKind | None
    evidence: Mapping[str, Any]

    @property
    def completed(self) -> bool:
        return self.kind is None


def build_runtime_envelope(request: SolRequest) -> dict[str, Any]:
    """Map #278 canonical outputs into the AP0.2 consumer envelope without reinterpretation."""
    target = request.backend_target.get("target")
    capabilities = request.backend_target.get("required_capabilities")
    if not isinstance(target, str) or not target:
        raise ValueError("SolRequest backend_target.target must be a non-empty string")
    if not isinstance(capabilities, (list, tuple)) or not all(
        isinstance(value, str) for value in capabilities
    ):
        raise ValueError("SolRequest required_capabilities must be a string sequence")
    return {
        "target": target,
        "required_capabilities": list(capabilities),
        "plan_request": {
            "adapter_protocol_version": ADAPTER_PROTOCOL_VERSION,
            "plan": request.mapping_plan,
            "realization_spec": request.realization_spec,
        },
    }


def _classify_failure(stderr: str) -> SolRuntimeFailureKind:
    text = stderr.upper()
    if "VALIDATION_REJECTED" in text:
        return SolRuntimeFailureKind.VALIDATION
    if "PROTOCOL_FAILURE" in text:
        return SolRuntimeFailureKind.PROTOCOL
    if "EXECUTION_NOT_COMPLETED" in text:
        return SolRuntimeFailureKind.EXECUTION
    if "RESPONSE" in text and "REPLAY" in text:
        return SolRuntimeFailureKind.NO_REPLAY_AMBIGUITY
    return SolRuntimeFailureKind.RUNTIME


def invoke_runtime_consumer(
    consumer: Path,
    adapter: Path,
    request: SolRequest,
    *,
    timeout_seconds: float = 120.0,
) -> SolRuntimeOutcome:
    """Invoke the upstream consumer as an opaque subprocess boundary."""
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    envelope = build_runtime_envelope(request)
    try:
        proc = subprocess.run(
            [str(consumer), str(adapter)],
            input=json.dumps(envelope, sort_keys=True),
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return SolRuntimeOutcome(
            SolRuntimeFailureKind.NO_REPLAY_AMBIGUITY,
            {
                "exception_type": type(exc).__name__,
                "error": str(exc),
            },
        )
    except OSError as exc:
        return SolRuntimeOutcome(
            SolRuntimeFailureKind.RUNTIME,
            {
                "exception_type": type(exc).__name__,
                "error": str(exc),
            },
        )
    if proc.returncode != 0:
        return SolRuntimeOutcome(
            _classify_failure(proc.stderr),
            {"returncode": proc.returncode, "stderr": proc.stderr.strip()},
        )
    try:
        evidence = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return SolRuntimeOutcome(
            SolRuntimeFailureKind.PROTOCOL,
            {"returncode": proc.returncode, "decode_error": str(exc)},
        )
    if not isinstance(evidence, dict) or evidence.get("status") != "completed":
        return SolRuntimeOutcome(SolRuntimeFailureKind.PROTOCOL, {"payload": evidence})
    if evidence.get("execute_response_loss_replay") != "forbidden":
        return SolRuntimeOutcome(SolRuntimeFailureKind.NO_REPLAY_AMBIGUITY, evidence)
    return SolRuntimeOutcome(None, evidence)
