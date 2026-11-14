"""Fail-closed P0 contract for the three incompatible Issue402 fixture modes.

No solver, private S6 kinetic data or scientific parity is implied here.
The frozen Native baseline is never modified or stacked with generated states.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / "experiments/Issue402_plasma_dsl_g1"


def deck(name: str) -> str:
    return (BASE / name).read_text()


def catalogue(name: str) -> dict:
    return json.loads((BASE / name).read_text())


def test_original_legacy_baseline_is_byte_unchanged():
    original = (BASE / "baseline.i").read_bytes()
    git_blob = b"blob " + str(len(original)).encode() + b"\x00" + original
    assert hashlib.sha1(git_blob).hexdigest() == "f2d841b804724107496353d7cee3a9c8da676df5"
    overlay = deck("legacy_noop_physics.i")
    assert "files = plasma_noop_control.json" in overlay
    assert "[Poisson]" in overlay and "[Maxwell]" in overlay
    assert "fem_potential = log_e" in overlay
    for generated in ("[Continuity]", "[Energy]", "[Chemistry]"):
        assert generated not in overlay
    for forbidden in ("[Variables]", "[Kernels]", "[FVKernels]", "[BCs]", "[FVBCs]"):
        assert forbidden not in overlay


def test_all_physics_is_a_disjoint_json_owned_construction_check():
    d = deck("valid_all_physics.i")
    for name in ("[Chemistry]", "[Continuity]", "[Energy]", "[Poisson]", "[Maxwell]"):
        assert name in d
    assert "files = plasma_two_channels.json" in d
    assert "fem_potential = potential" in d
    assert "field_real = potential" in d and "field_imag = u_rf_imag" in d
    assert "initial_molar_energy_density_eV = 4.98161720152154e-8" in d
    assert "solve = false" in d and "kernel_coverage_check = false" in d
    for old_var in ("[log_e]", "[log_O2p]", "[log_e_energy]"):
        assert old_var not in d
    e = catalogue("plasma_two_channels.json")["species"]["e"]
    assert e["initial_number_density"] > 0
    assert e["energy_transport_coef"] == "fluid"
    assert e["transport_coef"] == "constant"


def test_every_positive_electron_dsl_fixture_has_json_initial_density():
    for input_name, json_name in (
        ("valid_generated_transport_options.i", "plasma_auto_constant.json"),
        ("chemistry_two_channels.i", "plasma_two_channels.json"),
        ("chemistry_s6_417_catalogue_p2.i", "chemistry/oxygen_s6_p2_transport.json"),
        ("chemistry_s6_941_catalogue_p2.i", "chemistry/oxygen_s6_p2_transport.json"),
    ):
        d = deck(input_name)
        e = catalogue(json_name)["species"]["e"]
        assert e["initial_number_density"] > 0
        assert "[log_e]" not in d
        assert "fem_species = 'e'" in d
    generated = deck("valid_generated_transport_options.i")
    assert "fem_potential = potential" in generated
    assert "[potential]" in generated
    assert "solve = false" in generated
    for name in ("chemistry_s6_417_catalogue_p2.i",
                 "chemistry_s6_941_catalogue_p2.i"):
        d = deck(name)
        assert "synthetic_rate_and_transport_providers" in d
        assert "[log_e_energy]" in d  # Explicitly partial Energy; no auto-Energy IC.


def test_runner_enforces_three_separate_contracts():
    s = deck("run_native_binding_smoke.sh")
    assert 'native --check-input -i "$PILOT/valid_all_physics.i"' in s
    assert 'native --check-input -i "$PILOT/valid_generated_transport_options.i"' in s
    assert 'native -i "$PILOT/baseline.i" "$PILOT/legacy_noop_physics.i"' in s
    assert 'native -i "$PILOT/baseline.i" "$PILOT/valid_all_physics.i"' not in s
    assert 'native --check-input -i "$PILOT/baseline.i" "$PILOT/valid_all_physics.i"' not in s
    assert 'PLASMA_JSON_ALL_PHYSICS_P2_PASS' in s
    assert 'PLASMA_LEGACY_NOOP_PARITY_PASS' in s
    assert "invalid_fem_fv_swap) expected='Electron continuity is FEM-only'" in s
    assert 'invalid_missing_variable) expected="requires species.missing.initial_number_density"' in s
    assert 'invalid_species_density_nan_p2:requires species.nan.initial_number_density' in s


def test_direct_native_materials_are_canonical_log_molar():
    # Reuse the original physical Aux densities; do not replace them with a
    # free-standing '3 eV' constant or re-enable the retired physical_eV mode.
    s = (BASE.parents[1] / "physics_app/ci/plasma_direct_existing_materials_smoke.i").read_text()
    assert "state_form = log_molar_eV" in s
    assert "state_form = physical_eV" not in s
    assert "property_name = log_e" in s
    assert "property_name = log_e_energy" in s
    assert "expression = 'log(ne/6.02214076e23)'" in s
    assert "expression = 'log(we/6.02214076e23)'" in s
    assert "electron_density = log_e" in s
    assert "electron_energy_density = log_e_energy" in s
    assert "electron_number_density = electron_number_density_physical" in s
    assert "electron_energy_density_physical" in s
    from math import exp, log, isclose
    assert isclose(exp(log(3e15 / 6.02214076e23) - log(1e15 / 6.02214076e23)),
                   3.0, rel_tol=1e-14)


def test_deprecated_option_negatives_have_independent_state_owner():
    runner = deck("run_native_binding_smoke.sh")
    assert 'if [[ "$item" == invalid_poisson_variable ]]' in runner
    assert 'native --check-input -i "$PILOT/$item.i"' in runner
    # Only Poisson requires baseline.i to prove that an existing FV log_O2p
    # is illegal as a FEM electric potential. Deprecated-key negatives use
    # valid JSON initialization, so their *intended* errors are never masked.
    for name in (
        "invalid_legacy_variables.i",
        "invalid_legacy_kernel_names.i",
        "invalid_incomplete_coefficients.i",
        "invalid_missing_fvm_charges.i",
        "invalid_wrong_charge_sign.i",
    ):
        s = deck(name)
        assert "files = plasma_species_initial_p2.json" in s
        assert "fem_species = 'e'" in s
    assert 'fem_potential = log_O2p' in deck("invalid_poisson_variable.i")
