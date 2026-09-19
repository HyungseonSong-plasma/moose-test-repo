from __future__ import annotations

import pytest

from physics_harness.ontology.quantity import (
    CanonicalQuantityCatalog,
    CanonicalQuantitySpec,
    RealizationQuantityError,
)


def _catalog() -> CanonicalQuantityCatalog:
    return CanonicalQuantityCatalog(
        {
            "sol.quantity.temperature": CanonicalQuantitySpec(
                quantity_id="sol.quantity.temperature", unit="K"
            )
        }
    )


def test_explicit_canonical_quantity_and_unit_bind_value() -> None:
    bound = _catalog().bind("sol.quantity.temperature", 300.0, unit="K")
    assert bound.spec.quantity_id == "sol.quantity.temperature"
    assert bound.spec.unit == "K"
    assert bound.value == 300.0


def test_missing_or_ambiguous_unit_is_rejected() -> None:
    with pytest.raises(RealizationQuantityError, match="explicit unit required"):
        _catalog().bind("sol.quantity.temperature", 300.0, unit=None)
    with pytest.raises(RealizationQuantityError, match="unit mismatch"):
        _catalog().bind("sol.quantity.temperature", 300.0, unit="degC")


def test_untyped_scalar_cannot_infer_semantics_from_local_spelling() -> None:
    with pytest.raises(RealizationQuantityError, match="cannot infer"):
        _catalog().bind_untyped("temperature_K", 300.0)


def test_local_action_rename_does_not_change_canonical_quantity_meaning() -> None:
    catalog = _catalog()
    first = catalog.bind("sol.quantity.temperature", 300.0, unit="K")
    renamed = catalog.bind("sol.quantity.temperature", 300.0, unit="K")
    assert first == renamed


def test_catalog_alias_cannot_relabel_quantity_identity() -> None:
    spec = CanonicalQuantitySpec("sol.quantity.temperature", "K")
    with pytest.raises(ValueError, match="catalog key"):
        CanonicalQuantityCatalog({"temperature_K": spec})


def test_moose_native_spelling_cannot_be_canonical_quantity_identity() -> None:
    with pytest.raises(ValueError, match="solver independent"):
        CanonicalQuantitySpec("moose.material.temperature", "K")
