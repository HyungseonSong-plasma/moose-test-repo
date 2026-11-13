"""Issue #402: JSON species-owned FEM/FVM number-density initialization contract.

P0 validates source and fixtures; Native P1/P2 prove compilation/input
construction separately. Neither test establishes physical P3 parity.
"""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "experiments/Issue402_plasma_dsl_g1"
APP = ROOT / "physics_app"


def test_json_species_schema_and_positive_finite_validation():
    parser = (APP / "src/physics/plasma/Chemistry.C").read_text()
    header = (APP / "include/physics/plasma/Chemistry.h").read_text()
    continuity = (APP / "src/physics/plasma/DDContinuityEq.C").read_text()
    for fragment in (
        'record.contains("initial_number_density")',
        'record.at("initial_number_density").is_number()',
        "std::isfinite(density)",
        "density <= 0.0",
        "species.initial_number_density = density;",
        "existing->second.initial_number_density = species.initial_number_density;",
    ):
        assert fragment in parser
    assert "std::optional<double> initial_number_density;" in header
    assert "bind_json_initial(fem, _fem_initial_number_densities);" in continuity
    assert "bind_json_initial(fvm, _fvm_initial_number_densities);" in continuity
    assert "parseSpeciesInput" not in continuity
    assert "startsNumber" not in continuity
    assert "std::strtod" not in continuity
    assert "std::log(density) - std::log(PHYSICS_CONSTANTS::N_A)" in continuity
    assert "getProblem().addVariable(type, variable, params)" in continuity
    assert "getProblem().addInitialCondition" in continuity
    assert "getProblem().addFVInitialCondition" in continuity
    assert "shouldCreateIC(" in continuity
    assert '"add_variables_physics"' in continuity
    assert '"add_ics_physics"' in continuity
    assert "Choose JSON auto-generation OR external [Variables]/IC ownership" in continuity
    assert math.isclose(
        math.log(1e16) - math.log(6.02214076e23),
        math.log(1e16 / 6.02214076e23),
        abs_tol=1e-13,
    )


def test_p2_names_only_fem_fvm_with_json_initials():
    deck = (PILOT / "species_density_pairs_p2.i").read_text()
    data = json.loads((PILOT / "plasma_species_initial_p2.json").read_text())
    assert "files = plasma_species_initial_p2.json" in deck
    assert "fem_species = e" in deck
    assert "fvm_species = 'O2p Om Op'" in deck
    assert "initial_number_density" not in deck
    expected = {"e": 1e16, "O2p": 1e16, "Om": 1e14, "Op": 1e15}
    assert {id: data["species"][id]["initial_number_density"]
            for id in expected} == expected
    for state in ("log_e", "log_O2p", "log_Om", "log_Op"):
        assert f"[{state}]" not in deck
    assert "[potential]" in deck
    assert "kernel_coverage_check = false" in deck
    assert "type = Transient" in deck


def test_retired_positional_initials_fail_closed_and_legacy_external_ownership():
    # Old positional values remain only in deliberate negative inputs.
    assert "fem_species = 'e 0'" in (
        PILOT / "invalid_species_density_zero_p2.i").read_text()
    assert "fvm_species = 'O2p 1e16 Om'" in (
        PILOT / "invalid_species_density_odd_p2.i").read_text()
    assert "fem_species = 'e nan'" in (
        PILOT / "invalid_species_density_nan_p2.i").read_text()
    runner = (PILOT / "run_native_binding_smoke.sh").read_text()
    for case in (
        "species_density_pairs_p2",
        "invalid_species_density_zero_p2",
        "invalid_species_density_odd_p2",
        "invalid_species_density_nan_p2",
    ):
        assert case in runner
    assert "PLASMA_JSON_SPECIES_INITIAL_P2_PASS" in runner
    assert "PLASMA_RETIRED_POSITIONAL_SPECIES_INITIAL_REJECTED" in runner

    # Production S6 source remains untouched: absent JSON initial_number_density
    # means externally declared solver variables retain their prior ICs.
    for variant in ("417", "941"):
        old = (PILOT / f"s6_{variant}_chemistry_run.template.i").read_text()
        assert "fem_species = 'e'" in old
        assert "fvm_species = 'O2p Om Op'" in old
        for file in ("chemistry/oxygen_s6_common.json",
                     f"chemistry/oxygen_s6_{variant}.json"):
            data = json.loads((PILOT / file).read_text())
            assert all("initial_number_density" not in species
                       for species in data["species"].values())
