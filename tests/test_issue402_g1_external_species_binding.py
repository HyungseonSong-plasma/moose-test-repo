"""Check the plasma input validation classes and example inputs.

These tests do not replace building or running the solver.
"""
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "physics_app"
CASE = ROOT / "experiments/Issue402_plasma_dsl_g1"


def sources():
    base_header = (APP / "include/physics/plasma/PlasmaInterface.h").read_text()
    base_source = (APP / "src/physics/plasma/PlasmaInterface.C").read_text()
    header = (APP / "include/physics/plasma/ContinuityPhysics.h").read_text()
    source = (APP / "src/physics/plasma/ContinuityPhysics.C").read_text()
    app = (APP / "src/base/PhysicsApp.C").read_text()
    return base_header, base_source, header, source, app


def test_continuity_uses_shared_plasma_validation():
    base_header, base_source, header, source, app = sources()
    assert "class PlasmaInterface : public PhysicsBase" in base_header
    assert "class ContinuityPhysics : public PlasmaInterface" in header
    assert "namespace Plasma" in header
    assert "void checkIntegrity() const override;" in header
    assert "validateSpeciesInputs(" in base_source
    assert "validateExistingSpeciesVariables(" in base_source
    assert "validateSpeciesInputs(" in source
    assert "validateExistingSpeciesVariables(" in source
    assert "using Plasma::ContinuityPhysics;" in source
    assert 'registerPhysicsBaseTasks("PhysicsApp", ContinuityPhysics);' in source
    assert 'registerMooseAction("PhysicsApp", ContinuityPhysics, "check_integrity");' in source
    assert 'registerSyntax("ContinuityPhysics",' in app
    assert '"Physics/Plasmas/Transport/DriftDiffusion/Continuity"' in app
    assert 'syntax.registerActionSyntax("PlasmaClosuresAction", "PlasmaClosures/*");' in app
    assert 'syntax.registerActionSyntax("GummelIterationAction", "GummelIteration/*");' in app


def test_existing_variables_only():
    _, base_source, _, source, _ = sources()
    assert 'addParam<std::vector<std::string>>(\n      "fem_species"' in source
    assert 'addParam<std::vector<std::string>>(\n      "fvm_species"' in source
    assert '"owner_mode"' in base_source
    assert 'MooseEnum("external generate", "external")' in base_source
    assert "Cannot create equations: this check only uses existing solver variables." in base_source
    assert "Repeated or empty species in fem_species:" in base_source
    assert "Repeated or empty species in fvm_species" in base_source
    assert "Species '" in base_source
    assert "solverVariableExists(variable)" in base_source
    assert "isVariableFV(variable)" in base_source
    assert "getProblem().add" not in base_source + source
    assert "schema_version" not in base_source + source
    assert '"discretization"' not in base_source + source


def test_small_example_has_finite_element_and_finite_volume_equations():
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
def test_example_inputs(filename, expected):
    text = (CASE / filename).read_text()
    assert expected in text
    assert "[Physics]" in text
    assert "[Plasmas]" in text
    assert "[DriftDiffusion]" in text
    assert "[Continuity]" in text
    assert "schema_version" not in text


def test_native_build_and_comparison_script():
    runner = (CASE / "run_native_binding_smoke.sh").read_text()
    assert "physics-opt" in runner and "make -C physics_app -j2" in runner
    assert "app_non_unity_dirs='%/utils'" in runner
    assert "PLASMA_RESULTS_MATCH" in runner
    assert "invalid_overlap invalid_fem_fv_swap invalid_generate invalid_missing_variable" in runner
    assert "sha256sum" in runner
    assert "physics_app/src/physics/plasma/PlasmaInterface.C" in runner
    assert "physics_app/src/physics/plasma/ContinuityPhysics.C" in runner
    assert "ghcr.io/hyungseonsong-plasma/physics-build-base@sha256:" in runner
    assert "Do not change existing production simulation inputs" in runner
