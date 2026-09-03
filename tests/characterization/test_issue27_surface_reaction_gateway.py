from __future__ import annotations

import math
from pathlib import Path

import pytest

from experiments.Issue27_surface_reactions.controlled_wall.run import (
    Issue27A1Error,
    _validated_parameters,
)
from qpx_harness.application.experiment_registry import (
    protocol_registered,
    resolve_protocol,
)
from qpx_harness.application.experiment_spec import load_experiment_spec

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "experiments/Issue27_surface_reactions/A1_o_recombination/experiment.json"
INPUT = ROOT / "experiments/Issue27_surface_reactions/controlled_wall/input.i"


def test_issue27_a1_spec_uses_canonical_qpx_gateway() -> None:
    spec = load_experiment_spec(SPEC)
    assert spec.experiment_id == "issue27-a1-o-recombination"
    assert spec.protocol == "issue27-surface-reaction-controlled-wall"
    assert protocol_registered(spec.protocol)
    assert callable(resolve_protocol(spec.protocol))


def test_issue27_a1_prescribed_flux_contract_is_frozen() -> None:
    spec = load_experiment_spec(SPEC)
    frozen = _validated_parameters(spec.parameters)
    assert frozen["reaction_id"] == "O_to_half_O2"
    assert math.isclose(float(frozen["event_flux_mol_m2_s"]), 0.1)
    assert math.isclose(float(frozen["outward_O_mass_flux_kg_m2_s"]), 0.0016)
    assert math.isclose(float(frozen["initial_w_O"]), 0.1)
    assert math.isclose(float(frozen["initial_w_O2"]), 0.9)
    assert math.isclose(float(frozen["dt_seconds"]), 0.1)


def test_issue27_a1_rejects_unvalidated_reaction_extension() -> None:
    with pytest.raises(Issue27A1Error, match="currently accepts only"):
        _validated_parameters({"reaction_id": "Om_to_O"})


def test_issue27_a1_input_is_single_purpose_flux_discriminator() -> None:
    text = INPUT.read_text(encoding="utf-8")
    assert "type = QPXFVConservativeMassFractionTimeDerivative" in text
    assert "type = FVNeumannBC" in text
    assert "boundary = right" in text
    assert "variable = w_O" in text
    assert "property_name = w_O2_constraint" in text
    assert "expression = '1.0-wo'" in text
    assert "potential_plasma" not in text
    assert "QPXFVElectrostaticDrift" not in text
    assert "surface_charge" not in text
    assert "secondary" not in text.lower()
