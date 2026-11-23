"""Issue #633 C2 P15-A/P16-A/P17-A: source-bound static/negative tests.

The candidate is synthetic until the dependencies and actual generator exist;
these tests do not promote any P15/P16/P17 implementation gate.
"""
from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ci.guards.issue633_c2_wall_bc_contract import (  # noqa: E402
    CANONICAL_ION_ORDER, ContractError, DIELECTRIC_SIDES, GENERAL_SIDES,
    INV_AVOGADRO, LEGACY, check_candidate, check_native_source,
)


def _fixture(species_ids=CANONICAL_ION_ORDER):
    """Synthetic NEW-ONLY input, NOT the product of DDContinuityEq."""
    material = ["[FunctorMaterials]"]
    fvbc = ["[FVBCs]"]
    for species in species_ids:
        charge, molar_mass = LEGACY[species][6:8]
        material.extend([
            f"  [{species}_wall]", "    type = IonWallFluxMaterial",
            f"    species_id = {species}",
            f"    ion_number_density = {species}_number_density",
            f"    mobility = {species}_mobility",
            "    potential = potential", "    gas_temperature = temperature",
            "    use_element_gradient_for_potential = true",
            f"    charge_number = {charge}", f"    molar_mass = {molar_mass}",
            "    sticking = 1.0", "    migration_gate_smoothing_width = 1e-3",
            "  []",
        ])
        fvbc.extend([
            f"  [{species}_wall]", "    type = FVFunctorNeumannBC",
            f"    variable = log_{species}",
            f"    functor = {species}_wall_number_flux",
            f"    factor = {-INV_AVOGADRO:.17g}",
            f"    boundary = '{' '.join(GENERAL_SIDES)}'", "  []",
        ])
        for side in ("cover", "wafer", "focus_ring"):
            fvbc.extend([
                f"  [{species}_{side}_dielectric]", "    type = FVLogMolarDielectricFluxBC",
                f"    variable = log_{species}",
                f"    signed_number_flux = {species}_wall_number_flux",
                f"    boundary = plasma_{side}", "  []",
            ])
    for side in ("cover", "wafer", "focus_ring"):
        material.extend([
            f"  [{side}_surface_current]", "    type = ADParsedFunctorMaterial",
            f"    property_name = {side}_net_surface_current_density",
            "    functor_names = 'O2p_wall_number_flux Op_wall_number_flux Om_wall_number_flux electron_wall_number_flux'",
            "    functor_symbols = 'gi gop gm ge'",
            "    expression = '1.602176634e-19*(gi+gop-gm-ge)'",
            "  []",
        ])
    return "\n".join([*material, "[]", *fvbc, "[]", ""])


def test_actual_archived_native_source_contract_and_blob_identity():
    raw = (ROOT / "experiments/Issue402_plasma_dsl_g1/native/s6_c0_physics_base_no_d1.i").read_bytes()
    assert check_native_source(raw) == {"material": 3, "general_fvbc": 3, "dielectric_fvbc": 9}


def test_synthetic_new_only_contract_counts_and_signs():
    assert check_candidate(_fixture()) == {"material": 3, "general_fvbc": 3, "dielectric_fvbc": 9}
    assert check_candidate(_fixture(("Om",)), ("Om",)) == {"material": 1, "general_fvbc": 1, "dielectric_fvbc": 3}
    assert set(DIELECTRIC_SIDES) == {"plasma_cover", "plasma_wafer", "plasma_focus_ring"}


@pytest.mark.parametrize("needle,replacement", [
    ("  [O2p_wall]\n    type = IonWallFluxMaterial", "  [wrong_wall]\n    type = IonWallFluxMaterial"),
    ("species_id = O2p", "species_id = Op"),
    ("ion_number_density = O2p_number_density", "ion_number_density = Op_number_density"),
    ("mobility = Om_mobility", "mobility = O2p_mobility"),
    ("charge_number = -1", "charge_number = 1"),
    ("molar_mass = 0.032", "molar_mass = 0.016"),
    ("    type = IonWallFluxMaterial", "    type = PhysicsIonWallFluxMaterial"),
    ("factor = -1.6605390671738466e-24", "factor = 1.6605390671738466e-24"),
    ("functor = O2p_wall_number_flux", "functor = Op_wall_number_flux"),
    ("signed_number_flux = Om_wall_number_flux", "signed_number_flux = Op_wall_number_flux"),
    ("boundary = plasma_wafer", "boundary = plasma_cover"),
    ("type = FVLogMolarDielectricFluxBC", "type = PhysicsFVLogMolarDielectricFluxBC"),
    ("functor_names = 'O2p_wall_number_flux Op_wall_number_flux Om_wall_number_flux electron_wall_number_flux'",
     "functor_names = 'O2p_wall_number_flux Op_wall_number_flux Op_wall_number_flux electron_wall_number_flux'"),
    ("expression = '1.602176634e-19*(gi+gop-gm-ge)'",
     "expression = '1.602176634e-19*(gi+gop+gm-ge)'"),
])
def test_fail_closed_mutations(needle, replacement):
    original = _fixture()
    assert needle in original, needle
    with pytest.raises(ContractError):
        check_candidate(original.replace(needle, replacement, 1))


def test_missing_dielectric_bc_fails():
    text = _fixture()
    block = "  [O2p_focus_ring_dielectric]\n    type = FVLogMolarDielectricFluxBC\n    variable = log_O2p\n    signed_number_flux = O2p_wall_number_flux\n    boundary = plasma_focus_ring\n  []\n"
    assert block in text
    with pytest.raises(ContractError, match="missing"):
        check_candidate(text.replace(block, ""))


def test_duplicate_native_or_extra_fvbc_fails():
    text = _fixture()
    block = "  [O2p_wall]\n    type = FVFunctorNeumannBC\n    variable = log_O2p\n"
    assert block in text
    duplicate = "  [old_ion_wall]\n    type = FVFunctorNeumannBC\n    variable = log_O2p\n    functor = O2p_wall_number_flux\n    factor = -1.6605390671738466e-24\n    boundary = 'plasma_right'\n  []\n"
    with pytest.raises(ContractError, match="unexpected/duplicate"):
        check_candidate(text.replace("[FVBCs]\n", "[FVBCs]\n" + duplicate, 1))


def test_missing_surface_current_consumer_fails():
    original = _fixture()
    with pytest.raises(ContractError, match="missing"):
        check_candidate(original.replace("[cover_surface_current]", "[missing_current]"))


def test_dielectric_factor_is_forbidden_and_absent_sideset_rejected():
    text = _fixture()
    injected = text.replace("boundary = plasma_cover", "factor = -1.6605390671738466e-24\n    boundary = plasma_cover", 1)
    with pytest.raises(ContractError, match="dielectric must"):
        check_candidate(injected)
    with pytest.raises(ContractError, match="sideset"):
        check_candidate(text.replace("boundary = plasma_wafer", "boundary = absent_wafer", 1))


def test_reject_unselected_or_repeated_species():
    with pytest.raises(ContractError):
        check_candidate(_fixture(), ("O2p", "O2p"))
    with pytest.raises(ContractError):
        check_candidate(_fixture(), ("O2p", "unknown"))
    with pytest.raises(ContractError):
        check_candidate(_fixture(), ("O2p",))
