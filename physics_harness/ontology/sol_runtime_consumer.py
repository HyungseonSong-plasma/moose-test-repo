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
import tempfile
from typing import Any, Mapping

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
    if not isinstance(capabilities, (list, tuple)) or not all(isinstance(value, str) for value in capabilities):
        raise ValueError("SolRequest required_capabilities must be a string sequence")
    return {"target": target, "required_capabilities": list(capabilities), "plan_request": {"adapter_protocol_version": ADAPTER_PROTOCOL_VERSION, "plan": request.mapping_plan, "realization_spec": request.realization_spec}}

def _classify_failure(stderr: str) -> SolRuntimeFailureKind:
    text = stderr.upper()
    if "VALIDATION_REJECTED" in text: return SolRuntimeFailureKind.VALIDATION
    if "PROTOCOL_FAILURE" in text: return SolRuntimeFailureKind.PROTOCOL
    if "EXECUTION_NOT_COMPLETED" in text: return SolRuntimeFailureKind.EXECUTION
    return SolRuntimeFailureKind.RUNTIME

def invoke_runtime_consumer(consumer: Path, adapter: Path, request: SolRequest, *, timeout_seconds: float = 120.0) -> SolRuntimeOutcome:
    """Invoke the upstream consumer through its supported ``run`` CLI surface."""
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    envelope = build_runtime_envelope(request)
    request_path: Path | None = None
    outcome: SolRuntimeOutcome | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as handle:
            json.dump(envelope, handle, sort_keys=True)
            request_path = Path(handle.name)
        try:
            proc = subprocess.run([str(consumer), "run", str(adapter), str(request_path)], text=True, capture_output=True, timeout=timeout_seconds, check=False)
        except subprocess.TimeoutExpired as exc:
            outcome = SolRuntimeOutcome(SolRuntimeFailureKind.NO_REPLAY_AMBIGUITY, {"exception_type": type(exc).__name__, "error": str(exc)})
        except OSError as exc:
            outcome = SolRuntimeOutcome(SolRuntimeFailureKind.RUNTIME, {"exception_type": type(exc).__name__, "error": str(exc)})
        if outcome is None:
            if proc.returncode != 0:
                outcome = SolRuntimeOutcome(_classify_failure(proc.stderr), {"returncode": proc.returncode, "stderr": proc.stderr.strip()})
            else:
                try:
                    evidence = json.loads(proc.stdout)
                except json.JSONDecodeError as exc:
                    outcome = SolRuntimeOutcome(SolRuntimeFailureKind.NO_REPLAY_AMBIGUITY, {"returncode": proc.returncode, "decode_error": str(exc)})
                else:
                    if not isinstance(evidence, dict) or evidence.get("status") != "completed":
                        outcome = SolRuntimeOutcome(SolRuntimeFailureKind.NO_REPLAY_AMBIGUITY, {"payload": evidence})
                    elif evidence.get("execute_response_loss_replay") != "forbidden":
                        outcome = SolRuntimeOutcome(SolRuntimeFailureKind.NO_REPLAY_AMBIGUITY, evidence)
                    else:
                        outcome = SolRuntimeOutcome(None, evidence)
    except OSError as exc:
        outcome = SolRuntimeOutcome(SolRuntimeFailureKind.RUNTIME, {"exception_type": type(exc).__name__, "error": str(exc)})
    finally:
        if request_path is not None:
            try:
                request_path.unlink(missing_ok=True)
            except OSError as exc:
                cleanup = {"cleanup_exception_type": type(exc).__name__, "cleanup_error": str(exc)}
                if outcome is None:
                    outcome = SolRuntimeOutcome(SolRuntimeFailureKind.RUNTIME, cleanup)
                else:
                    evidence = dict(outcome.evidence)
                    evidence.update(cleanup)
                    outcome = SolRuntimeOutcome(outcome.kind, evidence)
    assert outcome is not None
    return outcome
