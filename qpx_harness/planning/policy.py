"""Canonical planning semantic IR exports."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from qpx_harness.ontology.records import (
    ActionSpec,
    CapabilityDescriptor,
    ScientificPolicy,
    SearchDecision,
)

PolicyRule = Callable[..., tuple[ActionSpec, ...]]


@dataclass(frozen=True)
class PolicyRuleDescriptor:
    rule_id: str
    capability_id: str
    semantic_inputs: tuple[str, ...]
    semantic_outputs: tuple[str, ...]
    solver_independent: bool = True
    version: str = "1"


def default_capabilities() -> tuple[CapabilityDescriptor, ...]:
    """Small solver-independent capability catalog used by the canonical pipeline."""
    return (
        CapabilityDescriptor(
            capability_id="electron_energy_diffusion",
            responsibility="scientific_intervention",
            semantic_inputs=("diffusivity",),
            semantic_outputs=("controlled_diffusion_action",),
        ),
        CapabilityDescriptor(
            capability_id="electron_energy_inventory_observation",
            responsibility="observation",
            semantic_outputs=("energy_inventory",),
        ),
        CapabilityDescriptor(
            capability_id="quasi_neutral_initialization",
            responsibility="derived_policy",
            semantic_inputs=("heavy_species_charge",),
            semantic_outputs=("electron_reference",),
        ),
        CapabilityDescriptor(
            capability_id="poisson_electrostatics",
            responsibility="scientific_intervention",
            semantic_outputs=("electrostatic_action",),
        ),
        CapabilityDescriptor(
            capability_id="observability_instrumentation",
            responsibility="observation_intervention",
            semantic_outputs=("instrumentation_action",),
        ),
    )


__all__ = [
    "ActionSpec", "CapabilityDescriptor", "ScientificPolicy", "SearchDecision",
    "PolicyRule", "PolicyRuleDescriptor", "default_capabilities",
]
