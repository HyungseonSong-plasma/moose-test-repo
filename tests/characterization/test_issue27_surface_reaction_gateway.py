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
from experiments.Issue27_surface_reactions.controlled_wall.sticking import (
    A1B_BC_NAME,
    A1B_FLUX_FUNCTOR,
    A1B_FLUX_MATERIAL,
    A1B_WALL_AREA_PP,
    A1B_WALL_RATE_PP,
    Issue27A1bError,
    _build_sticking_case_input,
    _validated_sticking_parameters,
)
from qpx_harness.application.experiment_spec import load_experiment_spec
from qpx_harness.adapters.moose import blocks as mb
from qpx_harness.adapters.moose import parameters as mp

ROOT = Path(__file__).resolve().parents[2]
A1_SPEC = ROOT / "experiments/Issue27_surface_reactions/A1_o_recombination/experiment.json"
A1B_SPEC = ROOT / "experiments/Issue27_surface_reactions/A1b_o_sticking/experiment.json"
R4_SOURCE = ROOT / "experiments/Issue91_real_qvt_r3/r3_e0/heavy_base.i"
RETIRED_STANDALONE_INPUT = ROOT / "experiments/Issue27_surface_reactions/controlled_wall/input.i"


def test_issue27_a1_spec_is_historical_provenance_not_canonical_dispatch() -> None:
    spec = load_experiment_spec(A1_SPEC)
    assert spec.experiment_id == "issue27-a1-o-recombination"
    assert spec.protocol == "issue27-surface-reaction-controlled-wall"
    assert not (ROOT / "qpx_harness/application/experiment_registry.py").exists()
    assert not (ROOT / "qpx_harness/application/protocols").exists()


def test_issue27_a1_prescribed_flux_contract_is_frozen() -> None:
    spec = load_experiment_spec(A1_SPEC)
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
    spec = load_experiment_spec(A1_SPEC)
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

    assert mb.has_block(text, "Variables/potential_plasma")
    assert mb.has_block(text, "FVKernels/r31_phi_diffusion")
    assert mb.has_block(text, "FVKernels/r31_phi_charge_source")
    assert mp.get_parameter(
        text, "FVKernels/n_e_drift", "potential"
    ) == "potential_plasma"
    assert mp.get_parameter(
        text, "FVKernels/O2p_electrostatic_drift", "potential"
    ) == "potential_plasma"
    assert mb.has_block(text, "FVKernels/O_advection")
    assert mb.has_block(text, "FVKernels/O_diffusion")


def test_issue27_a1b_spec_uses_same_historical_protocol_provenance() -> None:
    spec = load_experiment_spec(A1B_SPEC)
    assert spec.experiment_id == "issue27-a1b-o-sticking"
    assert spec.protocol == "issue27-surface-reaction-controlled-wall"
    assert spec.parameters["wall_model"] == "sticking"
    assert not (ROOT / "qpx_harness/application/experiment_registry.py").exists()


def test_issue27_a1b_sticking_contract_is_frozen() -> None:
    spec = load_experiment_spec(A1B_SPEC)
    frozen = _validated_sticking_parameters(spec.parameters)
    assert frozen["reaction_id"] == "O_to_half_O2"
    assert frozen["wall_boundary"] == "plasma_wafer"
    assert math.isclose(float(frozen["sticking_coefficient"]), 0.2)
    assert frozen["motz_wise_correction"] is False
    assert frozen["gas_temperature_functor"] == "T_g"
    assert frozen["moose_flux_factor"] == -1.0
    expression = str(frozen["outward_mass_flux_expression"])
    assert "rho*wo" in expression
    assert "sqrt(" in expression
    assert "tg" in expression


def test_issue27_a1b_rejects_motz_wise_in_this_discriminator() -> None:
    with pytest.raises(Issue27A1bError, match="Motz-Wise OFF"):
        _validated_sticking_parameters(
            {
                "reaction_id": "O_to_half_O2",
                "wall_model": "sticking",
                "wall_boundary": "plasma_wafer",
                "sticking_coefficient": 0.2,
                "motz_wise_correction": True,
                "gas_temperature_functor": "T_g",
            }
        )


@pytest.mark.parametrize(
    ("factor", "expected_factor"),
    ((0.0, 0.0), (-1.0, -1.0)),
)
def test_issue27_a1b_is_r4_qf1_plus_state_dependent_wafer_flux(
    factor: float,
    expected_factor: float,
) -> None:
    spec = load_experiment_spec(A1B_SPEC)
    base = R4_SOURCE.read_text(encoding="utf-8")
    text, meta = _build_sticking_case_input(
        base,
        parameters=spec.parameters,
        bc_factor=factor,
    )

    assert meta["predecessor"]["audit"]["status"] == "PASS"
    assert meta["frozen_phase"] == {
        "R4_QF1_preserved": True,
        "volumetric_reactions": False,
        "secondary_emission": False,
        "surface_accumulated_charge": False,
    }

    material = f"FunctorMaterials/{A1B_FLUX_MATERIAL}"
    assert mb.has_block(text, material)
    assert mp.get_parameter(text, material, "type") == "ADParsedFunctorMaterial"
    assert mp.get_parameter(text, material, "property_name") == A1B_FLUX_FUNCTOR
    assert tuple(mp.words(mp.get_parameter(text, material, "functor_names"))) == (
        "rho_mat",
        "w_O",
        "T_g",
    )

    bc = f"FVBCs/{A1B_BC_NAME}"
    assert mb.has_block(text, bc)
    assert mp.get_parameter(text, bc, "type") == "FVFunctorNeumannBC"
    assert mp.get_parameter(text, bc, "variable") == "w_O"
    assert mp.get_parameter(text, bc, "boundary") == "plasma_wafer"
    assert mp.get_parameter(text, bc, "functor") == A1B_FLUX_FUNCTOR
    assert math.isclose(
        float(mp.get_parameter(text, bc, "factor") or "nan"),
        expected_factor,
    )

    rate_pp = f"Postprocessors/{A1B_WALL_RATE_PP}"
    assert mb.has_block(text, rate_pp)
    assert mp.get_parameter(text, rate_pp, "functor") == A1B_FLUX_FUNCTOR
    assert mp.get_parameter(text, rate_pp, "boundary") == "plasma_wafer"

    area_pp = f"Postprocessors/{A1B_WALL_AREA_PP}"
    assert mb.has_block(text, area_pp)
    assert mp.get_parameter(text, area_pp, "boundary") == "plasma_wafer"

    assert mb.has_block(text, "Variables/potential_plasma")
    assert mb.has_block(text, "FVKernels/r31_phi_diffusion")
    assert mb.has_block(text, "FVKernels/r31_phi_charge_source")
    assert mp.get_parameter(
        text, "FVKernels/n_e_drift", "potential"
    ) == "potential_plasma"


def test_issue27_a1_standalone_1d_input_is_retired() -> None:
    assert not RETIRED_STANDALONE_INPUT.exists()
