"""Reusable Polars + DuckDB numerical evidence engine for QPX diagnostics."""

from .diagnose import EvidenceTolerances, summarize_constant_state
from .schema import CELL_KEY_COLUMNS, FACE_REQUIRED_COLUMNS, require_columns
from .store import EvidenceStore
from .transform import build_cell_evidence, prepare_face_evidence, write_evidence_bundle

__all__ = [
    "CELL_KEY_COLUMNS",
    "FACE_REQUIRED_COLUMNS",
    "EvidenceStore",
    "EvidenceTolerances",
    "build_cell_evidence",
    "prepare_face_evidence",
    "require_columns",
    "summarize_constant_state",
    "write_evidence_bundle",
]
