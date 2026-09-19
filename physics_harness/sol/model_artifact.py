"""Canonical SOL model artifact identity used at the Physics→SOL boundary.

This module owns identity/provenance construction only.  It deliberately does
not own adapter runtime, transport, registry, or backend realization semantics.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


class ModelArtifactResolutionError(ValueError):
    """Raised when a canonical model artifact cannot be resolved exactly."""


@dataclass(frozen=True, order=True)
class CanonicalModelArtifactRef:
    """Immutable identity for exactly one canonical SOL model artifact."""

    model_id: str
    artifact_id: str
    schema_version: str
    public_contract: str
    source: str
    revision: str
    digest: str

    def __post_init__(self) -> None:
        for name, value in self.to_dict().items():
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")

    def to_dict(self) -> dict[str, str]:
        """Return a deterministic serialization shape."""
        return {
            "model_id": self.model_id,
            "artifact_id": self.artifact_id,
            "schema_version": self.schema_version,
            "public_contract": self.public_contract,
            "source": self.source,
            "revision": self.revision,
            "digest": self.digest,
        }


class ModelArtifactCatalog:
    """Resolve immutable canonical references without guessing from local names."""

    def __init__(self, artifacts: Mapping[str, CanonicalModelArtifactRef]) -> None:
        self._artifacts = dict(artifacts)

    def resolve(self, artifact_id: str) -> CanonicalModelArtifactRef:
        try:
            return self._artifacts[artifact_id]
        except KeyError as exc:
            raise ModelArtifactResolutionError(
                f"canonical SOL model artifact is unavailable: {artifact_id!r}"
            ) from exc

    def resolve_execution_model_ref(self, model_ref: str | None) -> CanonicalModelArtifactRef:
        """Reject legacy/local model_ref strings rather than promoting by spelling."""
        raise ModelArtifactResolutionError(
            "ExecutionPlan.model_ref is an opaque Physics reference and cannot be "
            "promoted to canonical SOL model identity by string reuse"
        )


__all__ = [
    "CanonicalModelArtifactRef",
    "ModelArtifactCatalog",
    "ModelArtifactResolutionError",
]
