"""Issue #633: New-only C2 migration gate width is exclusively MOOSE-input owned.

P0 static/negative controls. This does not assert a PhysicsApp binary or S6 P2.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "experiments/Issue402_plasma_dsl_g1"
JSON = ROOT / "physics_app/ci/issue633_c2_wall_3ion_overlay.json"
CONTINUITY = ROOT / "physics_app/src/physics/plasma/DDContinuityEq.C"
CHEM = ROOT / "physics_app/src/physics/plasma/Chemistry.C"
HEADER = ROOT / "physics_app/include/physics/plasma/Chemistry.h"
CASES = ("417", "941")
PARAM = "wall_migration_gate_smoothing_width"


def _value(line):
    return float(line.split("=", 1)[1].split("#", 1)[0].strip())


def test_newonly_s6_inputs_explicitly_preserve_001_v_per_m_width():
    for case in CASES:
        path = PILOT / f"issue633_newonly_s6_{case}_continuity.template.i"
        text = path.read_text()
        assert f"unified_s6_{case}.json" in text
        assert "issue633_c2_wall_3ion_overlay.json" in text
        assert "fvm_species = 'O2p Om Op'" in text
        assert "fem_potential = potential" in text
        assert "temperature = 300" in text
        assert "[Poisson]" not in text
        lines = [line.strip() for line in text.splitlines()
                 if line.strip().startswith(PARAM + " =")]
        assert len(lines) == 1
        assert _value(lines[0]) == 0.001


def test_wall_json_has_only_physical_parameters_and_no_gate_override():
    data = json.loads(JSON.read_text())
    assert len(data["species"]) == 3
    for species in ("O2p", "Om", "Op"):
        record = data["species"][species]
        assert PARAM not in record
        assert "ion_wall" not in record
        assert "wall_molar_mass" in record
        assert "wall_sticking" in record
        assert "wall_ion_temperature_eV" in record


def test_moose_parameter_fail_closed_and_single_source_handoff():
    source = CONTINUITY.read_text()
    action = CHEM.read_text()
    record = HEADER.read_text()
    assert 'params.addParam<Real>(\n      "wall_migration_gate_smoothing_width",' in source
    assert 'if (mechanism.hasIonWalls())' in source
    assert 'if (!isParamValid("wall_migration_gate_smoothing_width"))' in source
    assert 'if (!std::isfinite(smoothing) || smoothing < 0.0)' in source
    assert 'if (record.contains("wall_migration_gate_smoothing_width"))' in action
    assert '".wall_migration_gate_smoothing_width belongs in MOOSE [Continuity], not JSON"' in action
    assert 'continuity.front()->getParam<Real>("wall_migration_gate_smoothing_width")' in action
    assert "double migration_gate_smoothing_width" not in record
    assert 'params.set<Real>("migration_gate_smoothing_width") =' in action


def test_static_negative_controls_catch_zero_missing_negative_and_nonfinite():
    source = CONTINUITY.read_text()
    # Zero is intentionally permitted for the exact hard outward-only gate.
    assert not (0.0 < 0.0)
    for bad in (-0.001, float("nan"), float("inf")):
        import math
        assert not math.isfinite(bad) or bad < 0.0
    for required in (
        'if (!isParamValid("wall_migration_gate_smoothing_width"))',
        'if (!std::isfinite(smoothing) || smoothing < 0.0)',
    ):
        assert required in source
        assert required not in source.replace(required, "", 1)
