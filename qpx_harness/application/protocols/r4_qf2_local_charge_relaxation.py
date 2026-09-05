"""Declarative adapter for the accepted R4-QF2 local-charge relaxation protocol."""
from __future__ import annotations

from argparse import Namespace

from qpx_harness.application.execution_options import experiment_results_root, positive_timeout
from qpx_harness.application.experiment_spec import ExperimentControl


def run_protocol(spec: ExperimentControl) -> int:
    if spec.case_source is not None:
        raise ValueError("r4-qf2-local-charge-relaxation owns its canonical QF2 case")
    qpx = spec.execution.get("qpx")
    args = Namespace(
        qpx=qpx,
        results_root=experiment_results_root(spec, qpx),
        timeout=positive_timeout(spec, default=180.0),
    )
    from experiments.Issue31_r4_qf2_local_charge_relaxation.run import run
    return int(run(args))


__all__ = ["run_protocol"]
