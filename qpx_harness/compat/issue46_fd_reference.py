"""Temporary stable-CLI adapter for the Issue46 FD-reference recipe migration.

The historical runtime shell remains the compatibility owner while Issue48
moves scientific construction/analysis/evidence composition into the thin
recipe. This adapter installs recipe-backed callables before delegating to the
accepted CLI/runtime shell, including translation back to the historical
exception type expected by legacy negative controls and CLI error handling.
Remove this module once the remaining Issue45/46 runtime orchestration is
recipe-owned.
"""
from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from recipes import issue46_fd_reference as recipe
from qpx_harness import jacobian_fd_reference_audit as legacy


def _legacy_error_adapter(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Preserve the legacy Issue46 exception contract around a recipe callable."""
    @wraps(fn)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except recipe.Issue46FDReferenceError as exc:
            raise legacy.JacobianFDReferenceAuditError(str(exc)) from exc

    setattr(wrapped, "__qpx_recipe_target__", fn)
    return wrapped


_predict_fd_step_quantization = _legacy_error_adapter(recipe.predict_fd_step_quantization)
_directional_localization = _legacy_error_adapter(recipe.directional_localization)
_instrument_ds_reference = _legacy_error_adapter(recipe.instrument_ds_reference)
_remove_fd_type_pair = _legacy_error_adapter(recipe.remove_fd_type_pair)
_mask_petsc_pair_lines = _legacy_error_adapter(recipe.mask_petsc_pair_lines)


def _install_recipe_backing() -> None:
    """Bind migrated Issue46 operations to recipe implementations or adapters."""
    legacy.predict_fd_step_quantization = _predict_fd_step_quantization
    legacy._historical_evr1_prediction = recipe.historical_evr1_prediction
    legacy._historical_mechanism_evidence = recipe.historical_mechanism_evidence
    legacy._termination_admissibility = recipe.termination_admissibility
    legacy._runtime_mechanism_applicability = recipe.runtime_mechanism_applicability
    legacy._evidence_provenance_status = recipe.evidence_provenance_status
    legacy.directional_localization = _directional_localization
    legacy.instrument_ds_reference = _instrument_ds_reference
    legacy._remove_fd_type_pair = _remove_fd_type_pair
    legacy._mask_petsc_pair_lines = _mask_petsc_pair_lines
    legacy.analyze_ds_runtime = recipe.analyze_ds_runtime


def _is_recipe_adapter(bound: Callable[..., Any], target: Callable[..., Any]) -> bool:
    return getattr(bound, "__qpx_recipe_target__", None) is target


def recipe_backing_status() -> dict[str, bool]:
    """Return identity/backing checks for every migrated compatibility binding."""
    _install_recipe_backing()
    return {
        "predict_fd_step_quantization": _is_recipe_adapter(
            legacy.predict_fd_step_quantization, recipe.predict_fd_step_quantization
        ),
        "historical_evr1_prediction": legacy._historical_evr1_prediction
        is recipe.historical_evr1_prediction,
        "historical_mechanism_evidence": legacy._historical_mechanism_evidence
        is recipe.historical_mechanism_evidence,
        "termination_admissibility": legacy._termination_admissibility
        is recipe.termination_admissibility,
        "runtime_mechanism_applicability": legacy._runtime_mechanism_applicability
        is recipe.runtime_mechanism_applicability,
        "evidence_provenance_status": legacy._evidence_provenance_status
        is recipe.evidence_provenance_status,
        "directional_localization": _is_recipe_adapter(
            legacy.directional_localization, recipe.directional_localization
        ),
        "instrument_ds_reference": _is_recipe_adapter(
            legacy.instrument_ds_reference, recipe.instrument_ds_reference
        ),
        "remove_fd_type_pair": _is_recipe_adapter(
            legacy._remove_fd_type_pair, recipe.remove_fd_type_pair
        ),
        "mask_petsc_pair_lines": _is_recipe_adapter(
            legacy._mask_petsc_pair_lines, recipe.mask_petsc_pair_lines
        ),
        "analyze_ds_runtime": legacy.analyze_ds_runtime is recipe.analyze_ds_runtime,
    }


def self_test() -> int:
    _install_recipe_backing()
    return legacy.self_test()


def main(argv: list[str] | None = None) -> int:
    _install_recipe_backing()
    return legacy.main(argv)
