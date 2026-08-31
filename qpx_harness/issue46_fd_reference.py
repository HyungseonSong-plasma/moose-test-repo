"""Semantic runtime owner for the Issue46 FD-reference audit.

Scientific FD-reference policy is owned by ``recipes.issue46_fd_reference``.
The historical ``jacobian_fd_reference_audit`` runtime shell remains a bounded
migration dependency while Issue48 converges orchestration into this owner.
This module preserves the accepted CLI/runtime behavior by installing
recipe-backed operations before delegating to that shell.
"""
from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from recipes import issue46_fd_reference as recipe
from qpx_harness import jacobian_fd_reference_audit as runtime_shell


def _runtime_error_adapter(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Preserve the current runtime-shell exception contract around recipe calls."""
    @wraps(fn)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except recipe.Issue46FDReferenceError as exc:
            raise runtime_shell.JacobianFDReferenceAuditError(str(exc)) from exc

    setattr(wrapped, "__qpx_recipe_target__", fn)
    return wrapped


_predict_fd_step_quantization = _runtime_error_adapter(recipe.predict_fd_step_quantization)
_directional_localization = _runtime_error_adapter(recipe.directional_localization)
_instrument_ds_reference = _runtime_error_adapter(recipe.instrument_ds_reference)
_remove_fd_type_pair = _runtime_error_adapter(recipe.remove_fd_type_pair)
_mask_petsc_pair_lines = _runtime_error_adapter(recipe.mask_petsc_pair_lines)


def _install_recipe_backing() -> None:
    """Bind migrated Issue46 operations to recipe implementations or adapters."""
    runtime_shell.predict_fd_step_quantization = _predict_fd_step_quantization
    runtime_shell._historical_evr1_prediction = recipe.historical_evr1_prediction
    runtime_shell._historical_mechanism_evidence = recipe.historical_mechanism_evidence
    runtime_shell._termination_admissibility = recipe.termination_admissibility
    runtime_shell._runtime_mechanism_applicability = recipe.runtime_mechanism_applicability
    runtime_shell._evidence_provenance_status = recipe.evidence_provenance_status
    runtime_shell.directional_localization = _directional_localization
    runtime_shell.instrument_ds_reference = _instrument_ds_reference
    runtime_shell._remove_fd_type_pair = _remove_fd_type_pair
    runtime_shell._mask_petsc_pair_lines = _mask_petsc_pair_lines
    runtime_shell.analyze_ds_runtime = recipe.analyze_ds_runtime


def _is_recipe_adapter(bound: Callable[..., Any], target: Callable[..., Any]) -> bool:
    return getattr(bound, "__qpx_recipe_target__", None) is target


def recipe_backing_status() -> dict[str, bool]:
    """Return identity/backing checks for every migrated semantic binding."""
    _install_recipe_backing()
    return {
        "predict_fd_step_quantization": _is_recipe_adapter(
            runtime_shell.predict_fd_step_quantization,
            recipe.predict_fd_step_quantization,
        ),
        "historical_evr1_prediction": runtime_shell._historical_evr1_prediction
        is recipe.historical_evr1_prediction,
        "historical_mechanism_evidence": runtime_shell._historical_mechanism_evidence
        is recipe.historical_mechanism_evidence,
        "termination_admissibility": runtime_shell._termination_admissibility
        is recipe.termination_admissibility,
        "runtime_mechanism_applicability": runtime_shell._runtime_mechanism_applicability
        is recipe.runtime_mechanism_applicability,
        "evidence_provenance_status": runtime_shell._evidence_provenance_status
        is recipe.evidence_provenance_status,
        "directional_localization": _is_recipe_adapter(
            runtime_shell.directional_localization,
            recipe.directional_localization,
        ),
        "instrument_ds_reference": _is_recipe_adapter(
            runtime_shell.instrument_ds_reference,
            recipe.instrument_ds_reference,
        ),
        "remove_fd_type_pair": _is_recipe_adapter(
            runtime_shell._remove_fd_type_pair,
            recipe.remove_fd_type_pair,
        ),
        "mask_petsc_pair_lines": _is_recipe_adapter(
            runtime_shell._mask_petsc_pair_lines,
            recipe.mask_petsc_pair_lines,
        ),
        "analyze_ds_runtime": runtime_shell.analyze_ds_runtime
        is recipe.analyze_ds_runtime,
    }


def self_test() -> int:
    _install_recipe_backing()
    return runtime_shell.self_test()


def main(argv: list[str] | None = None) -> int:
    _install_recipe_backing()
    return runtime_shell.main(argv)
