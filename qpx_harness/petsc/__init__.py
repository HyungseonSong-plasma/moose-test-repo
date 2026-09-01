"""Reusable PETSc option and diagnostic operations."""

from .options import (
    PetscOptionsError,
    add_flags,
    get_flags,
    get_name_value_pairs,
    remove_flags,
    remove_name_value,
    set_flags,
    set_name_value_pairs,
    upsert_name_value,
)

__all__ = [
    "PetscOptionsError",
    "add_flags",
    "get_flags",
    "get_name_value_pairs",
    "remove_flags",
    "remove_name_value",
    "set_flags",
    "set_name_value_pairs",
    "upsert_name_value",
]
