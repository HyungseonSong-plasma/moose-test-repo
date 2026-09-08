"""Canonical validation taxonomy and reusable validation metadata."""

from .cli_contract import (
    EXPECTED_INTERNAL_TARGETS,
    EXPECTED_LEGACY_COMMANDS,
    validate_command_surface,
)
from .taxonomy import ValidationKind, ValidationSurface

__all__ = [
    "EXPECTED_INTERNAL_TARGETS",
    "EXPECTED_LEGACY_COMMANDS",
    "ValidationKind",
    "ValidationSurface",
    "validate_command_surface",
]
