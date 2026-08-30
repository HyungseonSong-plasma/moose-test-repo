"""Issue46 FD-reference audit entry with an exact C0 synthetic fixture.

The base audit intentionally reuses Issue45 structural helpers. Issue45's
synthetic constrained input omits an electron initial condition because that
fixture only tests closure structure. The Issue46 FD-reference audit additionally
owns the C0 runtime-state invariant n_e=1e16. This adapter injects only that
missing synthetic-fixture datum while leaving production case construction and
all runtime logic in jacobian_fd_reference_audit unchanged.
"""
from __future__ import annotations

from . import jacobian_fd_reference_audit as base


_ORIGINAL_SYNTHETIC_CONSTRAINED_INPUT = base.inv._synthetic_constrained_input
_ORIGINAL_BASE_SELF_TEST = base.self_test


def _issue46_synthetic_constrained_input(macro_avg: float = base.TARGET) -> str:
    text = _ORIGINAL_SYNTHETIC_CONSTRAINED_INPUT(macro_avg)
    return base.inv._set_or_insert_parameter(
        text,
        "Variables/n_e",
        "initial_condition",
        f"{base.TARGET:.17g}",
    )


def self_test() -> int:
    """Run the base self-test with the Issue46-specific C0 fixture only."""
    original_fixture = base.inv._synthetic_constrained_input
    base.inv._synthetic_constrained_input = _issue46_synthetic_constrained_input
    try:
        return _ORIGINAL_BASE_SELF_TEST()
    finally:
        base.inv._synthetic_constrained_input = original_fixture


def main(argv: list[str] | None = None) -> int:
    """Delegate the canonical CLI while substituting only the repaired self-test."""
    original_self_test = base.self_test
    base.self_test = self_test
    try:
        return base.main(argv)
    finally:
        base.self_test = original_self_test


# Re-export analysis/runtime helpers for direct tests without duplicating ownership.
predict_fd_step_quantization = base.predict_fd_step_quantization
nonzero_threshold_difference = base.nonzero_threshold_difference
directional_localization = base.directional_localization
instrument_ds_reference = base.instrument_ds_reference
audit_ds_reference_structure = base.audit_ds_reference_structure
analyze_ds_runtime = base.analyze_ds_runtime
run_preflight = base.run_preflight
run_runtime = base.run_runtime

__all__ = [
    "main",
    "self_test",
    "predict_fd_step_quantization",
    "nonzero_threshold_difference",
    "directional_localization",
    "instrument_ds_reference",
    "audit_ds_reference_structure",
    "analyze_ds_runtime",
    "run_preflight",
    "run_runtime",
]
