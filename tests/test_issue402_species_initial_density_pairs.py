"""Issue #402 species/density pairs: source and P2 wiring contract.

These checks do not claim a successful C++ Native build or S6 numerical parity.
"""
from pathlib import Path
import math

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "experiments/Issue402_plasma_dsl_g1"


def test_paired_species_schema_and_finite_positive_checks():
    source = (ROOT / "physics_app/src/physics/plasma/DDContinuityEq.C").read_text()
    header = (ROOT / "physics_app/include/physics/plasma/DDContinuityEq.h").read_text()
    for token in ("parseSpeciesInput", "startsNumber", "std::strtod",
                  "std::isfinite(number_density)", "number_density > 0.0",
                  "tokens.size() % 2 != 0", "initial_number_density [1/m^3]"):
        assert token in source
    assert "std::log(density) - std::log(PHYSICS_CONSTANTS::N_A)" in source
    assert "getProblem().addVariable(type, variable, params)" in source
    assert "getProblem().addInitialCondition" in source
    assert "getProblem().addFVInitialCondition" in source
    assert "shouldCreateIC(" in source
    assert '"add_variables_physics"' in source
    assert '"add_ics_physics"' in source
    assert "void addSolverVariables() override;" in header
    assert "void addInitialConditions() override;" in header
    # No arbitrary floor and no substitution of input number density for log-state value.
    assert math.isclose(math.log(1e16) - math.log(6.02214076e23),
                        math.log(1e16 / 6.02214076e23), abs_tol=1e-13)


def test_synthetic_paired_input_omits_density_variables():
    deck = (PILOT / "species_density_pairs_p2.i").read_text()
    assert "# Format: species_name initial_number_density ..." in deck
    assert "fem_species = 'e 1e16'" in deck
    assert "fvm_species = 'O2p 1e16 Om 1e14 Op 1e15'" in deck
    for state in ("log_e", "log_O2p", "log_Om", "log_Op"):
        assert f"[{state}]" not in deck
    assert "[potential]" in deck
    assert "kernel_coverage_check = false" in deck
    assert "type = Transient" in deck


def test_negative_p2_cases_and_unchanged_legacy_inputs():
    assert "fem_species = 'e 0'" in (PILOT / "invalid_species_density_zero_p2.i").read_text()
    assert "fvm_species = 'O2p 1e16 Om'" in (PILOT / "invalid_species_density_odd_p2.i").read_text()
    assert "fem_species = 'e nan'" in (PILOT / "invalid_species_density_nan_p2.i").read_text()
    runner = (PILOT / "run_native_binding_smoke.sh").read_text()
    for case in ("species_density_pairs_p2", "invalid_species_density_zero_p2",
                 "invalid_species_density_odd_p2", "invalid_species_density_nan_p2"):
        assert case in runner
    assert "PLASMA_SPECIES_DENSITY_PAIRS_P2_PASS" in runner
    assert "PLASMA_INVALID_SPECIES_DENSITY_PAIRS_REJECTED" in runner
    # Frozen archive and current S6 staging remain names-only (external variables).
    for variant in ("417", "941"):
        old = (PILOT / f"s6_{variant}_chemistry_run.template.i").read_text()
        assert "fem_species = 'e'" in old
        assert "fvm_species = 'O2p Om Op'" in old
