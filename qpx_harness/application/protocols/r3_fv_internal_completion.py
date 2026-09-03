"""Declarative adapter for the existing R3 FV internal completion protocol."""
from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from qpx_harness.application.experiment_spec import ExperimentSpec


def _optional_path(spec: ExperimentSpec, value: object) -> Path | None:
    if value in (None, ""):
        return None
    if not isinstance(value, (str, Path)):
        raise ValueError(f"expected path-like value, got {type(value).__name__}")
    return spec.resolve_path(value)


def run_protocol(spec: ExperimentSpec) -> int:
    if spec.case_source is not None:
        raise ValueError("r3-fv-internal-completion owns its canonical case matrix")
    execution = spec.execution
    parameters = spec.parameters
    args = Namespace(
        qpx=execution.get("qpx"),
        results_root=_optional_path(spec, execution.get("results_root")),
        error_ledger=_optional_path(spec, execution.get("error_ledger")),
        timeout=float(execution.get("timeout_seconds", 120.0)),
        jacobian_timeout=float(execution.get("jacobian_timeout_seconds", 300.0)),
        jacobian_tolerance=float(parameters.get("jacobian_tolerance", 1.0e-8)),
    )
    if args.timeout <= 0 or args.jacobian_timeout <= 0:
        raise ValueError("timeouts must be positive")
    from experiments.R3_fv_internal_completion.run import run
    return int(run(args))


__all__ = ["run_protocol"]
