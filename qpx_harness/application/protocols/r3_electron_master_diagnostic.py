"""Declarative adapter for the R3 electron master diagnostic campaign."""
from __future__ import annotations

from argparse import Namespace

from qpx_harness.application.execution_options import optional_path, positive_timeout
from qpx_harness.application.experiment_spec import ExperimentSpec


def run_protocol(spec: ExperimentSpec) -> int:
    if spec.case_source is not None:
        raise ValueError("r3-electron-master-diagnostic owns its predeclared diagnostic matrix")
    parameters = spec.parameters
    args = Namespace(
        qpx=spec.execution.get("qpx"),
        results_root=optional_path(spec, "results_root"),
        error_ledger=optional_path(spec, "error_ledger"),
        timeout=positive_timeout(spec, default=120.0),
        jacobian_timeout=positive_timeout(spec, default=300.0, key="jacobian_timeout_seconds"),
        jacobian_tolerance=float(parameters.get("jacobian_tolerance", 1.0e-8)),
    )
    from experiments.R3_electron_master_diagnostic.run import run
    return int(run(args))


__all__ = ["run_protocol"]
