"""Canonical unit-bearing quantities for the Physics→SOL realization boundary.

This module owns semantic quantity identity and unit validation only.  It does
not infer meaning from Physics action/local names and contains no MOOSE-native
spelling or adapter runtime semantics.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


class RealizationQuantityError(ValueError):
    """Raised when a realization-bound value lacks canonical quantity semantics."""


@dataclass(frozen=True, order=True)
class CanonicalQuantitySpec:
    """Canonical semantic identity and unit for one realization-bound quantity."""

    quantity_id: str
    unit: str

    def __post_init__(self) -> None:
        for name, value in (("quantity_id", self.quantity_id), ("unit", self.unit)):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if "moose" in self.quantity_id.casefold():
            raise ValueError("canonical quantity identity must be solver independent")


@dataclass(frozen=True)
class RealizationQuantity:
    """A value bound explicitly to canonical semantic quantity identity and unit."""

    spec: CanonicalQuantitySpec
    value: Any


class CanonicalQuantityCatalog:
    """Resolve quantity semantics exactly; local/action spelling is never a key."""

    def __init__(self, quantities: Mapping[str, CanonicalQuantitySpec]) -> None:
        resolved = dict(quantities)
        for quantity_id, spec in resolved.items():
            if quantity_id != spec.quantity_id:
                raise ValueError(
                    "catalog key must match CanonicalQuantitySpec.quantity_id"
                )
        self._quantities = resolved

    def bind(self, quantity_id: str, value: Any, *, unit: str | None) -> RealizationQuantity:
        try:
            spec = self._quantities[quantity_id]
        except KeyError as exc:
            raise RealizationQuantityError(
                f"canonical realization quantity is unavailable: {quantity_id!r}"
            ) from exc
        if unit is None or not isinstance(unit, str) or not unit.strip():
            raise RealizationQuantityError(
                f"explicit unit required for realization quantity {quantity_id!r}"
            )
        if unit != spec.unit:
            raise RealizationQuantityError(
                f"unit mismatch for {quantity_id!r}: expected {spec.unit!r}, got {unit!r}"
            )
        return RealizationQuantity(spec=spec, value=value)

    def bind_untyped(self, local_name: str, value: Any) -> RealizationQuantity:
        """Reject raw Physics scalars instead of inferring quantity/unit from spelling."""
        raise RealizationQuantityError(
            "realization-bound scalar requires explicit canonical quantity identity and unit; "
            f"cannot infer either from local/action spelling {local_name!r}"
        )


__all__ = [
    "CanonicalQuantityCatalog",
    "CanonicalQuantitySpec",
    "RealizationQuantity",
    "RealizationQuantityError",
]
