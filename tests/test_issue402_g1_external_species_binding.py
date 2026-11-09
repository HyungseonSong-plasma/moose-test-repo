"""Check the registered C++ class and example inputs.

These tests do not replace building or running the solver.
"""
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "physics_app"
CASE = ROOT / "experiments/Issue402_plasma_dsl_g1"


def pilot():
    header = (APP / "include/physics/PlasmaSpeciesVariableCheckPhysics.h").read_text()
    src = (APP / "src/physics/PlasmaSpeciesVariableCheckPhysics.C").read_text()
    app = (APP / "src/base/PhysicsApp.C").read_text()
    return header, src, app


def test_exact_native_physicsbase_registration_only():
    header, src, app = pilot()
    assert "public PhysicsBase" in header
    assert "void checkIntegrity() const override;" in header
    assert 'registerPhysicsBaseTasks("PhysicsApp", PlasmaSpeciesVariableCheckPhysics);' in src
    assert 'registerMooseAction("PhysicsApp", PlasmaSpeciesVariableCheckPhysics, "check_integrity");' in src
    assert 'registerSyntax("PlasmaSpeciesVariableCheckPhysics",' in app
    assert '"Physics/Plasmas/Transport/DriftDiffusion/Continuity"' in app
    assert 'syntax.registerActionSyntax("PlasmaClosuresAction", "PlasmaClosures/*");' in app
    assert 'syntax.registerActionSyntax("GummelIterationAction", "GummelIteration/*");' in app


def test_no_implicit_equation_generation_or_schema_version():
    _, src, _ = pilot()
    assert 'addParam<std::vector<std::string>>(\n      "fem_species"' in src
    assert 'addParam<std::vector<std::string>>(\n      "fvm_species"' in src
    assert '"owner_mode"' in src
    assert 'MooseEnum("external generate", "external")' in src
    assert "Cannot create equations: this check only uses existing solver variables." in src
    assert "Repeated or empty species in fem_species:" in src
    assert "Repeated or empty species in fvm_species" in src
    assert "Species '" in src
    assert "solverVariableExists(variable)" in src
    assert "isVariableFV(variable)" in src
    assert "getProblem().add" not in src
    assert "schema_version" not in src
    assert '"discretization"' not in src


def test_test_fixture_has_real_fem_and_fv_diffusion_equations():
    text = (CASE / "baseline.i").read_text()
    assert "[u_fe]" in text and "family = LAGRANGE" in text
    assert "[u_fv]" in text and "type = MooseVariableFVReal" in text
    assert "type = Diffusion" in text
    assert "type = FVDiffusion" in text
    assert "type = FVDirichletBC" in text
    assert "[Executioner]" in text and "type = Steady" in text


@pytest.mark.parametrize(
    "filename,expected",
    [
        ("valid_bindings.i", "owner_mode = external"),
        ("invalid_overlap.i", "fem_species = 'e O2p'"),
        ("invalid_fem_fv_swap.i", "variables = 'u_fv u_fe'"),
        ("invalid_generate.i", "owner_mode = generate"),
        ("invalid_missing_variable.i", "missing_fe"),
    ],
)
def test_native_control_inputs_present(filename, expected):
    text = (CASE / filename).read_text()
    assert expected in text
    assert "[Physics]" in text
    assert "[Plasmas]" in text
    assert "[DriftDiffusion]" in text
    assert "[Continuity]" in text
    assert "schema_version" not in text


def test_run_instructions_avoid_history_mutation():
    runner = (CASE / "run_native_binding_smoke.sh").read_text()
    assert "physics-opt" in runner and "make -C physics_app -j2" in runner
    assert "PLASMA_RESULTS_MATCH" in runner
    assert "invalid_overlap invalid_fem_fv_swap invalid_generate invalid_missing_variable" in runner
    assert "sha256sum" in runner
    assert "ghcr.io/hyungseonsong-plasma/physics-build-base@sha256:" in runner
    assert "Do not change existing production simulation inputs" in runner
