from __future__ import annotations

import math
from pathlib import Path

import pytest

from experiments.Issue27_surface_reactions.controlled_wall.run import (
    A1_BC_NAME,
    A1_WALL_AREA_PP,
    Issue27A1Error,
    _build_case_input,
    _validated_parameters,
)
from qpx_harness.application.experiment_registry import (
    protocol_registered,
    resolve_protocol,
)
from qpx_harness.application.experiment_spec import load_experiment_spec
from qpx_harness.moose import blocks as mb
from qpx_harness.moose import parameters as mp

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "experiments/Issue27_surface_reactions/A1_o_recombination/experiment.json"
R4_SOURCE = ROOT / "experiments/Issue91_real_qvt_r3/r3_e0/heavy_base.i"
RETIRED_STANDALONE_INPUT = ROOT / "experiments/Issue27_surface_reactions/controlled_wall/input.i"


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
    assert frozen["wall_boundary"] == "plasma_wafer"
    assert math.isclose(float(frozen["event_flux_mol_m2_s"]), 0.1)
    assert math.isclose(float(frozen["O_mass_flux_magnitude_kg_m2_s"]), 0.0016)
    assert frozen["fvneumann_sign_mapping"] == "UNRESOLVED_UNTIL_PLUS_MINUS_RUNTIME"


def test_issue27_a1_rejects_unvalidated_extensions() -> None:
    with pytest.raises(Issue27A1Error, match="currently accepts only"):
        _validated_parameters({"reaction_id": "Om_to_O"})
    with pytest.raises(Issue27A1Error, match="frozen to"):
        _validated_parameters(
            {
                "reaction_id": "O_to_half_O2",
                "wall_boundary": "plasma_cover",
            }
        )


@pytest.mark.parametrize(
    ("sign", "expected_value"),
    ((0, 0.0), (1, 0.0016), (-1, -0.0016)),
)
def test_issue27_a1_is_r4_qf1_plus_one_wafer_wall_flux(
    sign: int,
    expected_value: float,
) -> None:
    spec = load_experiment_spec(SPEC)
    base = R4_SOURCE.read_text(encoding="utf-8")
    text, meta = _build_case_input(
        base,
        parameters=spec.parameters,
        fvbc_sign=sign,
    )

    assert meta["predecessor"]["audit"]["status"] == "PASS"
    assert meta["frozen_phase"] == {
        "R4_QF1_preserved": True,
        "volumetric_reactions": False,
        "secondary_emission": False,
        "surface_accumulated_charge": False,
    }

    bc = f"FVBCs/{A1_BC_NAME}"
    assert mb.has_block(text, bc)
    assert mp.get_parameter(text, bc, "type") == "FVNeumannBC"
    assert mp.get_parameter(text, bc, "variable") == "w_O"
    assert mp.get_parameter(text, bc, "boundary") == "plasma_wafer"
    assert math.isclose(float(mp.get_parameter(text, bc, "value") or "nan"), expected_value)

    area = f"Postprocessors/{A1_WALL_AREA_PP}"
    assert mb.has_block(text, area)
    assert mp.get_parameter(text, area, "boundary") == "plasma_wafer"

    # The surface discriminator must remain on the accepted solved-Poisson
    # closed-feedback architecture rather than falling back to a standalone FV toy.
    assert mb.has_block(text, "Variables/potential_plasma")
    assert mb.has_block(text, "FVKernels/r31_phi_diffusion")
    assert mb.has_block(text, "FVKernels/r31_phi_charge_source")
    assert mp.get_parameter(
        text, "FVKernels/n_e_drift", "potential"
    ) == "potential_plasma"
    assert mp.get_parameter(
        text, "FVKernels/O2p_electrostatic_drift", "potential"
    ) == "potential_plasma"

    # Existing heavy FV face kernels guarantee real-qvt face assembly is active.
    assert mb.has_block(text, "FVKernels/O_advection")
    assert mb.has_block(text, "FVKernels/O_diffusion")


def test_issue27_a1_standalone_1d_input_is_retired() -> None:
    assert not RETIRED_STANDALONE_INPUT.exists()
