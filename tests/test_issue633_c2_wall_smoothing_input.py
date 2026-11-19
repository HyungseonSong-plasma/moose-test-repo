"""Issue #633: migration_smoothing_width belongs to MOOSE input, not JSON.

P0 static and negative controls only; runtime P2 remains an independent gate.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "experiments/Issue402_plasma_dsl_g1"
JSON = ROOT / "physics_app/ci/issue633_c2_wall_3ion_overlay.json"
CONTINUITY = ROOT / "physics_app/src/physics/plasma/DDContinuityEq.C"
CHEM = ROOT / "physics_app/src/physics/plasma/Chemistry.C"
HEADER = ROOT / "physics_app/include/physics/plasma/Chemistry.h"
WALL = ROOT / "physics_app/src/functormaterials/IonWallFluxMaterial.C"
CASES = ("417", "941")
PARAM = "migration_smoothing_width"
RETIRED = "wall_migration_gate_smoothing_width"


def _value(line):
    return float(line.split("=", 1)[1].split("#", 1)[0].strip())


def test_newonly_s6_inputs_explicitly_preserve_001_v_per_m_width():
    # S6 continuity templates retain the old nonzero numerical treatment.
    # This does NOT make the parameter required for other MOOSE inputs.
    for case in CASES:
        path = PILOT / f"issue633_newonly_s6_{case}_continuity.template.i"
        text = path.read_text()
        assert f"chemistry/unified_s6_{case}_newonly.json" in text
        # Final-run JSON owns the ion wall/BC schema; no separate overlay is loaded.
        assert "issue633_c2_wall_3ion_overlay.json" not in text
        mechanism = json.loads((PILOT / "chemistry" / f"unified_s6_{case}_newonly.json").read_text())
        assert {"O2p", "Om", "Op"} <= set(mechanism["species"])
        assert "drift_diffusion_boundaries" in mechanism
        assert all(mechanism["species"][id]["sticking_coefficient"] == 1
                   for id in ("O2p", "Om", "Op"))
        assert "fvm_species = 'O2p Om Op'" in text
        assert "fem_potential = potential" in text
        assert "temperature = 300" in text
        assert "[Poisson]" not in text
        assert RETIRED not in text
        lines = [line.strip() for line in text.splitlines()
                 if line.strip().startswith(PARAM + " =")]
        assert len(lines) == 1
        assert _value(lines[0]) == 0.001


def test_wall_json_has_only_physical_parameters_and_no_numerical_gate():
    data = json.loads(JSON.read_text())
    assert len(data["species"]) == 3
    assert PARAM not in data and RETIRED not in data
    for species in ("O2p", "Om", "Op"):
        record = data["species"][species]
        assert PARAM not in record and RETIRED not in record
        assert "ion_wall" not in record
        assert "wall_molar_mass" in record
        assert "wall_sticking" in record
        assert "wall_ion_temperature_eV" in record


def test_default_zero_and_explicit_zero_are_the_same_hard_gate():
    source = CONTINUITY.read_text()
    wall = WALL.read_text()
    # Declared with a default (not a required parameter).
    assert 'params.addParam<Real>(\n      "migration_smoothing_width",\n      0.0,' in source
    assert 'getParam<Real>("migration_smoothing_width")' in source
    assert 'if (!isParamValid("migration_smoothing_width"))' not in source

    # The material receives 0 whether defaulted or explicitly set to 0.
    assert 'params.set<Real>("migration_gate_smoothing_width") =' in CHEM.read_text()
    assert 'continuity.front()->getParam<Real>("migration_smoothing_width")' in CHEM.read_text()
    assert 'if (smoothing_width <= 0.0)' in wall
    assert 'MetaPhysicL::raw_value(directed_field) > 0.0' in wall
    assert 'ADReal(0.0) * directed_field' in wall

    for x in (-1.0, -0.001, 0.0, 0.001, 1.0):
        assert (x if x > 0.0 else 0.0) == max(x, 0.0)


def test_negative_or_nonfinite_explicit_values_fail_closed():
    source = CONTINUITY.read_text()
    assert 'if (!std::isfinite(smoothing) || smoothing < 0.0)' in source
    assert 'paramError("migration_smoothing_width",' in source
    assert 'if (!isParamValid("migration_smoothing_width"))' not in source
    # The option occurs in its declaration, access, and error path.
    # Mutating only its first occurrence does not remove the contract.
    assert source.count('"migration_smoothing_width"') >= 3
    assert source.count('smoothing < 0.0') == 1
    mutated = source.replace(
        'if (!std::isfinite(smoothing) || smoothing < 0.0)', '', 1)
    assert 'if (!std::isfinite(smoothing) || smoothing < 0.0)' not in mutated


def test_no_second_legacy_numerical_owner_in_species_record_or_json_parser():
    chem = CHEM.read_text()
    header = HEADER.read_text()
    assert 'record.contains("migration_smoothing_width")' in chem
    assert 'record.contains("wall_migration_gate_smoothing_width")' in chem
    assert 'root.contains("migration_smoothing_width")' in chem
    assert 'root.contains("wall_migration_gate_smoothing_width")' in chem
    assert 'continuity.front()->getParam<Real>("migration_smoothing_width")' in chem
    assert "double migration_gate_smoothing_width" not in header
    assert 'number("wall_migration_gate_smoothing_width")' not in chem
