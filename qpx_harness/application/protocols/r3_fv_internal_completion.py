"""Declarative adapter for the existing R3 FV internal completion protocol."""
from __future__ import annotations

from argparse import Namespace

from qpx_harness.application.execution_options import optional_path, positive_timeout
from qpx_harness.application.experiment_spec import ExperimentControl


def run_protocol(spec: ExperimentControl) -> int:
    if spec.case_source is not None:
        raise ValueError("r3-fv-internal-completion owns its canonical case matrix")
    parameters = spec.parameters
    args = Namespace(
        qpx=spec.execution.get("qpx"),
        results_root=optional_path(spec, "results_root"),
        error_ledger=optional_path(spec, "error_ledger"),
        timeout=positive_timeout(spec, default=120.0),
        jacobian_timeout=positive_timeout(spec, default=300.0, key="jacobian_timeout_seconds"),
        jacobian_tolerance=float(parameters.get("jacobian_tolerance", 1.0e-8)),
    )
    from experiments.R3_fv_internal_completion.run import run
    return int(run(args))


__all__ = ["run_protocol"]
