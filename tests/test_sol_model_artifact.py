from __future__ import annotations

import pytest

from physics_harness.ontology.model_artifact import (
    CanonicalModelArtifactRef,
    ModelArtifactCatalog,
    ModelArtifactResolutionError,
)


def steady_thermal_ref() -> CanonicalModelArtifactRef:
    return CanonicalModelArtifactRef(
        model_id="sol:model:steady-thermal",
        artifact_id="sol:artifact:steady-thermal:a0.1",
        schema_version="sol-model/0.1",
        public_contract="0.2",
        source="HyungseonSong-plasma/simulation-ontology",
        revision="a2fefa213825dc58e03e03ab468ad1989dc39d6b",
        digest="sha256:steady-thermal-fixture",
    )


def test_resolves_exact_canonical_artifact() -> None:
    ref = steady_thermal_ref()
    catalog = ModelArtifactCatalog({ref.artifact_id: ref})

    assert catalog.resolve(ref.artifact_id) == ref
    assert list(ref.to_dict()) == [
        "model_id",
        "artifact_id",
        "schema_version",
        "public_contract",
        "source",
        "revision",
        "digest",
    ]
    assert ref.to_dict() == steady_thermal_ref().to_dict()


def test_catalog_rejects_artifact_identity_alias() -> None:
    ref = steady_thermal_ref()

    with pytest.raises(ValueError, match="catalog key must match"):
        ModelArtifactCatalog({"sol:artifact:alias": ref})


def test_unavailable_artifact_fails_closed() -> None:
    catalog = ModelArtifactCatalog({})

    with pytest.raises(ModelArtifactResolutionError, match="unavailable"):
        catalog.resolve("sol:artifact:missing")


def test_opaque_execution_model_ref_cannot_masquerade_as_sol_identity() -> None:
    ref = steady_thermal_ref()
    catalog = ModelArtifactCatalog({ref.artifact_id: ref})

    with pytest.raises(ModelArtifactResolutionError, match="opaque Physics reference"):
        catalog.resolve_execution_model_ref(ref.artifact_id)


@pytest.mark.parametrize(
    "field",
    ["model_id", "artifact_id", "schema_version", "public_contract", "source", "revision", "digest"],
)
def test_reference_rejects_missing_identity_or_provenance(field: str) -> None:
    values = steady_thermal_ref().to_dict()
    values[field] = ""

    with pytest.raises(ValueError, match=field):
        CanonicalModelArtifactRef(**values)
