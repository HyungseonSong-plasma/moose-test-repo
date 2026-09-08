"""Solver-independent species accounting and linear-constraint semantics.

This module intentionally owns no electron-specific defaults, Issue fixtures,
solver spellings, or acceptance thresholds.  Experiments provide species IDs,
coefficients, targets, and tolerances explicitly.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class SpeciesLinearConstraint:
    """One linear constraint over named species quantities."""

    coefficients: Mapping[str, float]
    target: float
    absolute_tolerance: float

    def __post_init__(self) -> None:
        if not self.coefficients:
            raise ValueError("species constraint requires at least one coefficient")
        normalized: dict[str, float] = {}
        for species, coefficient in self.coefficients.items():
            if not species:
                raise ValueError("species identifiers must be non-empty")
            value = float(coefficient)
            if not isfinite(value):
                raise ValueError(f"non-finite coefficient for {species!r}")
            normalized[str(species)] = value
        target = float(self.target)
        tolerance = float(self.absolute_tolerance)
        if not isfinite(target):
            raise ValueError("constraint target must be finite")
        if not isfinite(tolerance) or tolerance < 0.0:
            raise ValueError("absolute_tolerance must be finite and non-negative")
        object.__setattr__(self, "coefficients", MappingProxyType(normalized))
        object.__setattr__(self, "target", target)
        object.__setattr__(self, "absolute_tolerance", tolerance)


@dataclass(frozen=True)
class SpeciesConstraintEvaluation:
    value: float
    target: float
    error: float
    absolute_tolerance: float
    satisfied: bool


def evaluate_species_constraint(
    quantities: Mapping[str, float], constraint: SpeciesLinearConstraint
) -> SpeciesConstraintEvaluation:
    """Evaluate a declared linear species constraint without assigning physics policy."""
    missing = sorted(set(constraint.coefficients) - set(quantities))
    if missing:
        raise ValueError("missing species quantities: " + ", ".join(missing))
    value = 0.0
    for species, coefficient in constraint.coefficients.items():
        quantity = float(quantities[species])
        if not isfinite(quantity):
            raise ValueError(f"non-finite quantity for {species!r}")
        value += coefficient * quantity
    error = value - constraint.target
    return SpeciesConstraintEvaluation(
        value=value,
        target=constraint.target,
        error=error,
        absolute_tolerance=constraint.absolute_tolerance,
        satisfied=abs(error) <= constraint.absolute_tolerance,
    )


def species_total(quantities: Mapping[str, float], species: tuple[str, ...] | list[str]) -> float:
    """Return an explicitly selected species total."""
    if not species:
        raise ValueError("species selection must not be empty")
    missing = [name for name in species if name not in quantities]
    if missing:
        raise ValueError("missing species quantities: " + ", ".join(missing))
    values = [float(quantities[name]) for name in species]
    if not all(isfinite(value) for value in values):
        raise ValueError("species total received non-finite quantity")
    return sum(values)


__all__ = [
    "SpeciesLinearConstraint",
    "SpeciesConstraintEvaluation",
    "evaluate_species_constraint",
    "species_total",
]
