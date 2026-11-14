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
                  'std::log(getParam<Real>("initial_molar_energy_density_eV"))',
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


def test_electron_fem_only_and_non_electron_fvm_preserved():
    """The electron FVM DSL is retired; ion FVM creation remains active."""
    continuity = (APP / "DDContinuityEq.C").read_text()
    energy = (APP / "DDEnergyEq.C").read_text()
    p2 = (ROOT / "physics_app/ci/check_issue402_dd_json_plasma_boundary_p2.py").read_text()

    assert '"fvm_species"' not in energy
    assert 'validateSpeciesInputs(finite_element_species,\n                        {},' in energy
    assert 'validateExistingSpeciesVariables(getParam<std::vector<std::string>>("fem_species"),\n                                   {},' in energy
    assert 'std::find(_fvm_species.begin(), _fvm_species.end(), "e")' in continuity
    assert 'Electron continuity is FEM-only' in continuity
    assert 'generate(_fvm_initial_number_densities, true, "fvm_species");' in continuity
    assert 'generate(_fvm_initial_number_densities, true);' in continuity
    assert 'validate(_fvm_species, "fvm_species", "FVM");' in continuity
    assert 'species.insert(species.end(), fvm.begin(), fvm.end());' in continuity
    for marker in ("JSON_FEM_FVM_INITIAL_NUMBER_DENSITY",
                   "ELECTRON_FVM_CONTINUITY_REJECTED",
                   "ELECTRON_FVM_ENERGY_OPTION_REJECTED"):
        assert marker in p2
