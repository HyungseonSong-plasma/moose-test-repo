"""Reusable Polars + DuckDB numerical evidence engine for QPX diagnostics."""

from .diagnose import (
    DiagnosticMetricSpec,
    DiagnosisReport,
    DiagnosisRule,
    DiagnosisRuleRegistry,
    EvidenceTolerances,
    FailureLocation,
    build_constant_state_registry,
    evaluate_diagnosis_registry,
    summarize_constant_state,
    summarize_constant_state_report,
)
from .schema import (
    CELL_KEY_COLUMNS,
    CORE_FACE_CONTRACT,
    DEFAULT_FACE_CONTRACT,
    FACE_REQUIRED_COLUMNS,
    GREEN_GAUSS_FACE_CONTRACT,
    ColumnRole,
    ColumnSpec,
    CoreColumnRole,
    DynamicSchemaContract,
    SchemaResolution,
    normalize_and_project,
    require_columns,
)
from .store import EvidenceStore
from .transform import build_cell_evidence, prepare_face_evidence, write_evidence_bundle

__all__ = [
    "CELL_KEY_COLUMNS",
    "CORE_FACE_CONTRACT",
    "DEFAULT_FACE_CONTRACT",
    "FACE_REQUIRED_COLUMNS",
    "GREEN_GAUSS_FACE_CONTRACT",
    "ColumnRole",
    "ColumnSpec",
    "CoreColumnRole",
    "DiagnosticMetricSpec",
    "DiagnosisReport",
    "DiagnosisRule",
    "DiagnosisRuleRegistry",
    "DynamicSchemaContract",
    "EvidenceStore",
    "EvidenceTolerances",
    "FailureLocation",
    "SchemaResolution",
    "build_cell_evidence",
    "build_constant_state_registry",
    "evaluate_diagnosis_registry",
    "normalize_and_project",
    "prepare_face_evidence",
    "require_columns",
    "summarize_constant_state",
    "summarize_constant_state_report",
    "write_evidence_bundle",
]
