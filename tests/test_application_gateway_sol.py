from __future__ import annotations

from pathlib import Path

from physics_harness.application import gateway
from physics_harness.ontology.sol_request import SolRequest
from physics_harness.ontology.sol_runtime_consumer import SolRuntimeOutcome


def test_prepare_sol_experiment_uses_only_explicit_canonical_inputs(monkeypatch):
    planned = object()
    model = object()
    seen: dict[str, object] = {}
    expected = SolRequest(
        backend_target={"target": "moose"},
        mapping_plan={"public_contract_version": "0.2", "actions": []},
        realization_spec={"public_contract_version": "0.2", "entities": []},
    )

    monkeypatch.setattr(gateway, "plan_experiment", lambda *args, **kwargs: planned)

    class FakeCompiler:
        def __init__(self, capability_map, *, backend_target):
            seen["capability_map"] = capability_map
            seen["backend_target"] = backend_target

        def compile(self, realization_model, *, physics_capabilities):
            seen["model"] = realization_model
            seen["physics_capabilities"] = physics_capabilities
            return expected

    monkeypatch.setattr(gateway, "SolRequestCompiler", FakeCompiler)
    prepared = gateway.prepare_sol_experiment(
        "ignored.json",
        realization_model=model,
        physics_capabilities=("plasma.transport",),
        capability_map={"plasma.transport": "plasma.transport"},
        backend_target="moose",
    )

    assert prepared.planned is planned
    assert prepared.request is expected
    assert seen == {
        "capability_map": {"plasma.transport": "plasma.transport"},
        "backend_target": "moose",
        "model": model,
        "physics_capabilities": ("plasma.transport",),
    }


def test_run_sol_experiment_delegates_to_runtime_consumer_without_scientific_relabel(monkeypatch):
    request = SolRequest(
        backend_target={"target": "moose"},
        mapping_plan={"public_contract_version": "0.2", "actions": []},
        realization_spec={"public_contract_version": "0.2", "entities": []},
    )
    prepared = gateway.SolPreparedExperiment(planned=object(), request=request)
    expected = SolRuntimeOutcome(completed=False, kind=None, evidence={"status": "runtime-only"})
    seen: dict[str, object] = {}

    def fake_invoke(consumer, adapter, supplied_request, *, timeout_seconds):
        seen.update(
            consumer=consumer,
            adapter=adapter,
            request=supplied_request,
            timeout_seconds=timeout_seconds,
        )
        return expected

    monkeypatch.setattr(gateway, "invoke_runtime_consumer", fake_invoke)
    outcome = gateway.run_sol_experiment(
        prepared,
        consumer=Path("/runtime/consumer"),
        adapter=Path("/runtime/adapter"),
        timeout_seconds=17.0,
    )

    assert outcome is expected
    assert seen == {
        "consumer": Path("/runtime/consumer"),
        "adapter": Path("/runtime/adapter"),
        "request": request,
        "timeout_seconds": 17.0,
    }
