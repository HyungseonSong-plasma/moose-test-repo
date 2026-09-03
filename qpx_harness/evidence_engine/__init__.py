"""Reusable Polars + DuckDB numerical evidence engine for QPX diagnostics."""

from .diagnose import (
    DiagnosisReport,
    EvidenceTolerances,
    FailureLocation,
    summarize_constant_state,
    summarize_constant_state_report,
)
from .schema import (
    CELL_KEY_COLUMNS,
    DEFAULT_FACE_CONTRACT,
    FACE_REQUIRED_COLUMNS,
    ColumnRole,
    ColumnSpec,
    DynamicSchemaContract,
    SchemaResolution,
    normalize_and_project,
    require_columns,
)
from .store import EvidenceStore
from .transform import build_cell_evidence, prepare_face_evidence, write_evidence_bundle

__all__ = [
    "CELL_KEY_COLUMNS",
    "DEFAULT_FACE_CONTRACT",
    "FACE_REQUIRED_COLUMNS",
    "ColumnRole",
    "ColumnSpec",
    "DiagnosisReport",
    "DynamicSchemaContract",
    "EvidenceStore",
    "EvidenceTolerances",
    "FailureLocation",
    "SchemaResolution",
    "build_cell_evidence",
    "normalize_and_project",
    "prepare_face_evidence",
    "require_columns",
    "summarize_constant_state",
    "summarize_constant_state_report",
    "write_evidence_bundle",
]
