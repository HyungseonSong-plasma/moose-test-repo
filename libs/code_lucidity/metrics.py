"""Source-grounded code understandability indicators; human raters are optional.

Diagnostics owns syntax extraction. This engine calculates numeric indicators;
Analysis owns their interpretation and any refactor trade-off.
No universal weights or synthetic understandability score are used.
"""

from __future__ import annotations

from collections.abc import Mapping

from .model import UnderstandabilityIndicator, StructuralMetric

PYTHON_AST_FIELDS = ("loc", "branches", "max_branch_nesting")


def from_python_ast(
    attributes: Mapping[str, object], *, evidence_ids: tuple[str, ...] = (),
) -> tuple[StructuralMetric, ...]:
    """Re-use collector measurements without another AST implementation."""
    measured = []
    for name in PYTHON_AST_FIELDS:
        value = attributes.get(name)
        if type(value) is int and value >= 0:
            measured.append(StructuralMetric(
                name=name, value=value, method="python_ast", evidence_ids=evidence_ids,
            ))
    return tuple(measured)


def derive_indicators(
    structural_metrics: tuple[StructuralMetric, ...],
    *, source_facts: tuple[StructuralMetric, ...] = (),
) -> tuple[UnderstandabilityIndicator, ...]:
    """Calculate measurable traits, not an understandability verdict.

    Branch density and candidate-call density are source-derived features
    motivated by control-flow and abstraction-navigation model dimensions.
    They do NOT measure independent responsibilities, semantic cohesion,
    confirmed callees or a human comprehension probability.
    """
    if (not isinstance(structural_metrics, tuple)
            or not all(isinstance(x, StructuralMetric) for x in structural_metrics)
            or not isinstance(source_facts, tuple)
            or not all(isinstance(x, StructuralMetric) for x in source_facts)):
        raise TypeError("UNDERSTANDABILITY_INDICATOR_FACTS_REQUIRED")

    structural = {x.name: x for x in structural_metrics}
    facts = {x.name: x for x in source_facts}
    loc = structural.get("loc")
    if loc is None or loc.value == 0:
        return ()

    result = []
    for name, numerator in (
        ("branch_density", structural.get("branches")),
        ("candidate_call_density", facts.get("candidate_call_sites")),
    ):
        if numerator is None:
            continue
        result.append(UnderstandabilityIndicator(
            name=name,
            value=numerator.value / loc.value,
            # Preserve historical method identity across package migration.
            method=f"hu_density_v1:{numerator.method}/{loc.method}",
            evidence_ids=tuple(sorted(set(loc.evidence_ids) | set(numerator.evidence_ids))),
        ))
    return tuple(result)
