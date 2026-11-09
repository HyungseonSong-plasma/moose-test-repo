"""Issue #402 G1 external-only FEM/FV PhysicsBase integration contract.

This file is a static/fixture test, NOT native MOOSE compilation evidence.
Actual C++ build, --check-input and solve are required by the OCI runner.
"""
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "physics_app"
CASE = ROOT / "experiments/Issue402_plasma_dsl_g1"


def pilot():
    header = (APP / "include/physics/PlasmaSpeciesContinuityPhysics.h").read_text()
    src = (APP / "src/physics/PlasmaSpeciesContinuityPhysics.C").read_text()
    app = (APP / "src/base/PhysicsApp.C").read_text()
    return header, src, app


def test_exact_native_physicsbase_registration_only():
    header, src, app = pilot()
    assert "public PhysicsBase" in header
    assert "void checkIntegrity() const override;" in header
    assert 'registerPhysicsBaseTasks("PhysicsApp", PlasmaSpeciesContinuityPhysics);' in src
    assert 'registerMooseAction("PhysicsApp", PlasmaSpeciesContinuityPhysics, "check_integrity");' in src
    assert 'registerSyntax("PlasmaSpeciesContinuityPhysics",' in app
    assert '"Physics/Plasmas/Transport/DriftDiffusion/Continuity"' in app
    assert 'syntax.registerActionSyntax("PlasmaClosuresAction", "PlasmaClosures/*");' in app
    assert 'syntax.registerActionSyntax("GummelIterationAction", "GummelIteration/*");' in app


def test_no_implicit_equation_generation_or_schema_version():
    _, src, _ = pilot()
    assert 'addParam<std::vector<std::string>>(\n      "fem_species"' in src
    assert 'addParam<std::vector<std::string>>(\n      "fvm_species"' in src
    assert '"owner_mode"' in src
    assert 'MooseEnum("external generate", "external")' in src
    assert "P402_OWNER: G1 external-binding pilot cannot generate" in src
    assert "P402_SPECIES: duplicate or empty FEM species:" in src
    assert "P402_SPECIES: duplicated across FEM/FV" in src
    assert "P402_SPECIES: species '" in src
    assert "solverVariableExists(var)" in src
    assert "isVariableFV(var)" in src
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
    assert "P402_G1_EXTERNAL_BINDING_NATIVE_RUN_PARITY_PASS" in runner
    assert "invalid_overlap invalid_fem_fv_swap invalid_generate invalid_missing_variable" in runner
    assert "sha256sum" in runner
    assert "ghcr.io/hyungseonsong-plasma/physics-build-base@sha256:" in runner
    assert "S6" in runner
