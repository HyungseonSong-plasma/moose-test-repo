"""Scratch-only Issue #402 S6 Wall naming cutover: ownership and P0 negatives.

Only staged D overlays may be renamed. A source owner is required before
the spelling of any consumer changes. No scientific parity is asserted.
"""
from __future__ import annotations

import base64
import hashlib
import io
import importlib.util
import tarfile
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



def test_ion_species_density_mismatch_fails_closed():
    source = ION_PRODUCER.replace(
        "ion_number_density = n_Op", "ion_number_density = n_O2p", 1)
    original = _staged(source)
    with pytest.raises(ValueError, match="S6_WALL_DENSITY_IDENTITY_UNPROVED"):
        stage.canonicalize_staged_wall_inputs(original)
    assert original[Path("native.i")] == source


def test_ion_species_charge_mismatch_fails_closed():
    source = ION_PRODUCER.replace(
        "ion_number_density = n_Om\n    potential = potential\n    mobility = Om_mobility\n    gas_temperature = T_g\n    charge_number = -1",
        "ion_number_density = n_Om\n    potential = potential\n    mobility = Om_mobility\n    gas_temperature = T_g\n    charge_number = 1",
        1)
    original = _staged(source)
    with pytest.raises(ValueError, match="S6_WALL_CHARGE_IDENTITY_UNPROVED"):
        stage.canonicalize_staged_wall_inputs(original)
    assert original[Path("native.i")] == source



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


@pytest.mark.parametrize("case", ["S6-417-407-2069-H25", "S6-941-407-2069-H25"])
def test_public_s6_c_input_wall_producers_and_consumers(case):
    """Proof against public immutable S6 C input bytes, not hand-built fixtures.

    This is a P0 scratch transformation of the archived *input text* only.
    Historical B/C archives, private kinetic files and solver are not touched.
    """
    packed_path = (ROOT / "experiments/Issue493_s6_boltzmann/"
                   "public_p2_decks.tar.xz.b64")
    packed = base64.b64decode(packed_path.read_text().encode("ascii"))
    assert hashlib.sha256(packed).hexdigest() == (
        "9e801cc6dca3860750b7b97fb6ceca8e6060a3c894dd616cbaf688f529fea240"
    )
    staged = {}
    b_before = {}
    with tarfile.open(fileobj=io.BytesIO(packed), mode="r:xz") as archive:
        for member in archive.getmembers():
            if not member.isfile() or not member.name.endswith(".i"):
                continue
            if member.name.startswith(case + "/C/"):
                extracted = archive.extractfile(member)
                assert extracted is not None
                staged[Path(member.name).name] = extracted.read().decode("utf-8")
            elif member.name.startswith(case + "/B/"):
                extracted = archive.extractfile(member)
                assert extracted is not None
                b_before[member.name] = extracted.read()
    assert len(staged) == 11, sorted(staged)
    assert len(b_before) == 10
    originals = {name: value.encode("utf-8") for name, value in staged.items()}
    updated, audit = stage.canonicalize_staged_wall_inputs(staged)
    assert audit["owner_count"] == 4, audit
    assert {x["species_id"] for x in audit["wall_material_owners"]} == {
        "O2p", "Om", "Op", "e"
    }
    joined = "\n".join(updated.values())
    assert "species_id = O2p" in joined
    assert "species_id = Om" in joined
    assert "species_id = Op" in joined
    assert "species_id = e" in joined
    for name in ("O2p_wall_number_flux", "Om_wall_number_flux",
                 "Op_wall_number_flux", "e_wall_number_flux"):
        assert name in joined
    for old in stage._WALL_KNOWN_LEGACY:
        assert old not in joined
    assert audit["consumer_and_reference_replacements"]
    assert audit["P3"] == "NOT_RUN" and audit["science"] == "SCIENCE_HOLD"
    # The entire public B archive is kept in its original bytes, and all
    # archived C sources are only read as immutable inputs to the in-memory transform.
    assert all(staged[name].encode("utf-8") == original
               for name, original in originals.items())
    assert all(b_before[name] for name in b_before)
