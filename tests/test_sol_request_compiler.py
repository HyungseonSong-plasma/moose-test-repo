from __future__ import annotations

from dataclasses import replace
import math

import pytest

from physics_harness.ontology.model_artifact import CanonicalModelArtifactRef
from physics_harness.ontology.quantity import CanonicalQuantitySpec, RealizationQuantity
from physics_harness.ontology.sol_request import (
    CanonicalActionBinding,
    CanonicalEntity,
    CanonicalRealizationModel,
    CanonicalRelation,
    CanonicalScope,
    SolRequestCompilationError,
    SolRequestCompiler,
)


def _model(action_id: str = "physics_action_1") -> CanonicalRealizationModel:
    artifact = CanonicalModelArtifactRef(
        model_id="sol.model.steady_thermal",
        artifact_id="thermal-v1",
        schema_version="1",
        public_contract="0.2",
        source="canonical-catalog",
        revision="1",
        digest="sha256:test",
    )
    temperature = RealizationQuantity(
        CanonicalQuantitySpec("sol.quantity.temperature", "si.K"), 300.0
    )
    return CanonicalRealizationModel(
        artifact=artifact,
        ontology_version="sol-ontology-1",
        entities=(
            CanonicalEntity(
                "sol.entity.thermal_model", "physics_model", "thermal.steady", (temperature,)
            ),
            CanonicalEntity(
                "sol.entity.domain", "spatial_model", "geometry.domain"
            ),
        ),
        scopes=(CanonicalScope("sol.scope.domain", ("sol.entity.domain",)),),
        relations=(CanonicalRelation(
            "defined_on", "sol.entity.thermal_model", "sol.entity.domain"
        ),),
        action_bindings=(CanonicalActionBinding(
            action_id, ("sol.entity.thermal_model",), ("sol.scope.domain",)
        ),),
    )


def _compiler() -> SolRequestCompiler:
    return SolRequestCompiler(
        {"steady_thermal": "thermal.steady_conduction"}, backend_target="moose-adapter"
    )


def test_complete_canonical_model_compiles_public_contract_request() -> None:
    request = _compiler().compile(_model(), physics_capabilities=("steady_thermal",))
    assert request.backend_target == {
        "public_contract_version": "0.2",
        "target": "moose-adapter",
        "required_capabilities": ["thermal.steady_conduction"],
    }
    assert request.mapping_plan["actions"] == [{"id": "physics_action_1", "dependencies": []}]
    assert request.realization_spec["source_model"] == "sol.model.steady_thermal"
    parameter = request.realization_spec["entities"][0]["parameters"][0]
    assert parameter["semantic_parameter"] == "sol.quantity.temperature"
    assert parameter["quantity"] == {"value": 300.0, "unit": "si.K"}


def test_missing_relation_or_scope_rejects() -> None:
    with pytest.raises(SolRequestCompilationError, match="entity/relation/scope"):
        _compiler().compile(replace(_model(), relations=()), physics_capabilities=("steady_thermal",))
    with pytest.raises(SolRequestCompilationError, match="entity/relation/scope"):
        _compiler().compile(replace(_model(), scopes=()), physics_capabilities=("steady_thermal",))


def test_missing_or_noncanonical_unit_rejects() -> None:
    bad_quantity = RealizationQuantity(
        CanonicalQuantitySpec("sol.quantity.temperature", "K"), 300.0
    )
    bad_entity = replace(_model().entities[0], parameters=(bad_quantity,))
    model = replace(_model(), entities=(bad_entity, _model().entities[1]))
    with pytest.raises(SolRequestCompilationError, match="quantity unit"):
        _compiler().compile(model, physics_capabilities=("steady_thermal",))


def test_nonfinite_quantity_rejects() -> None:
    for value in (math.nan, math.inf, -math.inf):
        bad_quantity = RealizationQuantity(
            CanonicalQuantitySpec("sol.quantity.temperature", "si.K"), value
        )
        bad_entity = replace(_model().entities[0], parameters=(bad_quantity,))
        model = replace(_model(), entities=(bad_entity, _model().entities[1]))
        with pytest.raises(SolRequestCompilationError, match="finite numeric"):
            _compiler().compile(model, physics_capabilities=("steady_thermal",))


def test_duplicate_graph_identifiers_reject() -> None:
    model = _model()
    with pytest.raises(SolRequestCompilationError, match="duplicate entity"):
        _compiler().compile(
            replace(model, entities=model.entities + (model.entities[0],)),
            physics_capabilities=("steady_thermal",),
        )
    with pytest.raises(SolRequestCompilationError, match="duplicate scope"):
        _compiler().compile(
            replace(model, scopes=model.scopes + (model.scopes[0],)),
            physics_capabilities=("steady_thermal",),
        )
    with pytest.raises(SolRequestCompilationError, match="duplicate action"):
        _compiler().compile(
            replace(model, action_bindings=model.action_bindings + (model.action_bindings[0],)),
            physics_capabilities=("steady_thermal",),
        )


def test_unsupported_capability_mapping_rejects() -> None:
    with pytest.raises(SolRequestCompilationError, match="unsupported Physics capability"):
        _compiler().compile(_model(), physics_capabilities=("plasma_unknown",))


def test_action_rename_preserves_realization_meaning() -> None:
    first = _compiler().compile(_model("opaque_a"), physics_capabilities=("steady_thermal",))
    second = _compiler().compile(_model("opaque_b"), physics_capabilities=("steady_thermal",))
    first_spec = dict(first.realization_spec)
    second_spec = dict(second.realization_spec)
    first_spec.pop("action_bindings")
    second_spec.pop("action_bindings")
    assert first_spec == second_spec
    assert first.realization_spec["action_bindings"][0]["subjects"] == second.realization_spec["action_bindings"][0]["subjects"]
    assert first.realization_spec["action_bindings"][0]["scopes"] == second.realization_spec["action_bindings"][0]["scopes"]


def test_action_ids_are_opaque_to_backend_spelling() -> None:
    request = _compiler().compile(
        _model("opaque_moose_lineage"), physics_capabilities=("steady_thermal",)
    )
    assert request.mapping_plan["actions"][0]["id"] == "opaque_moose_lineage"


def test_moose_spelling_injected_upstream_rejects() -> None:
    bad = replace(
        _model(),
        entities=(replace(_model().entities[0], semantic_type="moose.HeatConduction"), _model().entities[1]),
    )
    with pytest.raises(SolRequestCompilationError, match="MOOSE-native"):
        _compiler().compile(bad, physics_capabilities=("steady_thermal",))


def test_action_dependency_graph_is_explicit_and_validated() -> None:
    model = replace(
        _model(),
        action_bindings=(CanonicalActionBinding(
            "second", ("sol.entity.thermal_model",), ("sol.scope.domain",), ("missing",)
        ),),
    )
    with pytest.raises(SolRequestCompilationError, match="unknown action"):
        _compiler().compile(model, physics_capabilities=("steady_thermal",))

def test_action_dependency_self_cycle_rejects() -> None:
    model = replace(
        _model(),
        action_bindings=(
            CanonicalActionBinding(
                "self_cycle",
                ("sol.entity.thermal_model",),
                ("sol.scope.domain",),
                ("self_cycle",),
            ),
        ),
    )
    with pytest.raises(SolRequestCompilationError, match="acyclic"):
        _compiler().compile(model, physics_capabilities=("steady_thermal",))


def test_action_dependency_indirect_cycle_rejects() -> None:
    model = replace(
        _model(),
        action_bindings=(
            CanonicalActionBinding(
                "first",
                ("sol.entity.thermal_model",),
                ("sol.scope.domain",),
                ("second",),
            ),
            CanonicalActionBinding(
                "second",
                ("sol.entity.thermal_model",),
                ("sol.scope.domain",),
                ("first",),
            ),
        ),
    )
    with pytest.raises(SolRequestCompilationError, match="acyclic"):
        _compiler().compile(model, physics_capabilities=("steady_thermal",))

def test_deep_action_dependency_chain_compiles_without_recursion_error() -> None:
    depth = 1500
    bindings = []
    for index in range(depth):
        dependencies = (f"action_{index + 1}",) if index + 1 < depth else ()
        bindings.append(
            CanonicalActionBinding(
                f"action_{index}",
                ("sol.entity.thermal_model",),
                ("sol.scope.domain",),
                dependencies,
            )
        )
    model = replace(_model(), action_bindings=tuple(bindings))
    request = _compiler().compile(model, physics_capabilities=("steady_thermal",))
    assert len(request.mapping_plan["actions"]) == depth
    assert request.mapping_plan["actions"][0]["dependencies"] == ["action_1"]
    assert request.mapping_plan["actions"][-1]["dependencies"] == []

