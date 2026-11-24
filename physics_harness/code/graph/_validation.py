"""Shared validation for immutable, JSON-compatible code graph records."""

from __future__ import annotations

import math
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any


def nonempty(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty string")
    return value


def optional_nonempty(value: str | None, field: str) -> str | None:
    if value is not None:
        nonempty(value, field)
    return value


def string_tuple(values: tuple[str, ...], field: str, *, unique: bool = True) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise TypeError(f"{field} must be a tuple")
    for value in values:
        nonempty(value, field)
    if unique and len(set(values)) != len(values):
        raise ValueError(f"{field} contains duplicate values")
    return values


def instance_tuple(values: tuple[Any, ...], item_type: type, field: str) -> None:
    if not isinstance(values, tuple) or not all(isinstance(item, item_type) for item in values):
        raise TypeError(f"{field} must be a tuple of {item_type.__name__}")


def frozen_json(value: Any) -> Any:
    """Freeze JSON-shaped attributes recursively; reject mutable/opaque objects."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite floats are not valid JSON attributes")
        return value
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("attribute mapping keys must be strings")
        return MappingProxyType({key: frozen_json(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(frozen_json(item) for item in value)
    raise TypeError(f"attribute value is not JSON-compatible: {type(value).__name__}")


def frozen_mapping(value: Mapping[str, Any], field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field} must be a mapping")
    return frozen_json(value)
