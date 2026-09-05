"""Declarative adapter for the R3 electron-density scaling counterfactual."""
from __future__ import annotations

from argparse import Namespace

from qpx_harness.application.execution_options import experiment_results_root, positive_timeout
from qpx_harness.application.experiment_spec import ExperimentControl


def run_protocol(spec: ExperimentControl) -> int:
    if spec.case_source is not None:
        raise ValueError("r3-electron-scaling-counterfactual owns its bounded N0/N1/N2 matrix")
    qpx = spec.execution.get("qpx")
    args = Namespace(
        qpx=qpx,
        results_root=experiment_results_root(spec, qpx),
        timeout=positive_timeout(spec, default=120.0),
    )
    from experiments.R3_electron_scaling_counterfactual.run import run
    return int(run(args))


__all__ = ["run_protocol"]
