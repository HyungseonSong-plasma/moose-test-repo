"""Scratch-only Issue #402 S6 Wall naming cutover: ownership and P0 negatives.

Only staged D overlays may be renamed. A source owner is required before
the spelling of any consumer changes. No scientific parity is asserted.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "experiments/Issue402_plasma_dsl_g1/chemistry/prepare_s6_run_input.py"
spec = importlib.util.spec_from_file_location("issue402_s6_wall_cutover", MODULE)
assert spec and spec.loader
stage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage)


ION_PRODUCER = """[FunctorMaterials]
  [ion_wall_flux]
    type = PhysicsIonWallFluxMaterial
    ion_number_density = n_O2p
    potential = potential
    mobility = O2p_mobility
    gas_temperature = T_g
    charge_number = 1
    molar_mass = 0.032
    sticking = 1
  []
  [atomic_positive_ion_wall_flux]
    type = PhysicsIonWallTotalFluxMaterial
    output_prefix = atomic_positive_
    ion_number_density = n_Op
    potential = potential
    mobility = Op_mobility
    gas_temperature = T_g
    charge_number = 1
    molar_mass = 0.016
    sticking = 1
  []
  [negative_ion_wall_flux]
    type = PhysicsIonWallTotalFluxMaterial
    output_prefix = negative_
    ion_number_density = n_Om
    potential = potential
    mobility = Om_mobility
    gas_temperature = T_g
    charge_number = -1
    molar_mass = 0.016
    sticking = 1
  []
  [electron_wall_flux]
    type = PhysicsElectronAdjacentSheathWallFluxMaterial
    electron_density = n_e
    mean_energy = mean_en_solved
    potential = potential
  []
[]
"""

CONSUMERS = """[FunctorMaterials]
  [wall_charge_ledger]
    type = ADParsedFunctorMaterial
    property_name = signed_surface_current
    functor_names = 'ion_wall_number_flux atomic_positive_ion_wall_number_flux negative_ion_wall_number_flux electron_wall_number_flux'
    functor_symbols = 'g_O2p g_Op g_Om g_e'
    expression = 'g_O2p + g_Op - g_Om - g_e'
  []
[]
[BCs]
  [electron_particle_wall]
    type = PhysicsFEMLogMolarElectronFieldLimitedFluxBC
    variable = log_e
    wall_number_flux = electron_wall_number_flux
    boundary = right
  []
[]
[FVBCs]
  [O2p_wall]
    type = FVFunctorNeumannBC
    variable = log_O2p
    functor = ion_wall_number_flux
    factor = -1.6605390671738466e-24
    boundary = right
  []
  [Op_wall]
    type = FVFunctorNeumannBC
    variable = log_Op
    functor = atomic_positive_ion_wall_number_flux
    factor = -1.6605390671738466e-24
    boundary = right
  []
  [Om_wall]
    type = FVFunctorNeumannBC
    variable = log_Om
    functor = negative_ion_wall_number_flux
    factor = -1.6605390671738466e-24
    boundary = right
  []
[]
"""


def _staged(source=ION_PRODUCER, consumers=CONSUMERS):
    return {Path("native.i"): source, Path("consumers.i"): consumers}


def test_s6_wall_names_rewrite_all_verified_producers_and_consumers():
    original = _staged()
    updated, report = stage.canonicalize_staged_wall_inputs(original)
    assert original[Path("native.i")] == ION_PRODUCER
    assert original[Path("consumers.i")] == CONSUMERS
    native, consumer = updated[Path("native.i")], updated[Path("consumers.i")]
    assert report["status"] == "SCRATCH_ONLY_SPECIES_WALL_NAMES"
    assert report["owner_count"] == 4
    assert {x["species_id"] for x in report["wall_material_owners"]} == {
        "O2p", "Om", "Op", "e"}
    assert native.count("species_id = ") == 4
    assert "output_prefix =" not in native
    assert "molar_mass = 0.032" in native
    assert "molar_mass = 0.016" in native
    assert "charge_number = -1" in native
    assert "sticking = 1" in native
    for old in stage._WALL_KNOWN_LEGACY:
        assert old not in native + consumer
    for s in ("O2p", "Op", "Om"):
        assert "functor = " + s + "_wall_number_flux" in consumer
    assert "wall_number_flux = e_wall_number_flux" in consumer
    assert "functor_names = 'O2p_wall_number_flux Op_wall_number_flux Om_wall_number_flux e_wall_number_flux'" in consumer
    assert "e_wall_sheath_drop_V" in report["wall_material_owners"][0]["outputs"].values() or any(
        "e_wall_sheath_drop_V" in x["outputs"].values() for x in report["wall_material_owners"])
    assert report["P3"] == "NOT_RUN" and report["science"] == "SCIENCE_HOLD"


def test_wall_cutover_never_writes_its_input_map():
    original = _staged()
    updated, _ = stage.canonicalize_staged_wall_inputs(original)
    assert original is not updated
    assert original[Path("native.i")] == ION_PRODUCER
    assert original[Path("consumers.i")] == CONSUMERS


def test_unowned_s6_legacy_functor_fails_before_any_rewrite():
    source = ION_PRODUCER.replace(
        "type = PhysicsIonWallFluxMaterial", "type = QPXIonWallFluxMaterial", 1)
    original = _staged(source)
    with pytest.raises(ValueError, match="S6_WALL_UNVERIFIED_LEGACY_OUTPUT_OWNER"):
        stage.canonicalize_staged_wall_inputs(original)
    assert original[Path("native.i")] == source
    assert original[Path("consumers.i")] == CONSUMERS


def test_ambiguous_wall_prefix_fails_closed():
    source = ION_PRODUCER.replace("output_prefix = atomic_positive_",
                                  "output_prefix = some_other_ion_", 1)
    original = _staged(source)
    with pytest.raises(ValueError, match="S6_WALL_UNRECOGNIZED_OUTPUT_PREFIX"):
        stage.canonicalize_staged_wall_inputs(original)
    assert original[Path("native.i")] == source


def test_duplicate_wall_provider_fails_closed():
    extra = """  [duplicate_ion_wall]
    type = PhysicsIonWallTotalFluxMaterial
    ion_number_density = n_O2p
    potential = potential
    mobility = O2p_mobility
    gas_temperature = T_g
    charge_number = 1
    molar_mass = 0.032
  []
"""
    source = ION_PRODUCER.replace("  [electron_wall_flux]", extra + "  [electron_wall_flux]")
    with pytest.raises(ValueError, match="S6_WALL_DUPLICATE_OUTPUT_OWNER"):
        stage.canonicalize_staged_wall_inputs(_staged(source))


def test_no_legacy_wall_outputs_is_safe_noop():
    original = {Path("empty.i"): "[Mesh]\n  type = GeneratedMesh\n[]\n"}
    updated, report = stage.canonicalize_staged_wall_inputs(original)
    assert updated == original
    assert report["owner_count"] == 0
    assert report["status"] == "NO_LEGACY_WALL_OUTPUTS"
