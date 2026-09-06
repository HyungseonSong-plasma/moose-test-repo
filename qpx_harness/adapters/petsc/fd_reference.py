"""Reusable floating-point representability helpers for PETSc FD references.

This module owns explicit perturbation math only. It does not know any issue,
physics variable, accepted experiment state, or scientific decision policy.
"""
from __future__ import annotations

import math
import sys

SQRT_MACHINE_EPSILON = math.sqrt(sys.float_info.epsilon)


class FDReferenceError(ValueError):
    """Raised when an explicit finite-difference state is invalid."""


def representable_increment(*, component_value: float, requested_dx: float) -> dict[str, float]:
    """Return the floating-point increment actually representable at a component."""
    if not math.isfinite(component_value) or not math.isfinite(requested_dx):
        raise FDReferenceError("component and requested increment must be finite")
    if requested_dx == 0.0:
        raise FDReferenceError("requested increment must be nonzero")
    representable = (component_value + requested_dx) - component_value
    return {
        "requested_dx": requested_dx,
        "representable_dx": representable,
        "attenuation": representable / requested_dx,
    }


def wp_requested_step(*, vector_norm: float, epsilon: float = SQRT_MACHINE_EPSILON) -> float:
    """Return PETSc WP-style requested perturbation for an explicit vector norm."""
    if not math.isfinite(vector_norm) or vector_norm < 0.0:
        raise FDReferenceError("vector_norm must be finite and non-negative")
    if not math.isfinite(epsilon) or epsilon <= 0.0:
        raise FDReferenceError("epsilon must be finite and positive")
    return math.sqrt(1.0 + vector_norm) * epsilon


def ds_requested_step(*, component_value: float, epsilon: float = SQRT_MACHINE_EPSILON) -> float:
    """Return PETSc DS-style requested perturbation for a nonzero component."""
    if not math.isfinite(component_value) or component_value == 0.0:
        raise FDReferenceError("component_value must be finite and nonzero")
    if not math.isfinite(epsilon) or epsilon <= 0.0:
        raise FDReferenceError("epsilon must be finite and positive")
    return component_value * epsilon


def predict_wp_ds_representability(
    *,
    vector_norm: float,
    component_value: float,
    epsilon: float = SQRT_MACHINE_EPSILON,
) -> dict[str, float]:
    """Predict requested vs representable WP/DS increments for explicit state."""
    if not math.isfinite(component_value) or component_value == 0.0:
        raise FDReferenceError("component_value must be finite and nonzero")
    wp = representable_increment(
        component_value=component_value,
        requested_dx=wp_requested_step(vector_norm=vector_norm, epsilon=epsilon),
    )
    ds = representable_increment(
        component_value=component_value,
        requested_dx=ds_requested_step(component_value=component_value, epsilon=epsilon),
    )
    return {
        "sqrt_machine_epsilon": epsilon,
        "wp_requested_dx": wp["requested_dx"],
        "wp_representable_dx": wp["representable_dx"],
        "wp_predicted_attenuation": wp["attenuation"],
        "ds_requested_dx": ds["requested_dx"],
        "ds_representable_dx": ds["representable_dx"],
        "ds_predicted_attenuation": ds["attenuation"],
    }
