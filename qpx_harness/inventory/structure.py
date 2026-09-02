"""Canonical electron-inventory structural policy adapters.

Scientific nullspace and constrained-closure audits are recipe-owned. Canonical
MOOSE parameter helpers own parsing/mutation mechanics.
"""
from __future__ import annotations

from typing import Any

from recipes import issue45_inventory_constraint as constraint_policy
from recipes import issue45_inventory_nullspace as nullspace_policy

from ..moose import parameters as mp
from ..moose.input import MooseInputError
from .errors import ElectronInventoryNullspaceError


def _adapt_error(exc: Exception) -> ElectronInventoryNullspaceError:
    return ElectronInventoryNullspaceError(str(exc))


def _unquote(value: str | None) -> str | None:
    return mp.unquote(value)


def _words(value: str | None) -> list[str]:
    return mp.words(value)


def _parameter_value(text: str, path: str, name: str) -> str | None:
    try:
        return mp.get_parameter(text, path, name)
    except (mp.MooseParameterError, MooseInputError) as exc:
        raise _adapt_error(exc) from exc


def _parameter_count(text: str, path: str, name: str) -> int:
    try:
        return mp.parameter_count(text, path, name)
    except (mp.MooseParameterError, MooseInputError) as exc:
        raise _adapt_error(exc) from exc


def _set_or_insert_parameter(text: str, path: str, name: str, value: str) -> str:
    try:
        return mp.upsert_parameter(text, path, name, value)
    except (mp.MooseParameterError, MooseInputError) as exc:
        raise _adapt_error(exc) from exc


def _direct_children(text: str, parent: str) -> list[str]:
    try:
        return mp.direct_children(text, parent)
    except (mp.MooseParameterError, MooseInputError) as exc:
        raise _adapt_error(exc) from exc


def _truthy(value: str | None) -> bool:
    raw = (_unquote(value) or "").lower()
    return raw in {"1", "true", "yes", "on"}


def _ensure_debug_block(text: str) -> str:
    try:
        return constraint_policy._ensure_debug_block(text)
    except Exception as exc:
        raise _adapt_error(exc) from exc


def _electron_kernel_records(text: str) -> list[dict[str, Any]]:
    return constraint_policy._electron_kernel_records(text)


def _electron_fvbcs(text: str) -> list[dict[str, Any]]:
    return constraint_policy._electron_fvbcs(text)


def _poisson_fvbcs(text: str) -> list[dict[str, Any]]:
    return constraint_policy._poisson_fvbcs(text)


def _flux_boundary_audit(
    text: str, electron_kernels: list[dict[str, Any]], add: Any
) -> None:
    constraint_policy._flux_boundary_audit(text, electron_kernels, add)


def _audit_poisson_grounding(text: str, add: Any) -> None:
    constraint_policy._audit_poisson_grounding(text, add)


def audit_closed_electron_structure(text: str) -> dict[str, Any]:
    return nullspace_policy.audit_closed_electron_structure(text)


def _float_parameter(text: str, path: str, name: str) -> float | None:
    raw = _unquote(_parameter_value(text, path, name))
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def audit_constrained_quasisteady_structure(
    text: str, *, expected_macro_avg: float
) -> dict[str, Any]:
    result = constraint_policy.audit_constrained_quasisteady_structure(
        text,
        expected_macro_avg=expected_macro_avg,
    )
    if result.get("status") != "PASS" and result.get("class") == "CLOSURE_STRUCTURE_FAIL":
        result = {**result, "class": "CONSERVATION_STRUCTURE_FAIL"}
    return result
