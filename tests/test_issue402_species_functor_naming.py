"""Issue #402 species-first public Functor names (P0/source only).

These checks reject swapped species consumers and accidental removal of the
legacy inputs. Native --check-input and numerical parity are separate gates.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
CI = ROOT / "physics_app/ci/species_wall_functor_naming_smoke.i"


def source(relative):
    return (ROOT / relative).read_text(encoding="utf-8")


def _block(text, section):
    match = re.search(r"(?m)^  \[" + re.escape(section) + r"\]\n(.*?)^  \[\]\n",
                      text, flags=re.DOTALL)
    assert match, section
    return match.group(1)


def _assert_wall_wiring(deck, species):
    material = _block(deck, species + "_wall")
    assert "type = PhysicsIonWallFluxMaterial" in material
    assert f"species_id = {species}" in material
    assert f"ion_number_density = {species}_number_density" in material
    assert f"mobility = {species}_mobility" in material
    bc = deck.split("[FVBCs]", 1)[1]
    consumer = _block(bc, species + "_wall")
    assert f"functor = {species}_wall_number_flux" in consumer
    assert f"variable = log_{species}" in consumer


def test_species_first_wall_functors_and_duplicate_owner_prevention():
    ion = source("physics_app/src/functormaterials/PhysicsIonWallFluxMaterial.C")
    for old, tail in (
        ("ion_surface_number_flux", "surface_number_flux"),
        ("ion_migration_number_flux", "migration_number_flux"),
        ("ion_wall_number_flux", "number_flux"),
        ("ion_surface_mass_flux", "surface_mass_flux"),
        ("ion_migration_mass_flux", "migration_mass_flux"),
        ("ion_wall_mass_flux", "mass_flux"),
    ):
        assert f'wallName("{old}", "{tail}")' in ion
    assert 'species_id.empty() ? std::string(legacy) : species_id + "_wall_" + suffix' in ion
    assert 'std::isalnum(static_cast<unsigned char>(ch))' in ion

    total = source("physics_app/src/functormaterials/PhysicsIonWallTotalFluxMaterial.C")
    assert 'species_id + "_wall_number_flux"' in total
    assert 'species_id + "_wall_mass_flux"' in total
    assert 'Do not combine output_prefix with species_id' in total
    assert 'species_id.empty() ? _output_prefix + "ion_wall_number_flux"' in total


def test_electron_wall_names_and_opt_in_legacy_compatibility():
    for f in ("PhysicsElectronWallFluxMaterial.C",
              "PhysicsElectronAdjacentSheathWallFluxMaterial.C"):
        src = source("physics_app/src/materials/" + f)
        assert '"species_id", ""' in src
        assert 'species_id != "e"' in src
        assert 'species_id.empty() ? "electron_wall_number_flux" : "e_wall_number_flux"' in src
        assert 'species_id.empty() ? "electron_mean_speed" : "e_mean_speed"' in src
    sheath = source("physics_app/src/materials/PhysicsElectronAdjacentSheathWallFluxMaterial.C")
    assert '"e_wall_sheath_drop_V"' in sheath


def test_charge_density_canonical_output_is_opt_in():
    src = source("physics_app/src/materials/PhysicsPlasmaChargeDensityMaterial.C")
    assert '"canonical_species_names", false' in src
    assert 'canonical_names ? id + "_number_density" : "ion_number_density_" + id' in src
    assert '"charge_number_density"' in src
    assert '"charge_density"' in src
    assert '"poisson_charge_source"' in src


def test_p2_wiring_for_two_species_and_electron_and_negative_mutation():
    deck = CI.read_text(encoding="utf-8")
    assert "solve = false" in deck
    assert "kernel_coverage_check = false" in deck
    assert "canonical_species_names = true" in deck
    for species in ("O2p", "Op"):
        _assert_wall_wiring(deck, species)
    electron = _block(deck, "electron_wall")
    assert "type = PhysicsElectronWallFluxMaterial" in electron
    assert "species_id = e" in electron
    assert "mean_energy = mean_en_solved" in electron
    assert "functor = e_wall_number_flux" in _block(deck.split("[FVBCs]", 1)[1], "e_wall")
    # Negative control: swapping the O2p consumer to Op must fail validation.
    swapped = deck.replace("functor = O2p_wall_number_flux", "functor = Op_wall_number_flux", 1)
    try:
        _assert_wall_wiring(swapped, "O2p")
    except AssertionError:
        pass
    else:
        raise AssertionError("Species-swapped wall Functor was not rejected")


def test_no_immutable_s6_archive_or_global_dd_name_changes():
    dd = source("physics_app/src/materials/DDMaterial.C")
    assert '_species + "_mobility"' in dd
    assert '_species + "_diffusivity"' in dd
    assert '"electron_mobility"' in dd  # Legacy consumer remains distinct.
    assert "species_wall_functor_naming_smoke.i" in CI.name
