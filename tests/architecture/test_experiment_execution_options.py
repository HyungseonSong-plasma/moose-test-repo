from pathlib import Path

import pytest

from qpx_harness.application.execution_options import optional_path, positive_timeout
from qpx_harness.application.experiment_spec import ExperimentControl
from qpx_harness.execution.runtime import resolve_results_root


def _spec(tmp_path: Path, *, execution: dict[str, object]) -> ExperimentControl:
    source = tmp_path / "experiment.json"
    source.write_text("{}\n")
    return ExperimentControl(
        schema_version=1,
        experiment_id="test",
        protocol="test-protocol",
        source_path=source,
        execution=execution,
    )


def test_optional_path_is_resolved_relative_to_experiment(tmp_path: Path):
    spec = _spec(tmp_path, execution={"results_root": "results"})
    assert optional_path(spec, "results_root") == (tmp_path / "results").resolve()


def test_positive_timeout_rejects_non_positive_values(tmp_path: Path):
    spec = _spec(tmp_path, execution={"timeout_seconds": 0})
    with pytest.raises(ValueError, match="timeout_seconds"):
        positive_timeout(spec, default=120.0)


def test_execution_results_root_preserves_configured_root(tmp_path: Path):
    configured = tmp_path / "custom-results"
    assert resolve_results_root(None, configured) == configured.resolve()
