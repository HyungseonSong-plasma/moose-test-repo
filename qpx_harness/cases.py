"""Compatibility facade for generic execution case staging."""

from .execution.cases import (
    CaseError,
    purge_generated_artifacts,
    referenced_file_parameters,
    stage_case,
    validate_case_references,
    validate_referenced_files,
)

__all__ = [
    "CaseError",
    "purge_generated_artifacts",
    "referenced_file_parameters",
    "stage_case",
    "validate_case_references",
    "validate_referenced_files",
]
