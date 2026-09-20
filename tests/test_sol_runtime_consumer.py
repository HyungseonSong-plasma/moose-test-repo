from pathlib import Path

from physics_harness.ontology.sol_request import SolRequest
from physics_harness.ontology.sol_runtime_consumer import (
    ADAPTER_PROTOCOL_VERSION,
    SOL_ADAPTER_MOOSE_REVISION,
    SOL_RUNTIME_REVISION,
    SolRuntimeFailureKind,
    build_runtime_envelope,
    invoke_runtime_consumer,
)


def _request() -> SolRequest:
    return SolRequest(
        backend_target={"target": "moose", "required_capabilities": ["thermal.steady_conduction"]},
        mapping_plan={"public_contract_version": "0.2", "actions": [{"id": "solve", "dependencies": []}]},
        realization_spec={"public_contract_version": "0.2", "ontology_version": "test", "entities": []},
    )


def test_runtime_envelope_is_mechanical_mapping_of_sol_request():
    request = _request()
    envelope = build_runtime_envelope(request)
    assert envelope["target"] == "moose"
    assert envelope["required_capabilities"] == ["thermal.steady_conduction"]
    assert envelope["plan_request"] == {
        "adapter_protocol_version": ADAPTER_PROTOCOL_VERSION,
        "plan": request.mapping_plan,
        "realization_spec": request.realization_spec,
    }


def test_upstream_revisions_are_exact_pins():
    assert SOL_RUNTIME_REVISION == "020e9a979a0b97f2af3cf54758cedf38fecb187a"
    assert SOL_ADAPTER_MOOSE_REVISION == "f35563f0e63e2739cb94a36c450d5d66024aff2a"


def _write_consumer(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "consumer"
    path.write_text("#!/usr/bin/env python3\n" + body)
    path.chmod(0o755)
    return path


def test_success_requires_explicit_no_replay_evidence(tmp_path):
    consumer = _write_consumer(
        tmp_path,
        "import json\nprint(json.dumps({'status':'completed','execute_response_loss_replay':'forbidden'}))\n",
    )
    result = invoke_runtime_consumer(consumer, Path("adapter"), _request())
    assert result.completed


def test_nonzero_runtime_validation_failure_is_typed(tmp_path):
    consumer = _write_consumer(
        tmp_path,
        "import sys\nsys.stderr.write('VALIDATION_REJECTED:Rejected')\nsys.exit(1)\n",
    )
    result = invoke_runtime_consumer(consumer, Path("adapter"), _request())
    assert result.kind is SolRuntimeFailureKind.VALIDATION


def test_malformed_success_is_protocol_failure(tmp_path):
    consumer = _write_consumer(tmp_path, "print('not-json')\n")
    result = invoke_runtime_consumer(consumer, Path("adapter"), _request())
    assert result.kind is SolRuntimeFailureKind.PROTOCOL


def test_success_without_no_replay_proof_is_ambiguous(tmp_path):
    consumer = _write_consumer(tmp_path, "print('{\"status\":\"completed\"}')\n")
    result = invoke_runtime_consumer(consumer, Path("adapter"), _request())
    assert result.kind is SolRuntimeFailureKind.NO_REPLAY_AMBIGUITY
