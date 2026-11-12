"""Issue402: all selected FEM/FVM species get JSON-driven DDMaterial providers.

This static/schema check supplements exact-head Native P1 and P2; values
in the fixtures are synthetic and must not be promoted to S6.
"""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "experiments/Issue402_plasma_dsl_g1"


def test_json_drives_species_transport_without_i_material_blocks():
    deck = (PILOT / "valid_json_dd_fem_fvm_mixed_p2.i").read_text()
    data = json.loads((PILOT / "json_dd_fem_fvm_mixed_p2.json").read_text())
    owners = data["transport_coefficients"]["drift_diffusion"]
    assert set(owners) == {"e", "O2p", "Om", "Op"}
    assert owners["e"]["model"] == "lookup"
    assert owners["e"]["table_units"] == "reduced"
    assert owners["Om"]["model"] == "lookup"
    assert owners["Om"]["table_units"] == "physical"
    for ion in ("O2p", "Op"):
        assert owners[ion]["model"] == "constant"
        assert owners[ion]["mobility"] >= 0
        assert owners[ion]["diffusivity"] >= 0
    assert owners["Om"]["table_file"] == "lookup_om_physical_p2.txt"
    assert (PILOT / owners["Om"]["table_file"]).exists()
    assert "fem_species = 'e 1e16'" in deck
    assert "fvm_species = 'O2p 1e16 Om 1e14 Op 1e15'" in deck
    assert "require_json_transport" not in deck
    assert "[DDMaterial]" not in deck
    assert "type = DDMaterial" not in deck
    assert "electron_energy_mobility" not in deck


def test_continuity_maps_both_species_families_to_ddmaterial():
    code = (ROOT / "physics_app/src/physics/plasma/DDContinuityEq.C").read_text()
    assert '"require_json_transport"' not in code
    assert "chemistryData().hasDDTransport()" in code
    assert "validate(_fem_species, \"fem_species\", \"FEM\")" in code
    assert "validate(_fvm_species, \"fvm_species\", \"FVM\")" in code
    assert 'const auto * config = mechanism.ddTransport(id)' in code
    assert "species.insert(species.end(), fvm.begin(), fvm.end())" in code
    assert 'getProblem().addFunctorMaterial(type, name() + "_" + id + "_transport_coefficients", params)' in code
    assert 'params.set<MooseEnum>("model") = config->model' in code
    assert 'params.set<FileName>("table_file") = config->table_file' in code
    assert 'params.set<Real>("mobility") = config->mobility' in code
    assert 'params.set<Real>("diffusivity") = config->diffusivity' in code


def test_json_and_lookup_data_are_validated_fail_closed():
    parser = (ROOT / "physics_app/src/physics/plasma/Chemistry.C").read_text()
    provider = (ROOT / "physics_app/src/materials/DDMaterial.C").read_text()
    assert "resolveDataFile(requiredText(value, \"table_file\", file), file)" in parser
    assert "std::isfinite(result.mobility)" in parser
    assert "std::isfinite(result.diffusivity)" in parser
    assert "DDMaterial lookup coefficients must be finite and nonnegative" in provider
    assert 'std::isfinite(coordinate)' in provider
    missing = json.loads((PILOT / "invalid_json_dd_missing_om_p2.json").read_text())
    assert "Om" not in missing["transport_coefficients"]["drift_diffusion"]
    assert "Om" in json.loads((PILOT / "json_dd_fem_fvm_mixed_p2.json").read_text())["transport_coefficients"]["drift_diffusion"]
    assert "require_json_transport" not in (
        PILOT / "invalid_json_dd_missing_om_p2.i").read_text()
    assert "lookup_om_invalid_p2.txt" in (
        PILOT / "invalid_json_dd_bad_lookup_p2.json").read_text()
    runner = (PILOT / "run_native_binding_smoke.sh").read_text()
    assert "PLASMA_JSON_DD_FEM_FVM_MIXED_P2_PASS" in runner
    assert "PLASMA_JSON_DD_MISSING_AND_INVALID_LOOKUP_REJECTED" in runner


def test_legacy_s6_is_not_silently_overridden():
    for variant in ("417", "941"):
        deck = (PILOT / f"s6_{variant}_chemistry_run.template.i").read_text()
        assert "require_json_transport" not in deck
        assert "fvm_species = 'O2p Om Op'" in deck
        for item in ("chemistry/oxygen_s6_common.json", f"chemistry/oxygen_s6_{variant}.json"):
            source = json.loads((PILOT / item).read_text())
            assert "transport_coefficients" not in source
