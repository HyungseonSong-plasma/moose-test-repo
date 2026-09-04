from pathlib import Path

from qpx_harness.provenance import (
    ArtifactRef,
    FileIdentity,
    RunEnvelope,
    read_run_envelope,
    write_run_envelope,
)


def test_run_envelope_is_reference_only_and_round_trips(tmp_path: Path):
    envelope = RunEnvelope(
        run_id="run-001",
        experiment_id="r4-qf2-local-charge-relaxation",
        protocol="r4-qf2-local-charge-relaxation",
        source_revision="abc123",
        executable=FileIdentity(path="/opt/qpx-opt", sha256="exe-sha"),
        input=FileIdentity(path="case/input.i", sha256="input-sha"),
        artifacts=(
            ArtifactRef(kind="execution", path="logs/runtime.log"),
            ArtifactRef(kind="evidence", path="case/input_out.physical.csv"),
            ArtifactRef(kind="protocol", path="summary.json", schema_version=1),
        ),
    )

    path = write_run_envelope(tmp_path / "run_envelope.json", envelope)
    loaded = read_run_envelope(path)

    assert loaded == envelope
    payload = loaded.to_dict()
    assert payload["schema_version"] == 1
    assert payload["run_id"] == "run-001"
    assert payload["artifacts"][0]["kind"] == "execution"
    assert "payload" not in payload
    assert "summary" not in payload


def test_run_envelope_rejects_unknown_schema_version(tmp_path: Path):
    path = tmp_path / "run_envelope.json"
    path.write_text('{"schema_version": 2}\n')

    try:
        read_run_envelope(path)
    except ValueError as exc:
        assert "schema_version" in str(exc)
    else:
        raise AssertionError("unknown RunEnvelope schema must be rejected")
