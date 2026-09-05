"""Application service for the canonical declarative experiment gateway."""
from __future__ import annotations

from pathlib import Path

from .experiment_registry import protocol_registered, resolve_protocol
from .experiment_spec import ExperimentControl, load_experiment_spec


def validate_experiment_spec(spec: ExperimentControl) -> None:
    if not protocol_registered(spec.protocol):
        raise ValueError(f"experiment {spec.experiment_id!r} uses unregistered protocol {spec.protocol!r}")
    if spec.case_source is not None and not spec.case_source.path.is_file():
        raise FileNotFoundError(f"experiment case source does not exist: {spec.case_source.path}")


def run_experiment(spec_or_path: ExperimentControl | str | Path) -> int:
    spec = spec_or_path if isinstance(spec_or_path, ExperimentControl) else load_experiment_spec(spec_or_path)
    validate_experiment_spec(spec)
    runner = resolve_protocol(spec.protocol)
    return int(runner(spec))


__all__ = ["run_experiment", "validate_experiment_spec"]
