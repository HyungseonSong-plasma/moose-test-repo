"""Issue 402: source-level energy and Poisson state ownership regression."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "physics_app/src/physics/plasma"
CASE = ROOT / "experiments/Issue402_plasma_dsl_g1"


def test_energy_autogeneration_requires_positive_molar_energy():
    code = (APP / "DDEnergyEq.C").read_text()
    for token in ('"initial_molar_energy_density_eV"', "std::isfinite(initial)",
                  "initial <= 0.0", "variableExists(variable",
                  "getProblem().addVariable(", "getProblem().addInitialCondition(",
                  'std::log(initial_energy)',
                  '1.5 * (*electron.temperature_eV) * (*electron.initial_number_density)',
                  '"add_variables_physics"', '"add_ics_physics"'):
        assert token in code


def test_poisson_name_and_fem_type():
    code = (APP / "PoissonEq.C").read_text()
    for token in ('"fem_potential"', '"initial_potential_V"',
                  "std::isfinite(", "variableExists(variable",
                  "getProblem().addVariable(", "getProblem().addInitialCondition(",
                  "isVariableFV(potential)", '"add_variables_physics"',
                  '"add_ics_physics"'):
        assert token in code
    assert '"potential_variable"' not in code


def test_p2_decks_and_legacy_variable_reuse():
    good = (CASE / "auto_energy_potential_p2.i").read_text()
    assert "[Variables]" not in good
    assert "fem_species = e" in good
    assert "files = plasma_species_initial_p2.json" in good
    assert "initial_number_density" not in good
    assert "fem_potential = potential" in good
    assert "initial_molar_energy_density_eV = 4.98161720152154e-8" in good
    assert "initial_potential_V = 0" in good
    assert "initial_molar_energy_density_eV =" not in (CASE / "invalid_auto_energy_missing_initial_p2.i").read_text()
    assert "initial_molar_energy_density_eV = 0" in (CASE / "invalid_auto_energy_zero_initial_p2.i").read_text()
    assert "initial_potential_V = nan" in (CASE / "invalid_auto_poisson_nan_initial_p2.i").read_text()
    assert "fem_potential = log_e" in (CASE / "valid_all_physics.i").read_text()
    assert "fem_potential = log_O2p" in (CASE / "invalid_poisson_variable.i").read_text()
    run = (CASE / "run_native_binding_smoke.sh").read_text()
    assert "PLASMA_AUTO_ENERGY_POTENTIAL_P2_PASS" in run
    assert "PLASMA_INVALID_AUTO_ENERGY_POTENTIAL_REJECTED" in run

def test_issue633_energy_closure_is_i_owned_and_p2_guards_current_diagnostic():
    energy = (APP / "DDEnergyEq.C").read_text()
    smoke = (CASE / "run_native_binding_smoke.sh").read_text()
    native = (ROOT / "physics_app/ci/check_issue402_dd_json_plasma_boundary_p2.py").read_text()
    assert 'MooseEnum("fluid", "fluid")' in energy
    assert "species.e initial_number_density and positive temperature_eV in JSON" in energy
    assert "requires either explicit .i initial_molar_energy_density_eV" in smoke
    assert 'FULL_PHYSICS_JSON_ENERGY_CLOSURE_OPTIONAL' in native
    assert 'FULL_PHYSICS_EXPLICIT_ENERGY_FLUID' in native
    assert 'FULL_PHYSICS_INVALID_ENERGY_CLOSURE' in native
    assert 'FULL_PHYSICS_MISSING_E_ENERGY_FLUID' not in native
