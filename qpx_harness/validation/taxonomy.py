"""Machine-readable classification for repository validation surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ValidationKind(str, Enum):
    """Semantic purpose of a validation entry point or fixture."""

    UNIT_TEST = "UNIT_TEST"
    CHARACTERIZATION = "CHARACTERIZATION"
    SCIENTIFIC_ACCEPTANCE = "SCIENTIFIC_ACCEPTANCE"
    REGRESSION_CONTRACT = "REGRESSION_CONTRACT"
    EXPERIMENT_PREPARATION = "EXPERIMENT_PREPARATION"
    SMOKE_TEST = "SMOKE_TEST"
    COMPATIBILITY_TEST = "COMPATIBILITY_TEST"
    HISTORICAL = "HISTORICAL"


@dataclass(frozen=True)
class ValidationSurface:
    """Describe one validation surface without executing or interpreting it."""

    kind: ValidationKind
    requires_solver: bool = False
    writes_artifacts: bool = False
    mutates_workspace: bool = False
    depends_on_scientific_thresholds: bool = False
    ci_suitable: bool = True
    canonical_location: str | None = None

    @property
    def is_scientific_protocol(self) -> bool:
        return self.kind is ValidationKind.SCIENTIFIC_ACCEPTANCE

    @property
    def is_infrastructure_validation(self) -> bool:
        return self.kind in {
            ValidationKind.UNIT_TEST,
            ValidationKind.REGRESSION_CONTRACT,
            ValidationKind.SMOKE_TEST,
            ValidationKind.COMPATIBILITY_TEST,
        }


__all__ = ["ValidationKind", "ValidationSurface"]
